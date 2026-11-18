"use strict";
// Tiny SVG chart kit for DriveMind: donut, area, bars, treemap. No dependencies, works offline,
// follows the light/dark theme through CSS variables, animates unless reduced motion is on.

const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const PALETTE = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6", "--c7", "--c8"];
  const reduce = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const col = (i) => `var(${PALETTE[i % PALETTE.length]})`;
  const fmt = (n) => (typeof human === "function" ? human(n) : String(n));
  const escH = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }

  // one shared tooltip
  let tip;
  function tooltip(html, evt) {
    if (!tip) { tip = document.createElement("div"); tip.className = "chart-tip"; document.body.appendChild(tip); }
    if (!html) { tip.style.opacity = 0; return; }
    tip.innerHTML = html;
    const x = Math.min(evt.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const y = Math.min(evt.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
    tip.style.transform = `translate(${x}px, ${y}px)`;
    tip.style.opacity = 1;
  }
  const hover = (node, html) => {
    node.addEventListener("pointermove", (e) => tooltip(html, e));
    node.addEventListener("pointerleave", () => tooltip(null));
  };

  /** Donut with a legend. data: [{name, size, count?}] */
  function donut(host, data, { label = "", value = "" } = {}) {
    host.innerHTML = "";
    const total = data.reduce((a, d) => a + d.size, 0) || 1;
    const top = data.slice(0, 7);
    const rest = data.slice(7).reduce((a, d) => a + d.size, 0);
    if (rest) top.push({ name: "Other types", size: rest });
    const wrap = document.createElement("div"); wrap.className = "donut-wrap"; host.appendChild(wrap);
    const svg = el("svg", { viewBox: "0 0 120 120", class: "donut", role: "img", "aria-label": label }, wrap);
    const r = 46, C = 2 * Math.PI * r;
    el("circle", { cx: 60, cy: 60, r, fill: "none", stroke: "var(--line)", "stroke-width": 14 }, svg);
    let acc = 0;
    top.forEach((d, i) => {
      const frac = d.size / total;
      const seg = el("circle", {
        cx: 60, cy: 60, r, fill: "none", stroke: col(i), "stroke-width": 14,
        "stroke-dasharray": `0 ${C}`, transform: `rotate(${-90 + acc * 360} 60 60)`, class: "seg",
      }, svg);
      const target = `${Math.max(0, frac * C - 1.2)} ${C}`;
      if (reduce()) seg.setAttribute("stroke-dasharray", target);
      else requestAnimationFrame(() => setTimeout(() => seg.setAttribute("stroke-dasharray", target), 30 + i * 60));
      hover(seg, `<b>${escH(d.name)}</b><br>${fmt(d.size)} · ${(frac * 100).toFixed(1)}%${d.count ? ` · ${d.count.toLocaleString()} files` : ""}`);
      acc += frac;
    });
    el("text", { x: 60, y: 58, "text-anchor": "middle", class: "donut-value" }, svg).textContent = value || fmt(total);
    el("text", { x: 60, y: 74, "text-anchor": "middle", class: "donut-label" }, svg).textContent = label;
    const legend = document.createElement("ul"); legend.className = "legend"; wrap.appendChild(legend);
    legend.innerHTML = top.map((d, i) => `<li><i style="background:${col(i)}"></i><span>${escH(d.name)}</span><b>${fmt(d.size)}</b></li>`).join("");
  }

  /** Area chart of used space over time. points: [{ts, used, free, total}] */
  function area(host, points, { height = 180 } = {}) {
    host.innerHTML = "";
    if (points.length < 2) {
      host.innerHTML = `<p class="muted empty-chart">DriveMind records free space every hour. The chart appears after a few readings.</p>`;
      return;
    }
    const W = Math.max(320, host.clientWidth || 600), H = height, P = { l: 48, r: 12, t: 12, b: 24 };
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "area", role: "img", "aria-label": "Used space over time" }, host);
    const xs = points.map((p) => p.ts), ys = points.map((p) => p.used);
    const cap = Math.max(...points.map((p) => p.used + p.free));
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const ymin = Math.max(0, Math.min(...ys) * 0.96), ymax = Math.min(cap, Math.max(...ys) * 1.02) || 1;
    const X = (t) => P.l + ((t - x0) / (x1 - x0 || 1)) * (W - P.l - P.r);
    const Y = (v) => H - P.b - ((v - ymin) / (ymax - ymin || 1)) * (H - P.t - P.b);
    for (let i = 0; i <= 3; i++) {
      const v = ymin + ((ymax - ymin) * i) / 3, y = Y(v);
      el("line", { x1: P.l, x2: W - P.r, y1: y, y2: y, class: "grid" }, svg);
      el("text", { x: P.l - 6, y: y + 4, "text-anchor": "end", class: "axis" }, svg).textContent = fmt(v);
    }
    const fmtD = (t) => new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    [x0, (x0 + x1) / 2, x1].forEach((t, i) => {
      el("text", { x: X(t), y: H - 6, "text-anchor": ["start", "middle", "end"][i], class: "axis" }, svg).textContent = fmtD(t);
    });
    const line = points.map((p, i) => `${i ? "L" : "M"}${X(p.ts).toFixed(1)},${Y(p.used).toFixed(1)}`).join("");
    const defs = el("defs", {}, svg);
    const g = el("linearGradient", { id: "areaFill", x1: 0, x2: 0, y1: 0, y2: 1 }, defs);
    el("stop", { offset: "0%", "stop-color": "var(--accent)", "stop-opacity": 0.35 }, g);
    el("stop", { offset: "100%", "stop-color": "var(--accent)", "stop-opacity": 0 }, g);
    const clip = el("clipPath", { id: "areaClip" }, defs);
    const clipRect = el("rect", { x: 0, y: 0, width: reduce() ? W : 0, height: H }, clip);
    const grp = el("g", { "clip-path": "url(#areaClip)" }, svg);
    el("path", { d: `${line}L${X(x1)},${H - P.b}L${X(x0)},${H - P.b}Z`, fill: "url(#areaFill)" }, grp);
    el("path", { d: line, class: "area-line" }, grp);
    if (!reduce()) {
      const t0 = performance.now();
      const step = (t) => { const k = Math.min(1, Math.max(0, (t - t0) / 700)); clipRect.setAttribute("width", W * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    }
    // hover guide
    const guide = el("line", { y1: P.t, y2: H - P.b, class: "guide", opacity: 0 }, svg);
    const dot = el("circle", { r: 4, class: "dot", opacity: 0 }, svg);
    const hit = el("rect", { x: P.l, y: 0, width: W - P.l - P.r, height: H, fill: "transparent" }, svg);
    hit.addEventListener("pointermove", (e) => {
      const box = svg.getBoundingClientRect();
      const t = x0 + ((e.clientX - box.left) * (W / box.width) - P.l) / (W - P.l - P.r) * (x1 - x0);
      const p = points.reduce((a, b) => (Math.abs(b.ts - t) < Math.abs(a.ts - t) ? b : a));
      guide.setAttribute("x1", X(p.ts)); guide.setAttribute("x2", X(p.ts)); guide.setAttribute("opacity", 1);
      dot.setAttribute("cx", X(p.ts)); dot.setAttribute("cy", Y(p.used)); dot.setAttribute("opacity", 1);
      tooltip(`<b>${new Date(p.ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</b><br>${fmt(p.used)} used · ${fmt(p.free)} free`, e);
    });
    hit.addEventListener("pointerleave", () => { guide.setAttribute("opacity", 0); dot.setAttribute("opacity", 0); tooltip(null); });
  }

  /** Horizontal bars. data: [{name, size, count}] by: "size" | "count" */
  function bars(host, data, { by = "size", colorIndex = 0 } = {}) {
    host.innerHTML = "";
    const max = Math.max(1, ...data.map((d) => d[by]));
    const list = document.createElement("div"); list.className = "hbars"; host.appendChild(list);
    data.forEach((d, i) => {
      const row = document.createElement("div"); row.className = "hbar";
      const pct = (100 * d[by]) / max;
      row.innerHTML = `<span class="hbar-name">${escH(d.name)}</span><span class="hbar-track"><span class="hbar-fill" style="background:${col(colorIndex + i)};width:${reduce() ? pct : 0}%"></span></span>
        <span class="hbar-val">${by === "size" ? fmt(d.size) : d.count.toLocaleString()}</span>`;
      list.appendChild(row);
      if (!reduce()) requestAnimationFrame(() => setTimeout(() => (row.querySelector(".hbar-fill").style.width = pct + "%"), 40 + i * 50));
      hover(row, `<b>${escH(d.name)}</b><br>${fmt(d.size)} · ${(d.count || 0).toLocaleString()} files`);
    });
  }

  /** Squarified treemap (Bruls et al.). items: [{name, path, size, children?}] */
  function squarify(items, x, y, w, h) {
    const out = [];
    const total = items.reduce((a, d) => a + d.size, 0);
    if (!total || w <= 0 || h <= 0) return out;
    const scale = (w * h) / total;
    let rest = items.map((d) => ({ ...d, area: d.size * scale })).filter((d) => d.area > 0);
    while (rest.length) {
      const short = Math.min(w, h);
      let row = [rest[0]], best = worst(row, short), i = 1;
      while (i < rest.length) {
        const next = [...row, rest[i]], ws = worst(next, short);
        if (ws > best) break;
        row = next; best = ws; i++;
      }
      const sum = row.reduce((a, d) => a + d.area, 0);
      if (w >= h) {
        const cw = sum / h; let cy = y;
        row.forEach((d) => { const ch = d.area / cw; out.push({ ...d, x, y: cy, w: cw, h: ch }); cy += ch; });
        x += cw; w -= cw;
      } else {
        const ch = sum / w; let cx = x;
        row.forEach((d) => { const cw = d.area / ch; out.push({ ...d, x: cx, y, w: cw, h: ch }); cx += cw; });
        y += ch; h -= ch;
      }
      rest = rest.slice(row.length);
    }
    return out;
    function worst(r, s) {
      const sum = r.reduce((a, d) => a + d.area, 0), mx = Math.max(...r.map((d) => d.area)), mn = Math.min(...r.map((d) => d.area));
      return Math.max((s * s * mx) / (sum * sum), (sum * sum) / (s * s * mn));
    }
  }

  function treemap(host, tree, { onPick } = {}) {
    host.innerHTML = "";
    if (!tree.length) { host.innerHTML = `<p class="muted empty-chart">Scan a drive or folder to see what fills it.</p>`; return; }
    const W = host.clientWidth || 800, H = Math.max(260, Math.min(420, W * 0.45));
    const box = document.createElement("div"); box.className = "treemap"; box.style.height = H + "px"; host.appendChild(box);
    const total = tree.reduce((a, d) => a + d.size, 0);
    squarify([...tree].sort((a, b) => b.size - a.size), 0, 0, W, H).forEach((t, i) => {
      const cell = document.createElement("div");
      cell.className = "tm-cell";
      Object.assign(cell.style, { left: t.x + "px", top: t.y + "px", width: t.w + "px", height: t.h + "px", animationDelay: reduce() ? "0s" : `${i * 35}ms` });
      cell.style.setProperty("--tm", col(i));
      const big = t.w > 90 && t.h > 46;
      cell.innerHTML = big ? `<b>${escH(t.name)}</b><span>${fmt(t.size)}</span>` : "";
      // children as faint inner blocks
      if (big && t.children && t.children.length && t.w > 120 && t.h > 110) {
        const inner = squarify([...t.children].sort((a, b) => b.size - a.size), 7, 46, t.w - 18, t.h - 54);
        inner.forEach((c) => {
          const sub = document.createElement("div"); sub.className = "tm-sub";
          Object.assign(sub.style, { left: c.x + "px", top: c.y + "px", width: Math.max(0, c.w - 2) + "px", height: Math.max(0, c.h - 2) + "px" });
          if (c.w > 70 && c.h > 22) sub.textContent = c.name;
          hover(sub, `<b>${escH(c.name)}</b><br>${fmt(c.size)}<br><span class="tip-path">${escH(c.path)}</span>`);
          sub.addEventListener("click", (e) => { e.stopPropagation(); onPick && onPick(c); });
          cell.appendChild(sub);
        });
      }
      hover(cell, `<b>${escH(t.name)}</b><br>${fmt(t.size)} · ${((t.size / total) * 100).toFixed(1)}%<br><span class="tip-path">${escH(t.path)}</span>`);
      cell.addEventListener("click", () => onPick && onPick(t));
      box.appendChild(cell);
    });
  }

  /** Count a number up smoothly into an element. */
  function countUp(node, to, format = (v) => Math.round(v).toLocaleString(), ms = 700) {
    const from = Number(node.dataset.v || 0);
    node.dataset.v = to;
    if (reduce() || from === to) { node.textContent = format(to); return; }
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, Math.max(0, (t - t0) / ms)), e = 1 - Math.pow(1 - k, 3);
      node.textContent = format(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  return { donut, area, bars, treemap, countUp, tooltip };
})();
