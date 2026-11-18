"""DriveMind command line.

    drivemind status                       drive health for every drive
    drivemind scan C:\\                     what is eating space (treemap data, largest files)
    drivemind organize ~/Desktop --root D:\\ --dry-run
    drivemind clean caches | temp | dev | dupes [--apply]
    drivemind plans / show ID / approve ID [ids] / apply ID / undo ID
    drivemind where report.pdf             where did my file go?
    drivemind explain "C:\\some\\folder"     what is this folder, is it safe to delete?
    drivemind mode safe|balanced|autopilot   /  drivemind set OPTION yes|ask|no
    drivemind rule "anything with invoice from Downloads goes to Work/Invoices"
    drivemind serve                        open the dashboard on http://127.0.0.1:7878
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path
from typing import List, Optional

from .config import OPTION_INFO, Decision, Mode, Settings
from .plan import Plan, Status
from .scanner import human

USE_COLOR = sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def _print_plan(p: Plan, limit: int = 60) -> None:
    s = p.summary()
    print(c(f"\nPlan {p.id}: {p.title}", "1"))
    for note in p.notes:
        print(c(f"  note: {note}", "2"))
    marks = {Status.PENDING: "?", Status.APPROVED: "+", Status.SKIPPED: "-", Status.DONE: "✓",
             Status.FAILED: "!", Status.REJECTED: "x", Status.UNDONE: "↺"}
    for a in p.actions[:limit]:
        tag = "auto" if a.decision == Decision.YES else a.decision.value
        mark = marks.get(a.status, " ")
        target = f" → {a.dst}" if a.dst else ""
        print(f"  [{mark}] {a.id} {c(tag, '36'):>6} {a.op.value:<12} {a.src}{target}")
        print(c(f"        {a.reason}  (confidence {a.confidence:.0%}, {human(a.size)})", "2"))
    if len(p.actions) > limit:
        print(f"  ... and {len(p.actions) - limit} more")
    print(f"\n  {s['actions']} actions · {s['auto']} automatic · {s['waiting']} waiting for you"
          + (f" · frees {human(s['frees_bytes'])}" if s["frees_bytes"] else ""))


def cmd_status(args) -> None:
    from .disk import drive_status, list_drives, record_snapshot
    s = Settings.load()
    for d in list_drives():
        record_snapshot(d)
        st = drive_status(d, s.low_space_percent)
        if not st:
            continue
        color = {"good": "32", "watch": "33", "critical": "31"}[st.status]
        bar = "█" * int((100 - st.free_percent) / 5) + "░" * (20 - int((100 - st.free_percent) / 5))
        print(f"{d:<6} {bar} {c(f'{st.free_percent:.0f}% free', color)}  {human(st.free)} of {human(st.total)}"
              f"  health {st.score}/100" + (f"  full in ~{st.days_to_full:.0f} days" if st.days_to_full else ""))


def cmd_scan(args) -> None:
    from .disk import growth, save_scan
    from .scanner import scan
    root = Path(args.path)
    t = time.time()
    res = scan(root, top_n=args.top, progress=lambda n: print(f"\r  {n:,} files...", end="", flush=True))
    print(f"\r{human(res.total_size)} in {res.file_count:,} files, {res.dir_count:,} folders "
          f"({time.time() - t:.1f}s; {res.cloud_skipped} cloud-only files skipped, {res.errors} unreadable)")
    save_scan(res)
    print(c("\nBiggest folders:", "1"))
    for p, size in res.top_children(15):
        print(f"  {human(size):>10}  {p}")
    print(c("\nLargest files:", "1"))
    for f in res.largest_files[:args.top]:
        print(f"  {human(f.size):>10}  {f.path}")
    g = growth(str(res.root))
    if g:
        print(c("\nGrew since the last scan:", "1"))
        for row in g[:8]:
            print(f"  {'+' if row['delta'] > 0 else ''}{human(row['delta']):>10}  {row['path']}")


def _apply_or_save(p: Plan, args) -> None:
    from .executor import apply_plan
    _print_plan(p)
    p.save()
    if getattr(args, "dry_run", False):
        print(c("\nDry run: nothing changed.", "33"))
        return
    if getattr(args, "apply", False):
        if args.yes_all:
            p.set_status([a.id for a in p.actions if a.status == Status.PENDING], Status.APPROVED)
        r = apply_plan(p, Settings.load())
        print(c(f"\nDone: {r['done']} applied, {r['failed']} failed"
                + (f", freed {human(r['freed_bytes'])}" if r["freed_bytes"] else ""), "32"))
        if p.summary()["waiting"]:
            print(f"{p.summary()['waiting']} actions still wait for you: drivemind approve {p.id}")
    else:
        print(f"\nSaved. Apply automatic actions with: drivemind apply {p.id}"
              f"\nApprove the rest with:            drivemind approve {p.id} [ids...]")


def cmd_organize(args) -> None:
    from .planner import plan_organize
    s = Settings.load()
    root = Path(args.root or s.organize_root or Path.home() / "Organized")
    p = plan_organize(Path(args.source), root, s, preset=args.preset,
                      use_ai=False if args.no_ai else None)
    _apply_or_save(p, args)


def cmd_clean(args) -> None:
    s = Settings.load()
    from .paths import user_folders
    roots = [Path(r) for r in args.roots] if args.roots else None
    if args.what == "caches":
        from .cleaner import plan_cache_clean
        p = plan_cache_clean(s, only=args.only)
    elif args.what == "temp":
        from .cleaner import plan_temp_clean
        p = plan_temp_clean(s, roots=roots)
    elif args.what == "dev":
        from .devjunk import plan_dev_junk
        p = plan_dev_junk(s, roots or [x for x in (user_folders()["Desktop"], user_folders()["Documents"],
                                                   Path.home() / "Projects") if x.exists()])
    else:
        from .duplicates import plan_duplicates
        p = plan_duplicates(s, roots or [x for x in user_folders().values() if x.exists()])
    _apply_or_save(p, args)


def cmd_caches(args) -> None:
    from .cleaner import cache_report
    for r in cache_report(Settings.load()):
        flag = " (open: " + ", ".join(r["apps_open"]) + ")" if r["apps_open"] else ""
        print(f"  {r['choice']:>4}  {human(r['size']):>10}  {r['id']:<11} {r['name']}{flag}")


def cmd_plans(args) -> None:
    for row in Plan.recent(args.limit):
        s = row["summary"]
        print(f"  {row['id']}  {row['status']:<9} {row['title']}  ({s['actions']} actions, {s['waiting']} waiting)")


def _get_plan(pid: str) -> Plan:
    p = Plan.load(pid)
    if not p:
        sys.exit(f"No plan {pid}")
    return p


def cmd_show(args) -> None:
    _print_plan(_get_plan(args.plan), limit=10_000)


def cmd_approve(args) -> None:
    p = _get_plan(args.plan)
    ids = args.ids or [a.id for a in p.actions if a.status == Status.PENDING]
    n = p.set_status(ids, Status.REJECTED if args.reject else Status.APPROVED)
    p.save()
    print(f"{'Rejected' if args.reject else 'Approved'} {n} actions. Run: drivemind apply {p.id}")


def cmd_apply(args) -> None:
    from .executor import apply_plan
    p = _get_plan(args.plan)
    r = apply_plan(p, Settings.load(), args.ids or None)
    print(f"{r['done']} applied, {r['failed']} failed" + (f", freed {human(r['freed_bytes'])}" if r["freed_bytes"] else ""))
    for a in p.actions:
        if a.status == Status.FAILED:
            print(c(f"  ! {a.src}: {a.error}", "31"))


def cmd_undo(args) -> None:
    from .executor import undo_plan
    r = undo_plan(_get_plan(args.plan))
    print(f"Restored {r['restored']} items" + (f"; {r['not_reversible']} cache deletions cannot come back"
                                               if r["not_reversible"] else ""))


def cmd_where(args) -> None:
    from .executor import where_is
    rows = where_is(args.query)
    if not rows:
        print("DriveMind has not moved anything with that name.")
    for r in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"]))
        state = "undone" if r["undone"] else ("still there" if r["exists_now"] else "no longer there")
        print(f"  {when}  {r['op']:<10} {r['src']}\n{'':20}→ {r['dst'] or '(deleted cache)'}  [{state}]")


def cmd_explain(args) -> None:
    from .explain import explain
    r = explain(Path(args.path), use_ai=not args.no_ai)
    print(f"{r['path']}  ({r['size_human']})")
    if r["source"] == "known":
        print(f"  Made by:        {r['made_by']}\n  Holds:          {r['holds']}\n  Safe to delete: {r['safe_to_delete']}")
    else:
        print("  " + r["answer"])


def cmd_mode(args) -> None:
    s = Settings.load()
    s.set_mode(Mode(args.mode))
    s.save()
    print(f"Mode set to {args.mode}.")
    cmd_settings(args)


def cmd_set(args) -> None:
    s = Settings.load()
    value = Decision(args.value)
    if args.option.startswith("cache."):
        s.cache_choices[args.option[6:]] = value
    elif args.option.startswith("temp."):
        s.temp_choices[args.option[5:]] = value
    else:
        s.set_option(args.option, value)
    s.save()
    print(f"{args.option} = {value.value}")


def cmd_settings(args) -> None:
    s = Settings.load()
    print(c(f"Mode: {s.mode.value}", "1"))
    for k, desc in OPTION_INFO.items():
        print(f"  {s.decision(k).value:>4}  {k:<27} {desc}")
    print(f"\n  organize root: {s.organize_root or '(not set)'}   confidence threshold: {s.confidence_threshold}")


def cmd_rule(args) -> None:
    from .rules import load_rules, parse_rule, save_rules
    rules = load_rules()
    if args.text:
        r = parse_rule(" ".join(args.text))
        rules.append(r)
        save_rules(rules)
        print("Added: " + json.dumps(r.model_dump(), indent=2))
    for i, r in enumerate(rules):
        print(f"  {i}. {r.name}  →  {r.destination}")


def cmd_serve(args) -> None:
    import uvicorn
    from .api import app
    from .service import Guardian
    from . import devices
    if not args.no_guardian:
        Guardian().start()
    # Listen on the home Wi-Fi only when a phone is (or is being) paired.
    lan = args.lan or devices.any_paired()
    app.state.lan, app.state.port = lan, args.port
    url = f"http://127.0.0.1:{args.port}"
    print(f"DriveMind dashboard: {url}")
    if lan:
        print(f"Phone sync on: http://{devices.lan_ip()}:{args.port}  (only paired phones can connect)")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(app, host="0.0.0.0" if lan else "127.0.0.1", port=args.port, log_level="warning")


def cmd_chat(args) -> None:
    from .chat import answer
    if args.question:
        r = answer(" ".join(args.question))
        print(r["answer"])
        for i, src in enumerate(r["sources"], 1):
            print(c(f"  [{i}] {src['path']}", "2"))
        return
    history = []
    print("DriveMind assistant — ask about space, cleaning, finding files, duplicates, disk health. Ctrl+C to quit.")
    try:
        while True:
            q = input(c("\nyou> ", "36")).strip()
            if not q:
                continue
            r = answer(q, history)
            print(r["answer"])
            for i, src in enumerate(r["sources"], 1):
                print(c(f"  [{i}] {src['path']}", "2"))
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": r["answer"]}]
    except (KeyboardInterrupt, EOFError):
        print()


def cmd_mcp(args) -> None:
    try:
        from .mcp_server import main as run
    except ImportError:
        sys.exit('The MCP server needs:  pip install "drivemind[mcp]"')
    run()


def cmd_tray(args) -> None:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        sys.exit('The tray needs extra packages:  pip install "drivemind[tray]"')
    except Exception as e:  # e.g. no desktop session to show a tray in
        sys.exit(f"Cannot show a tray icon here ({type(e).__name__}). Use `drivemind serve` instead.")
    from .tray import TrayApp
    TrayApp(port=args.port).run()


def cmd_watch(args) -> None:
    from .service import Guardian
    g = Guardian(interval_s=args.interval)
    print("Guardian running. Ctrl+C to stop.")
    try:
        while True:
            g.tick()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


def cmd_archive(args) -> None:
    from .archiver import plan_archive
    from .paths import user_folders
    s = Settings.load()
    roots = [Path(r) for r in args.roots] if args.roots else [
        p for p in (user_folders()["Desktop"], user_folders()["Documents"], Path.home() / "Projects",
                    Path.home() / "source") if p.exists()]
    _apply_or_save(plan_archive(s, roots, Path(args.to) if args.to else None), args)


def cmd_index(args) -> None:
    from .search import build_index, default_roots
    roots = [Path(r) for r in args.roots] if args.roots else default_roots()
    r = build_index(roots)
    print(f"Indexed: {r['added']} new, {r['updated']} changed, {r['removed']} removed — "
          f"{r['total']:,} files searchable ({r['seconds']}s)")


def cmd_search(args) -> None:
    from .search import search
    hits = search(" ".join(args.query), args.limit)
    if not hits:
        print("Nothing found. Run `drivemind index` first if you have not yet.")
    for h in hits:
        when = time.strftime("%Y-%m-%d", time.localtime(h["mtime"]))
        print(f"  {when}  {human(h['size']):>9}  {h['path']}")
        if h["snippet"]:
            print(c(f"{'':24}{h['snippet'][:110]}", "2"))


def cmd_ssd(args) -> None:
    from .ssd import disk_health
    disks = disk_health()
    if not disks:
        print("Disk health is read from Windows; nothing reported here.")
    for d in disks:
        color = {"good": "32", "watch": "33", "critical": "31"}[d["status"]]
        print(f"{d['name']} ({d['media']} {d['bus']}, {d['size_gb']} GB): {c(d['status'], color)}")
        for n in d["notes"]:
            print(f"   - {n}")


def cmd_report(args) -> None:
    from .insights import weekly, weekly_text
    r = weekly(args.days)
    print(weekly_text(r))
    print(f"  freed: {human(r['freed_bytes'])} · organized: {r['moved_files']} files · plans applied: {r['plans_applied']}")
    for t in r["top_categories"]:
        print(f"  {t['files']:>4} files → {t['name']}")


def cmd_large(args) -> None:
    from .insights import large_files
    roots = [Path(p) for p in args.roots] or None
    if roots is None:
        from .paths import user_folders
        roots = [p for p in user_folders().values() if p.exists()]
    rows = large_files(roots, args.min_mb * 1024 * 1024, args.limit)
    if not rows:
        print(f"No files over {args.min_mb} MB in {', '.join(str(r) for r in roots)}.")
    for f in rows:
        when = time.strftime("%Y-%m-%d", time.localtime(f["last_used"]))
        print(f"{human(f['size']):>10}  last used {when}  {f['path']}")
    if rows:
        print("\nTo let some go (to quarantine, 30 days to undo), pick them on the dashboard's Large files page.")


def cmd_devdata(args) -> None:
    from .devdata import report
    rows = report()
    if not rows:
        print("No WSL, Docker, Android, Gradle, Ollama or Steam data found on this PC.")
    for r in rows:
        print(c(f"\n{r['name']}: {human(r['size'])}", "1"))
        for p in r["paths"]:
            print(f"   {p}")
        for i, step in enumerate(r["steps"], 1):
            print(f"   {i}. {step}")
        if r.get("compact"):
            print(c(f"   Shrink it: {r['compact']['how']}", "2"))


def cmd_tag_temp(args) -> None:
    from .cleaner import tag_temporary
    exp = tag_temporary(Path(args.path), args.days)
    print(f"{args.path} is temporary until {time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))}. "
          "DriveMind will ask once, then move it to quarantine.")


def cmd_pair(args) -> None:
    from . import devices
    r = devices.pair(args.name, args.port)
    print("Open the DriveMind app on your phone > Pair > Enter code, and type:\n")
    print(f"    {r['code']}\n")
    print("Then restart `drivemind serve` (it now listens on your Wi-Fi for paired phones).")
    print("Windows may ask to allow Python through the firewall: choose Private networks.")


def cmd_shell(args) -> None:
    from . import winshell
    if args.action == "install":
        for label in winshell.install_menu():
            print(f"  added: {label}")
        print("Right-click any folder in Explorer > DriveMind (Windows 11: Show more options).")
    elif args.action == "uninstall":
        winshell.uninstall_menu()
        print("Explorer menu removed.")
    elif args.action in ("autostart-on", "autostart-off"):
        winshell.set_autostart(args.action == "autostart-on")
        print("DriveMind " + ("starts with Windows." if args.action == "autostart-on" else "no longer starts with Windows."))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="drivemind", description="AI Drive Guardian for Windows")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("scan")
    p.add_argument("path")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("organize")
    p.add_argument("source")
    p.add_argument("--root")
    p.add_argument("--preset", default="developer",
                   choices=["developer", "student", "freelancer", "by_type", "minimal", "johnny_decimal"])
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true", help="apply automatic actions now")
    p.add_argument("--yes-all", action="store_true", help="with --apply: also approve every waiting action")
    p.set_defaults(fn=cmd_organize)

    p = sub.add_parser("clean")
    p.add_argument("what", choices=["caches", "temp", "dev", "dupes"])
    p.add_argument("--only", nargs="*", help="cache ids, e.g. browser pip npm")
    p.add_argument("--roots", nargs="*")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes-all", action="store_true")
    p.set_defaults(fn=cmd_clean)

    sub.add_parser("caches").set_defaults(fn=cmd_caches)
    p = sub.add_parser("plans")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(fn=cmd_plans)
    p = sub.add_parser("show")
    p.add_argument("plan")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("approve")
    p.add_argument("plan")
    p.add_argument("ids", nargs="*")
    p.add_argument("--reject", action="store_true")
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("apply")
    p.add_argument("plan")
    p.add_argument("ids", nargs="*")
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("undo")
    p.add_argument("plan")
    p.set_defaults(fn=cmd_undo)
    p = sub.add_parser("where")
    p.add_argument("query")
    p.set_defaults(fn=cmd_where)
    p = sub.add_parser("explain")
    p.add_argument("path")
    p.add_argument("--no-ai", action="store_true")
    p.set_defaults(fn=cmd_explain)
    p = sub.add_parser("mode")
    p.add_argument("mode", choices=["safe", "balanced", "autopilot"])
    p.set_defaults(fn=cmd_mode)
    p = sub.add_parser("set", help="set OPTION, cache.ID or temp.ID to yes/ask/no")
    p.add_argument("option")
    p.add_argument("value", choices=["yes", "ask", "no"])
    p.set_defaults(fn=cmd_set)
    sub.add_parser("settings").set_defaults(fn=cmd_settings)
    p = sub.add_parser("root", help="set the organize root folder")
    p.add_argument("path")
    p.set_defaults(fn=lambda a: (lambda s: (setattr(s, "organize_root", str(Path(a.path).resolve())), s.save(),
                                            print(f"Organize root: {s.organize_root}")))(Settings.load()))
    p = sub.add_parser("rule")
    p.add_argument("text", nargs="*")
    p.set_defaults(fn=cmd_rule)
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=7878)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-guardian", action="store_true")
    p.add_argument("--lan", action="store_true", help="accept paired phones on the home Wi-Fi")
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("pair", help="pair an Android phone (prints a code; the dashboard shows a QR)")
    p.add_argument("--name", default="Android phone")
    p.add_argument("--port", type=int, default=7878)
    p.set_defaults(fn=cmd_pair)
    p = sub.add_parser("archive", help="zip projects idle for months (git-safe)")
    p.add_argument("--roots", nargs="*")
    p.add_argument("--to", help="archive folder")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes-all", action="store_true")
    p.set_defaults(fn=cmd_archive)
    p = sub.add_parser("index", help="build the search index of your files")
    p.add_argument("--roots", nargs="*")
    p.set_defaults(fn=cmd_index)
    p = sub.add_parser("search", help="find files by content, type and date")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_search)
    sub.add_parser("ssd", help="SSD / disk health").set_defaults(fn=cmd_ssd)
    sp = sub.add_parser("report", help="what DriveMind did this week")
    sp.add_argument("--days", type=int, default=7)
    sp.set_defaults(fn=cmd_report)
    sp = sub.add_parser("large", help="the biggest files in your folders")
    sp.add_argument("roots", nargs="*", help="folders to look in (default: your user folders)")
    sp.add_argument("--min-mb", type=int, default=500)
    sp.add_argument("--limit", type=int, default=30)
    sp.set_defaults(fn=cmd_large)
    sub.add_parser("devdata", help="WSL, Docker, Android SDK ... sizes and how to move them").set_defaults(fn=cmd_devdata)
    p = sub.add_parser("tag-temp", help="mark a file or folder as temporary")
    p.add_argument("path")
    p.add_argument("--days", type=float, default=7)
    p.set_defaults(fn=cmd_tag_temp)
    p = sub.add_parser("shell", help="Windows: Explorer right-click menu and autostart")
    p.add_argument("action", choices=["install", "uninstall", "autostart-on", "autostart-off"])
    p.set_defaults(fn=cmd_shell)
    p = sub.add_parser("chat", help="ask the DriveMind assistant (RAG over your files)")
    p.add_argument("question", nargs="*")
    p.set_defaults(fn=cmd_chat)
    sub.add_parser("mcp", help="run as an MCP server for Claude Code / Codex / Cursor (stdio)").set_defaults(fn=cmd_mcp)
    p = sub.add_parser("tray", help="run in the system tray (dashboard, phone sync, guardian)")
    p.add_argument("--port", type=int, default=7878)
    p.set_defaults(fn=cmd_tray)
    p = sub.add_parser("watch")
    p.add_argument("--interval", type=float, default=300)
    p.set_defaults(fn=cmd_watch)
    return ap


def main(argv: Optional[List[str]] = None) -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
