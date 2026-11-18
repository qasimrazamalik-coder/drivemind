"""Fast, safe directory scanner.

- Never follows symlinks or junctions (no loops, no double counting).
- Never reads OneDrive / cloud online-only files (that would download them).
- Survives permission errors and long paths.
"""

from __future__ import annotations

import heapq
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional

from .paths import is_cloud_placeholder, is_link, long_path


@dataclass
class FileInfo:
    path: Path
    size: int
    mtime: float
    atime: float

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()

    @property
    def age_days(self) -> float:
        return (time.time() - self.mtime) / 86400


@dataclass
class ScanResult:
    root: Path
    total_size: int = 0
    file_count: int = 0
    dir_count: int = 0
    cloud_skipped: int = 0
    errors: int = 0
    seconds: float = 0.0
    dir_sizes: Dict[str, int] = field(default_factory=dict)
    ext_sizes: Dict[str, int] = field(default_factory=dict)
    largest_files: List[FileInfo] = field(default_factory=list)
    # breakdowns for the charts: label -> [file count, bytes]
    categories: Dict[str, List[int]] = field(default_factory=dict)
    age_buckets: Dict[str, List[int]] = field(default_factory=dict)
    size_buckets: Dict[str, List[int]] = field(default_factory=dict)
    stale_large: List[FileInfo] = field(default_factory=list)  # big files untouched for 6+ months

    def top_children(self, n: int = 15) -> List[tuple]:
        """Biggest direct children of the scanned root: [(path, size), ...]."""
        root = str(self.root)
        kids = [(p, s) for p, s in self.dir_sizes.items() if str(Path(p).parent) == root]
        return sorted(kids, key=lambda x: x[1], reverse=True)[:n]

    def top_dirs(self, n: int = 25, min_depth: int = 1) -> List[tuple]:
        root_depth = len(self.root.parts)
        rows = [(p, s) for p, s in self.dir_sizes.items() if len(Path(p).parts) - root_depth >= min_depth]
        return sorted(rows, key=lambda x: x[1], reverse=True)[:n]


def iter_files(root: Path, skip_dir: Optional[Callable[[Path], bool]] = None,
               on_error: Optional[Callable[[Exception], None]] = None,
               max_depth: Optional[int] = None) -> Iterator[FileInfo]:
    """Yield every regular, local file under root (iterative, no recursion limit)."""
    stack = [(Path(root), 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            it = os.scandir(long_path(folder))
        except OSError as e:
            if on_error:
                on_error(e)
            continue
        with it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError as e:
                    if on_error:
                        on_error(e)
                    continue
                if is_link(st):
                    continue
                p = folder / entry.name
                if entry.is_dir(follow_symlinks=False):
                    if skip_dir and skip_dir(p):
                        continue
                    if max_depth is None or depth < max_depth:
                        stack.append((p, depth + 1))
                    continue
                if is_cloud_placeholder(st):
                    continue
                yield FileInfo(p, st.st_size, st.st_mtime, st.st_atime)


AGE_EDGES = [(30, "< 1 month"), (182, "1–6 months"), (365, "6–12 months"), (3 * 365, "1–3 years"), (10 ** 9, "3+ years")]
SIZE_EDGES = [(1 << 20, "< 1 MB"), (100 << 20, "1–100 MB"), (1 << 30, "100 MB–1 GB"), (1 << 62, "> 1 GB")]
STALE_LARGE_BYTES, STALE_DAYS = 100 << 20, 182


def _bucket(edges, value) -> str:
    for edge, label in edges:
        if value < edge:
            return label
    return edges[-1][1]


def scan(root: Path, top_n: int = 50, skip_dir: Optional[Callable[[Path], bool]] = None,
         progress: Optional[Callable[[int], None]] = None) -> ScanResult:
    root = Path(root).resolve()
    res = ScanResult(root=root)
    t0 = time.perf_counter()
    dir_sizes: Dict[str, int] = defaultdict(int)
    ext_sizes: Dict[str, int] = defaultdict(int)
    heap: List[tuple] = []
    seen_dirs = set()
    root_str = str(root)
    from .classify import EXT_CATEGORY
    now = time.time()
    cats: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    ages: Dict[str, List[int]] = {label: [0, 0] for _, label in AGE_EDGES}
    sizes: Dict[str, List[int]] = {label: [0, 0] for _, label in SIZE_EDGES}
    stale: List[tuple] = []

    stack = [root]
    while stack:
        folder = stack.pop()
        res.dir_count += 1
        try:
            it = os.scandir(long_path(folder))
        except OSError:
            res.errors += 1
            continue
        with it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    res.errors += 1
                    continue
                if is_link(st):
                    continue
                p = folder / entry.name
                if entry.is_dir(follow_symlinks=False):
                    if skip_dir and skip_dir(p):
                        continue
                    key = (st.st_dev, st.st_ino)
                    if st.st_ino and key in seen_dirs:
                        continue
                    seen_dirs.add(key)
                    stack.append(p)
                    continue
                if is_cloud_placeholder(st):
                    res.cloud_skipped += 1
                    continue
                size = st.st_size
                res.total_size += size
                res.file_count += 1
                ext = p.suffix.lower()
                ext_sizes[ext or "(none)"] += size
                c = cats[EXT_CATEGORY.get(ext, "Other")]
                c[0] += 1
                c[1] += size
                age_days = (now - st.st_mtime) / 86400
                a = ages[_bucket(AGE_EDGES, age_days)]
                a[0] += 1
                a[1] += size
                b = sizes[_bucket(SIZE_EDGES, size)]
                b[0] += 1
                b[1] += size
                if size >= STALE_LARGE_BYTES and (now - max(st.st_mtime, st.st_atime)) / 86400 >= STALE_DAYS:
                    stale.append((size, str(p), st.st_mtime, st.st_atime))
                # add size to every ancestor up to the root
                parent = folder
                while True:
                    dir_sizes[str(parent)] += size
                    if str(parent) == root_str or parent.parent == parent:
                        break
                    parent = parent.parent
                item = (size, str(p), st.st_mtime, st.st_atime)
                if len(heap) < top_n:
                    heapq.heappush(heap, item)
                elif size > heap[0][0]:
                    heapq.heapreplace(heap, item)
                if progress and res.file_count % 5000 == 0:
                    progress(res.file_count)

    res.dir_sizes = dict(dir_sizes)
    res.ext_sizes = dict(sorted(ext_sizes.items(), key=lambda x: x[1], reverse=True))
    res.largest_files = [FileInfo(Path(p), s, m, a) for s, p, m, a in sorted(heap, reverse=True)]
    res.categories = dict(sorted(cats.items(), key=lambda kv: kv[1][1], reverse=True))
    res.age_buckets, res.size_buckets = ages, sizes
    res.stale_large = [FileInfo(Path(p), s, m, a) for s, p, m, a in sorted(stale, reverse=True)[:50]]
    res.seconds = time.perf_counter() - t0
    return res


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
