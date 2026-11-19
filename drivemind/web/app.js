"use strict";
// DriveMind dashboard. Every file name is escaped before it reaches the page.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function human(n) {
  if (n == null) return "–";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; n = Number(n);
  while (Math.abs(n) >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${u[i]}`;
}
const pct = (v) => `${Math.round(v * 100)}%`;
const when = (ts) => new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

async function api(path, method = "GET", body) {
  const opt = { method, headers: { "X-DriveMind": "1" } };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast on" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = "toast"), 3800);
}

async function busy(btn, fn) {
  const label = btn.textContent; btn.disabled = true; btn.textContent = "Working…";
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.disabled = false; btn.textContent = label; }
}

// ------------------------------------------------------------- navigation --
const loaders = {};
function show(view) {
  $$("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.view === view));
  $$(".page").forEach((p) => p.classList.toggle("on", p.dataset.page === view));
  if (!$(`[data-page="${view}"]`)) view = "home";
  history.replaceState(null, "", "#" + view);
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  loaders[view]?.();
}
$$("#nav a").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); show(a.dataset.view); }));
window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (v && $(`[data-page="${v}"]`)) show(v); });

// ---------------------------------------------------------- shared pieces --
function seg(current, onPick, disabled = false) {
  const wrap = document.createElement("div"); wrap.className = "seg";
  for (const v of ["yes", "ask", "no"]) {
    const b = document.createElement("button");
    b.textContent = v[0].toUpperCase() + v.slice(1); b.className = v + (v === current ? " on" : "");
    b.disabled = disabled; b.setAttribute("aria-pressed", v === current);
    b.onclick = async () => {
      try { await onPick(v); $$("button", wrap).forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); }); }
      catch (e) { toast(e.message, true); }
    };
    wrap.appendChild(b);
  }
  return wrap;
}

// ------------------------------------------------------------------ theme --
// System follows Windows (prefers-color-scheme); Light and Dark pin it. Remembered per browser.
const ICONS = {
  system: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor"/></svg>',
  light: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.2" fill="currentColor"/><g stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3 3l1.1 1.1M11.9 11.9 13 13M3 13l1.1-1.1M11.9 4.1 13 3"/></g></svg>',
  dark: '<svg viewBox="0 0 16 16"><path d="M13.5 10.2A6 6 0 0 1 5.8 2.5a6 6 0 1 0 7.7 7.7z" fill="currentColor"/></svg>',
};
$$(".t-ico").forEach((n) => (n.innerHTML = ICONS[n.dataset.ico]));
function applyTheme(t) {
  if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  $$("#theme-seg button").forEach((b) => b.setAttribute("aria-checked", b.dataset.theme === t));
  try { localStorage.setItem("dm-theme", t); } catch (e) { /* storage blocked: theme still applies for this visit */ }
  if (lastScan !== undefined) renderShelf();
}
let theme = "system";
try { theme = localStorage.getItem("dm-theme") || "system"; } catch (e) {}
$$("#theme-seg button").forEach((b) => (b.onclick = () => { theme = b.dataset.theme; applyTheme(theme); }));
$("#theme-seg").addEventListener("keydown", (e) => {  // arrow keys move between the three, like any radio group
  const order = ["system", "light", "dark"], i = order.indexOf(theme);
  const n = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
  if (!n) return;
  e.preventDefault(); theme = order[(i + n + 3) % 3]; applyTheme(theme); $(`#theme-seg [data-theme="${theme}"]`).focus();
});

// -------------------------------------------------------------- plan view --
const sepOf = (p) => (p.includes("\\") ? "\\" : "/");
function commonDir(paths) {
  if (!paths.length) return "";
  const sep = sepOf(paths[0]);
  const parts = paths.map((p) => p.split(sep).slice(0, -1));
  let i = 0;
  while (parts.every((x) => x[i] !== undefined && x[i] === parts[0][i])) i++;
  return parts[0].slice(0, i).join(sep);
}
const rel = (p, base) => (base && p.startsWith(base) ? p.slice(base.length).replace(/^[\\/]/, "") : p);
const plans = {}; // plan id -> plan
function renderPlan(target, plan) {
  plans[plan.id] = plan;
  const el = typeof target === "string" ? $(target) : target;
  const s = plan.summary;
  const pending = plan.actions.filter((a) => a.status === "pending" || a.status === "approved");
  const srcBase = commonDir(plan.actions.map((a) => a.src));
  const dstBase = commonDir(plan.actions.filter((a) => a.dst && !a.dst.includes("quarantine")).map((a) => a.dst));
  const rows = plan.actions.map((a) => {
    const sel = a.status === "pending" || a.status === "approved";
    const tag = a.status === "pending" ? (a.decision === "yes" ? "auto" : "ask") : a.status;
    const cls = a.status === "pending" ? (a.decision === "yes" ? "yes" : "ask") : a.status;
    const conf = a.confidence < 0.8 ? "conf low" : "conf";
    const dst = a.dst ? `<span class="arrow">→</span><span class="to" title="${esc(a.dst)}">${esc(rel(a.dst, dstBase))}</span>` : "";
    const from = `<span class="from path" title="${esc(a.src)}">${esc(rel(a.src, srcBase))}</span>`;
    return `<tr class="act${a.status === "skipped" || a.status === "rejected" ? " dim" : ""}"><td>${sel ? `<input type="checkbox" data-id="${esc(a.id)}" ${a.status === "approved" || a.decision === "yes" ? "checked" : ""} aria-label="select">` : ""}</td>
      <td><div class="move">${from}${dst}</div><div class="desc">${esc(a.reason)}${a.error ? ` — <span style="color:var(--bad)">${esc(a.error)}</span>` : ""}</div></td>
      <td><span class="pill">${esc(a.category || a.op)}</span></td>
      <td class="${conf}">${pct(a.confidence)}</td><td class="num">${human(a.size)}</td>
      <td><span class="pill ${cls}">${esc(tag)}</span></td></tr>`;
  }).join("");
  el.innerHTML = `<div class="card plan">
    <div class="row-head"><h2>${esc(plan.title)}</h2><span class="pill">${esc(plan.status)}</span></div>
    ${srcBase ? `<p class="where">From ${esc(srcBase)}${dstBase ? ` → into ${esc(dstBase)}` : ""}</p>` : ""}
    ${plan.notes.map((n) => `<p class="note">${esc(n)}</p>`).join("")}
    <div class="stats"><span class="pill">${s.actions} actions</span><span class="pill yes">${s.auto} automatic</span>
      <span class="pill ask">${s.waiting} waiting for you</span>${s.frees_bytes ? `<span class="pill">frees ${human(s.frees_bytes)}</span>` : `<span class="pill">${human(s.bytes)} involved</span>`}</div>
    ${plan.actions.length ? `<table class="tbl"><thead><tr><th><input type="checkbox" class="all" aria-label="select all"></th><th>Change</th><th>Group</th><th>Sure</th><th>Size</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`
      : `<p class="empty">Nothing to do — this is already tidy.</p>`}
    <div class="actions-bar">
      ${pending.length ? `<button class="btn" data-do="apply">Apply selected</button><button class="btn ghost" data-do="reject">Reject selected</button>` : ""}
      ${plan.status === "applied" ? `<button class="btn danger" data-do="undo">Undo this plan</button>` : ""}
    </div></div>`;
  $(".all", el)?.addEventListener("change", (e) => $$("input[data-id]", el).forEach((c) => (c.checked = e.target.checked)));
  const picked = () => $$("input[data-id]:checked", el).map((c) => c.dataset.id);
  $$("[data-do]", el).forEach((b) => b.addEventListener("click", () => busy(b, async () => {
    if (b.dataset.do === "undo") {
      const r = await api(`/api/plans/${plan.id}/undo`, "POST");
      toast(`Restored ${r.result.restored} items`); renderPlan(el, r.plan); return;
    }
    const ids = picked();
    if (!ids.length) return toast("Select at least one change");
    if (b.dataset.do === "reject") {
      renderPlan(el, await api(`/api/plans/${plan.id}/decide`, "POST", { reject: ids })); toast("Rejected — DriveMind will learn from this"); return;
    }
    await api(`/api/plans/${plan.id}/decide`, "POST", { approve: ids });
    const r = await api(`/api/plans/${plan.id}/apply`, "POST", { ids });
    toast(`${r.result.done} done${r.result.failed ? `, ${r.result.failed} failed` : ""}${r.result.freed_bytes ? `, freed ${human(r.result.freed_bytes)}` : ""}`);
    renderPlan(el, r.plan);
  })));
}

// --------------------------------------------------------------- overview --
let status = null, lastScan = null, histDays = 30;

// The drive drawn as a shelf: each segment is real bytes / capacity. File types come from the last
// scan when it covered this drive; whatever the scan did not see is "Other used". Free space is hatched.
function renderShelf() {
  const sys = status && (status.drives.find((d) => d.drive === status.system_drive) || status.drives[0]);
  if (!sys) return;
  const cap = sys.used + sys.free;
  const sameDrive = lastScan && lastScan.root && lastScan.root.toLowerCase().startsWith(sys.drive.toLowerCase());
  // a file type gets its own block only if it is at least 0.5% of the drive; smaller ones count as "Other used"
  const types = sameDrive ? (lastScan.categories || []).filter((c) => c.size >= cap * 0.005).slice(0, 6) : [];
  const typed = types.reduce((a, c) => a + c.size, 0);
  const segs = types.map((c, i) => ({ name: c.name, size: c.size, cls: `c${(i % 8) + 1}` }));
  if (sys.used - typed > 0) segs.push({ name: types.length ? "Other used" : "Used", size: sys.used - typed, cls: "used" });
  segs.push({ name: "Free", size: sys.free, cls: "free" });
  $("#shelf-drive").textContent = sys.drive;
  $("#shelf-bar").className = `shelf-bar ${sys.status}`;
  $("#shelf-bar").setAttribute("aria-label", segs.map((g) => `${g.name} ${human(g.size)}`).join(", "));
  $("#shelf-bar").innerHTML = segs.map((g) =>
    `<i class="seg-${g.cls}" style="flex-grow:${Math.max(g.size / cap, 0.004).toFixed(5)}" title="${esc(g.name)}: ${human(g.size)}"></i>`).join("");
  $("#shelf-legend").innerHTML = segs.map((g) =>
    `<li><i class="seg-${g.cls}" aria-hidden="true"></i>${esc(g.name)} <b>${human(g.size)}</b></li>`).join("") +
    (sameDrive ? "" : `<li class="muted">Scan ${esc(sys.drive)} below to split this by file type.</li>`);
}
const fullIn = (d) => !d.days_to_full ? (d.trend === "learning" ? "Learning" : "Not filling")
  : d.days_to_full > 365 ? "Over a year" : d.days_to_full > 60 ? `~${Math.round(d.days_to_full / 30)} months` : `~${Math.round(d.days_to_full)} days`;

async function refreshStatus() {
  status = await api("/api/status");
  $("#ver").textContent = "v" + status.version;
  $("#mode-pill").textContent = status.mode;
  const sys = status.drives.find((d) => d.drive === status.system_drive) || status.drives[0];
  if (!$("#scan-root").value) $("#scan-root").value = sys?.drive || "/";
  if (sys) {
    const msg = { good: "Plenty of room.", watch: "Getting full — worth a clean.", critical: "Almost full — fix this now." }[sys.status];
    $("#home-sub").textContent = `${sys.drive} has ${human(sys.free)} free. ${msg}`;
    Charts.countUp($("#k-free"), sys.free, (v) => human(v));
    $("#k-free-sub").textContent = `free of ${human(sys.used + sys.free)}`;
    Charts.countUp($("#k-health"), sys.score, (v) => `${Math.round(v)}/100`);
    $("#k-health-sub").innerHTML = `<span class="pill ${sys.status === "good" ? "yes" : "ask"}">${esc(sys.status)}</span>`;
    $("#k-full").textContent = fullIn(sys);
    $("#k-full-sub").textContent = sys.days_to_full ? "at the current rate" : sys.trend === "learning" ? "needs a few days of history" : "usage is steady";
    renderShelf();
  }
  $("#drives").innerHTML = status.drives.map((d) => `<div class="drive"><b>${esc(d.drive)}</b>
    <div class="bar ${d.status}"><i style="width:${100 - d.free_percent}%"></i></div>
    <span class="muted">${human(d.free)} free of ${human(d.used + d.free)}</span></div>`).join("");
  const waiting = (await api("/api/plans")).filter((p) => p.status === "proposed").reduce((a, p) => a + p.summary.waiting, 0);
  Charts.countUp($("#k-wait"), waiting);
}

async function loadHistory() {
  const h = await api(`/api/history?days=${histDays}`);
  Charts.area($("#area"), h.points);
}
$$("#range button").forEach((b) => b.onclick = () => {
  $$("#range button").forEach((x) => x.classList.toggle("on", x === b)); histDays = Number(b.dataset.days); loadHistory();
});

loaders.home = async () => {
  try { await refreshStatus(); } catch (e) { toast(e.message, true); }
  loadHistory().catch(() => {});
  loadNotices();
  api("/api/advice").then((a) => {
    $("#tips").innerHTML = a.tips.length ? a.tips.map((t) => `<div class="tip"><b>${esc(t.title)}</b><p>${esc(t.detail)}</p>
      <button class="btn sm" data-tip="${esc(t.action)}">Fix</button></div>`).join("")
      : (status?.drives?.find((d) => d.drive === status.system_drive)?.status || "good") === "good"
        ? `<p class="muted">No big wins right now. Your drive is in good shape.</p>`
        : `<p class="muted">No single cache or project is the culprit. Scan the drive to see which folders take the space.</p>`;
    $$("[data-tip]").forEach((b) => b.onclick = () => show({ clean_caches: "caches", clean_dev_junk: "more", move_user_folders: "folders" }[b.dataset.tip] || "home"));
  }).catch(() => ($("#tips").innerHTML = `<p class="muted">Could not build tips.</p>`));
  api("/api/scan/latest").then((s) => (s.root ? renderScan(s) : renderScan(null)));
  loadWeek().catch(() => ($("#week").innerHTML = `<p class="muted">Could not load the weekly report.</p>`));
  api("/api/ssd").then((disks) => {
    $("#ssd").innerHTML = disks.length ? `<div class="list">${disks.map((d) => `<div class="li"><div><b>${esc(d.name)}</b>
      <div class="meta">${esc([d.media, d.bus, d.size_gb ? d.size_gb + " GB" : ""].filter(Boolean).join(" · "))}</div>
      <div class="meta">${esc(d.notes.join(" · "))}</div></div><span class="pill ${d.status === "good" ? "yes" : "ask"}">${esc(d.status)}</span></div>`).join("")}</div>`
      : `<p class="muted">Disk health counters are read from Windows. None were reported here.</p>`;
  }).catch(() => ($("#ssd").innerHTML = `<p class="muted">Could not read disk health.</p>`));
};

// ------------------------------------------------------------- this week --
async function loadWeek() {
  const w = await api("/api/report/weekly");
  const growth = w.growth_bytes == null ? "–" : `${w.growth_bytes >= 0 ? "+" : "−"}${human(Math.abs(w.growth_bytes))}`;
  $("#week").innerHTML = [
    ["freed", human(w.freed_bytes)], ["files organized", w.moved_files.toLocaleString()],
    ["plans applied", w.plans_applied], ["drive change", growth],
  ].map(([k, v]) => `<div><b>${v}</b><span>${k}</span></div>`).join("");
}

// ------------------------------------------------------------- large files --
let largeMb = 500, largeRows = [];
$$("#large-min button").forEach((b) => b.onclick = () => {
  $$("#large-min button").forEach((x) => x.classList.toggle("on", x === b)); largeMb = Number(b.dataset.mb);
});
function renderLarge() {
  if (!largeRows.length) {
    $("#large-chart").innerHTML = "";
    $("#large").innerHTML = `<p class="muted">No files over ${largeMb >= 1024 ? largeMb / 1024 + " GB" : largeMb + " MB"} in your folders.</p>`;
    return;
  }
  Charts.bars($("#large-chart"), largeRows.slice(0, 8).map((f) => ({ name: f.name, size: f.size, count: 1 })), { colorIndex: 2 });
  const ago = (t) => { const d = (Date.now() / 1000 - t) / 86400; return d < 1 ? "today" : d < 60 ? `${Math.round(d)} days ago` : d < 730 ? `${Math.round(d / 30)} months ago` : `${Math.round(d / 365)} years ago`; };
  $("#large").innerHTML = `<table class="tbl"><thead><tr><th><span class="sr-only">Pick</span></th><th>File</th><th>Last used</th><th class="num">Size</th></tr></thead><tbody>${
    largeRows.map((f, i) => `<tr><td><input type="checkbox" data-large="${i}" aria-label="Pick ${esc(f.name)}"></td>
      <td>${esc(f.name)}<div class="desc path">${esc(f.path)}</div></td><td>${ago(f.last_used)}</td><td class="num">${human(f.size)}</td></tr>`).join("")
  }</tbody></table><div class="row-head" style="margin-top:12px"><span class="muted" id="large-sel">Nothing picked</span>
    <button class="btn" id="large-go" disabled>Review removal</button></div>`;
  const update = () => {
    const picked = $$("[data-large]:checked").map((c) => largeRows[c.dataset.large]);
    $("#large-sel").textContent = picked.length ? `${picked.length} picked · ${human(picked.reduce((a, f) => a + f.size, 0))}` : "Nothing picked";
    $("#large-go").disabled = !picked.length;
  };
  $$("[data-large]").forEach((c) => c.addEventListener("change", update));
  $("#large-go").onclick = (e) => busy(e.target, async () => {
    const paths = $$("[data-large]:checked").map((c) => largeRows[c.dataset.large].path);
    renderPlan("#large-plan", await api("/api/plans/large", "POST", { paths }));
    $("#large-plan").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}
$("#large-btn").onclick = (e) => busy(e.target, async () => {
  const { job } = await api("/api/large", "POST", { roots: [], min_mb: largeMb });
  $("#large").innerHTML = `<div class="skeleton" style="height:160px"></div>`;
  for (;;) {
    await new Promise((r) => setTimeout(r, 700));
    const j = await api(`/api/jobs/${job}`);
    if (j.status === "done") { largeRows = j.result; $("#large-plan").innerHTML = ""; return renderLarge(); }
    if (j.status !== "running") throw new Error(j.error || "Search failed");
  }
});

// ---------------------------------------------------------------- live sync --
// Long-polls /api/events: the server answers the moment anything changes (a phone approves a
// plan, the guardian raises an alert, a scan finishes), so every open screen stays in step.
const onPage = (v) => $(`[data-page="${v}"]`)?.classList.contains("on");
const live = { seq: 0, boot: null, pending: new Set(), timer: null };
const PHONE_SAYS = { plans: "Your phone changed a plan", settings: "Settings changed on your phone" };
function applyLive() {
  const k = live.pending; live.pending = new Set();
  if (k.has("status") || k.has("plans")) { if (onPage("home")) { refreshStatus().catch(() => {}); loadWeek().catch(() => {}); } }
  if (k.has("notices") && onPage("home")) loadNotices().catch(() => {});
  if (k.has("scan") && onPage("home")) api("/api/scan/latest").then((s) => s.root && renderScan(s)).catch(() => {});
  if (k.has("settings")) api("/api/status").then((st) => ($("#mode-pill").textContent = st.mode)).catch(() => {});
  if (k.has("devices") && onPage("settings")) loadDevices().catch(() => {});
  if (k.has("history") && onPage("history")) loaders.history?.();
}
async function liveLoop() {
  for (;;) {
    try {
      const q = `/api/events?since=${live.seq}&timeout=25` + (live.boot ? `&boot=${live.boot}` : "");
      const r = await api(q);
      $("#live").classList.remove("off");
      const first = live.boot === null;
      live.boot = r.boot; live.seq = r.seq;
      if (first) continue; // first call only learns the cursor
      if (r.reset) { live.pending.add("status").add("notices").add("plans"); }
      for (const e of r.events) {
        live.pending.add(e.kind);
        if (e.kind === "plans" || e.kind === "status") live.pending.add("history");
        if (e.source === "phone" && PHONE_SAYS[e.kind]) toast(PHONE_SAYS[e.kind]);
        if (e.kind === "devices" && e.source === "phone") toast("Your phone is paired and connected");
      }
      clearTimeout(live.timer); live.timer = setTimeout(applyLive, 250); // batch bursts of events
    } catch (e) {
      $("#live").classList.add("off");
      await new Promise((res) => setTimeout(res, 4000));
    }
  }
}

async function loadNotices() {
  const n = await api("/api/notices");
  $("#notices").innerHTML = n.length ? n.slice(0, 8).map((x) => `<div class="notice ${esc(x.level)}"><b>${esc(x.title)}</b>
    <div class="muted">${esc(x.body || "")} · ${when(x.ts)}</div></div>`).join("") : `<p class="muted">No alerts.</p>`;
}
$("#read-btn").onclick = async () => { await api("/api/notices/read", "POST"); loadNotices(); };

let ageBy = "size", sizeBy = "size";
function renderScan(s) {
  lastScan = s;
  renderShelf();
  if (!s) {
    Charts.treemap($("#treemap"), []);
    ["#donut", "#ages", "#sizes"].forEach((id) => ($(id).innerHTML = `<p class="muted empty-chart">Appears after a scan.</p>`));
    return;
  }
  $("#scan-meta").textContent = `${s.root} · ${human(s.total_size)} in ${s.file_count.toLocaleString()} files · scanned in ${s.seconds}s` +
    (s.cloud_skipped ? ` · ${s.cloud_skipped} cloud-only files skipped (not downloaded)` : "");
  Charts.treemap($("#treemap"), s.tree || [], { onPick: (n) => { show("more"); $("#explain-path").value = n.path; $("#explain-btn").click(); } });
  Charts.donut($("#donut"), (s.categories || []).filter((c) => c.size > 0), { label: "by file type", value: human(s.total_size) });
  Charts.bars($("#ages"), s.ages || [], { by: ageBy, colorIndex: 1 });
  Charts.bars($("#sizes"), s.sizes || [], { by: sizeBy, colorIndex: 4 });
  $("#stale").innerHTML = (s.stale_large || []).length ? `<div class="list">${s.stale_large.slice(0, 8).map((f) => `<div class="li"><div>
      <b>${esc(f.path.split(/[\\/]/).pop())}</b><div class="path muted">${esc(f.path)}</div></div>
      <span class="num">${human(f.size)}<br>${new Date(Math.max(f.mtime, f.atime) * 1000).toLocaleDateString()}</span></div>`).join("")}</div>`
    : `<p class="muted">No files over 100 MB have sat untouched for 6 months. Nice.</p>`;
}
const segToggle = (sel, set) => $$(`${sel} button`).forEach((b) => b.onclick = () => {
  $$(`${sel} button`).forEach((x) => x.classList.toggle("on", x === b)); set(b.dataset.by); renderScan(lastScan);
});
segToggle("#age-by", (v) => (ageBy = v));
segToggle("#size-by", (v) => (sizeBy = v));
window.addEventListener("resize", () => { clearTimeout(window._rz); window._rz = setTimeout(() => { if (lastScan) renderScan(lastScan); loadHistory().catch(() => {}); }, 250); });

$("#scan-btn").onclick = (e) => busy(e.target, async () => {
  const { job } = await api("/api/scan", "POST", { root: $("#scan-root").value });
  $("#scan-meta").textContent = "Scanning… large drives take a minute.";
  $("#treemap").innerHTML = `<div class="skeleton" style="height:260px"></div>`;
  for (;;) {
    await new Promise((r) => setTimeout(r, 700));
    const j = await api(`/api/jobs/${job}`);
    if (j.status === "done") return renderScan(j.result);
    if (j.status !== "running") throw new Error(j.error || "Scan failed");
  }
});

// ----------------------------------------------------------------- search --
async function runSearch() {
  const q = $("#q").value.trim();
  if (!q) return;
  const hits = await api(`/api/search?q=${encodeURIComponent(q)}`);
  $("#q-out").innerHTML = `<div class="card">${hits.length ? `<div class="list">${hits.map((h) => `<div class="li"><div>
    <b>${esc(h.name)}</b><div class="path muted">${esc(h.path)}</div>
    ${h.snippet ? `<div class="meta">${esc(h.snippet).replace(/\[(.*?)\]/g, "<mark>$1</mark>")}</div>` : ""}</div>
    <span class="num">${human(h.size)}<br>${new Date(h.mtime * 1000).toLocaleDateString()}</span></div>`).join("")}</div>`
    : `<p class="muted">Nothing found. If you have not indexed yet, press “Refresh index now”.</p>`}</div>`;
}
$("#q-btn").onclick = (e) => busy(e.target, runSearch);
$("#q").addEventListener("input", () => { clearTimeout(window._qt); window._qt = setTimeout(() => $("#q").value.trim().length > 2 && runSearch().catch(() => {}), 350); });
$("#q").addEventListener("keydown", (e) => e.key === "Enter" && runSearch().catch((x) => toast(x.message, true)));
$("#idx-btn").onclick = (e) => busy(e.target, async () => {
  const { job } = await api("/api/search/index", "POST", { roots: [] });
  $("#idx-status").textContent = "Indexing your folders…";
  for (;;) {
    await new Promise((r) => setTimeout(r, 800));
    const j = await api(`/api/jobs/${job}`);
    if (j.status === "done") { $("#idx-status").textContent = `${j.result.total.toLocaleString()} files searchable · ${j.result.added} new, ${j.result.updated} changed`; return; }
    if (j.status !== "running") throw new Error(j.error || "Indexing failed");
  }
});

// --------------------------------------------------------------- organize --
loaders.organize = async () => {
  const st = await api("/api/settings");
  status = status || (await api("/api/status"));
  if (!$("#org-src").value) $("#org-src").value = status.user_folders.Desktop;
  if (!$("#org-root").value) $("#org-root").value = st.settings.organize_root || "";
};
$("#org-btn").onclick = (e) => busy(e.target, async () => {
  const root = $("#org-root").value.trim();
  if (!root) return toast("Choose where organized files should live");
  await api("/api/settings", "PUT", { organize_root: root });
  renderPlan("#org-plan", await api("/api/plans/organize", "POST", { source: $("#org-src").value.trim(), root, preset: $("#org-preset").value }));
});

// ----------------------------------------------------------------- caches --
loaders.caches = async () => {
  const rows = await api("/api/caches");
  const total = rows.filter((r) => !r.display_only).reduce((a, r) => a + r.size, 0);
  $("#cache-total").textContent = `Caches · ${human(total)} can be cleared`;
  const sized = rows.filter((r) => r.size > 0 && !r.display_only).sort((a, b) => b.size - a.size).slice(0, 8);
  if (sized.length) Charts.bars($("#cache-chart"), sized.map((r) => ({ name: r.name.split(" (")[0], size: r.size, count: r.paths.length })));
  else $("#cache-chart").innerHTML = "";
  const tbl = $("#cache-tbl");
  tbl.innerHTML = `<thead><tr><th>Cache</th><th>If cleared</th><th>Size</th><th>Default</th></tr></thead><tbody></tbody>`;
  rows.sort((a, b) => (b.paths.length || b.command ? 1 : 0) - (a.paths.length || a.command ? 1 : 0) || b.size - a.size);
  for (const r of rows) {
    const tr = document.createElement("tr");
    const found = r.paths.length > 0 || !!r.command;
    if (!found) tr.className = "dim";
    const note = r.apps_open.length ? ` · <span style="color:var(--warn)">${esc(r.apps_open.join(", "))} open</span>` : r.admin ? " · needs admin" : "";
    tr.innerHTML = `<td>${esc(r.name)}<div class="desc">${r.command ? "cleared by its own tool" : found ? `${r.paths.length} location${r.paths.length === 1 ? "" : "s"}` : "not found on this PC"}${note}</div></td>
      <td class="desc">${esc(r.effect)}</td><td class="num">${found && !(r.command && !r.size) ? human(r.size) : "–"}</td><td></td>`;
    tr.lastChild.appendChild(seg(r.choice, (v) => api("/api/settings/cache", "PUT", { key: r.id, value: v }), r.display_only));
    $("tbody", tbl).appendChild(tr);
  }
};
$("#cache-btn").onclick = (e) => busy(e.target, async () => renderPlan("#cache-plan", await api("/api/plans/clean", "POST", {})));

// ------------------------------------------------------------------- temp --
loaders.temp = async () => {
  const rows = await api("/api/temp/rules");
  const tbl = $("#temp-tbl");
  tbl.innerHTML = `<thead><tr><th>Temp file type</th><th>Rule</th><th>Default</th></tr></thead><tbody></tbody>`;
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(r.name)}</td><td class="desc">${esc(r.rule)}</td><td></td>`;
    tr.lastChild.appendChild(seg(r.choice, (v) => api("/api/settings/temp", "PUT", { key: r.id, value: v })));
    $("tbody", tbl).appendChild(tr);
  }
};
$("#temp-btn").onclick = (e) => busy(e.target, async () => renderPlan("#temp-plan", await api("/api/plans/temp", "POST", { roots: [] })));

// ------------------------------------------------------------------- more --
const roots = (sel) => $(sel).value.split(";").map((s) => s.trim()).filter(Boolean);
$("#dupe-btn").onclick = (e) => busy(e.target, async () => renderPlan("#more-plan", await api("/api/plans/duplicates", "POST", { roots: roots("#dupe-roots") })));
$("#dev-btn").onclick = (e) => busy(e.target, async () => renderPlan("#more-plan", await api("/api/plans/devjunk", "POST", { roots: roots("#dev-roots") })));
$("#arch-btn").onclick = (e) => busy(e.target, async () => renderPlan("#more-plan", await api("/api/plans/archive", "POST", { roots: roots("#arch-roots") })));
$("#devdata-btn").onclick = (e) => busy(e.target, async () => {
  const rows = await api("/api/devdata");
  $("#devdata").innerHTML = rows.length ? rows.map((r) => `<div class="li" style="display:block;margin-top:8px">
    <div class="row-head" style="margin:0 0 6px"><b>${esc(r.name)}</b><span class="num">${human(r.size)}</span></div>
    <ol class="steps">${r.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>
    ${r.compact ? `<p class="meta">${esc(r.compact.why)} ${esc(r.compact.how)}</p>${r.compact.scripts.map((sc) => `<pre class="code">${esc(sc)}</pre>`).join("")}` : ""}</div>`).join("")
    : `<p class="muted">No WSL, Docker, Android, Gradle, Ollama or Steam data found on this PC.</p>`;
});
$("#explain-btn").onclick = (e) => busy(e.target, async () => {
  const r = await api("/api/explain", "POST", { path: $("#explain-path").value.trim() });
  $("#explain-out").innerHTML = r.source === "known"
    ? `<dl class="explain"><dt>Size</dt><dd>${esc(r.size_human)}</dd><dt>Made by</dt><dd>${esc(r.made_by)}</dd><dt>Holds</dt><dd>${esc(r.holds)}</dd><dt>Safe to delete</dt><dd>${esc(r.safe_to_delete)}</dd></dl>`
    : `<dl class="explain"><dt>Size</dt><dd>${esc(r.size_human)}</dd><dt>${r.source === "ai" ? "AI says" : "Answer"}</dt><dd>${esc(r.answer)}</dd></dl>`;
});

// ---------------------------------------------------------------- folders --
loaders.folders = async () => {
  const rows = await api("/api/folders");
  $("#folder-tbl").innerHTML = `<thead><tr><th>Folder</th><th>Now at</th><th>Size</th></tr></thead><tbody>${rows.map((r) =>
    `<tr><td>${esc(r.name)}</td><td class="path">${esc(r.path)}</td><td class="num">${r.exists ? human(r.size) : "–"}</td></tr>`).join("")}</tbody>`;
};
$("#folder-btn").onclick = (e) => busy(e.target, async () => {
  const target = $("#folder-target").value.trim();
  if (!target) return toast("Enter the new location");
  renderPlan("#folder-plan", await api("/api/plans/folders", "POST", { target }));
});

// ---------------------------------------------------------------- history --
loaders.history = async () => {
  const list = await api("/api/plans");
  $("#plans").innerHTML = list.length ? `<div class="list">${list.map((p) => `<div class="li"><div><b>${esc(p.title)}</b>
    <div class="meta">${when(p.ts)} · ${p.summary.actions} actions · ${esc(p.status)}</div></div>
    <button class="btn ghost sm" data-open="${esc(p.id)}">Open</button></div>`).join("")}</div>` : `<p class="muted">No plans yet.</p>`;
  $$("[data-open]").forEach((b) => b.onclick = async () => renderPlan("#hist-plan", await api(`/api/plans/${b.dataset.open}`)));
};
$("#where-btn").onclick = (e) => busy(e.target, async () => {
  const rows = await api(`/api/where?q=${encodeURIComponent($("#where-q").value.trim())}`);
  $("#where-out").innerHTML = rows.length ? `<div class="list">${rows.map((r) => `<div class="li"><div>
    <div class="path">${esc(r.src)}</div><div class="path">→ ${esc(r.dst || "(cache, deleted)")}</div>
    <div class="meta">${esc(r.op)} · ${when(r.ts)} · ${r.undone ? "undone" : r.exists_now ? "still there" : "no longer there"}</div></div></div>`).join("")}</div>`
    : `<p class="muted">DriveMind has not moved anything with that name.</p>`;
});

// ------------------------------------------------------------------- apps --
let appsData = [], appsSort = "size";
function renderApps() {
  const f = $("#apps-filter").value.trim().toLowerCase();
  let rows = appsData.filter((a) => !f || a.name.toLowerCase().includes(f) || a.publisher.toLowerCase().includes(f));
  rows = [...rows].sort((a, b) => appsSort === "name" ? a.name.localeCompare(b.name)
    : appsSort === "installed" ? (a.installed || "9999").localeCompare(b.installed || "9999") : b.size - a.size);
  $("#apps").innerHTML = rows.length ? `<table class="tbl"><thead><tr><th>App</th><th>Installed</th><th>Drive</th><th class="num">Size</th></tr></thead><tbody>${rows.slice(0, 200).map((a) =>
    `<tr><td>${esc(a.name)}<div class="desc">${esc([a.publisher, a.version].filter(Boolean).join(" · "))}</div></td><td>${esc(a.installed || "–")}</td>
     <td>${esc(a.drive || "–")}</td><td class="num">${a.size ? human(a.size) : "–"}</td></tr>`).join("")}</tbody></table>`
    : `<p class="muted">${appsData.length ? "No app matches." : "Installed apps are read from Windows. None were found on this machine."}</p>`;
}
loaders.apps = async () => {
  appsData = await api("/api/apps");
  const total = appsData.reduce((a, x) => a + x.size, 0);
  $("#apps-title").textContent = appsData.length ? `Installed apps · ${appsData.length} · ${human(total)}` : "Installed apps";
  const top = appsData.filter((a) => a.size).slice(0, 8);
  if (top.length) Charts.bars($("#apps-chart"), top.map((a) => ({ name: a.name, size: a.size, count: 1 })), { colorIndex: 1 });
  renderApps();
  const st = await api("/api/startup");
  $("#startup-count").textContent = st.length ? `${st.filter((x) => x.enabled).length} of ${st.length} on` : "";
  $("#startup").innerHTML = st.length ? "" : `<p class="muted">Startup apps are read from Windows. None were found on this machine.</p>`;
  st.forEach((x) => {
    const row = document.createElement("div"); row.className = "li";
    row.innerHTML = `<div><b>${esc(x.name)}</b><div class="meta path">${esc(x.command)}</div><div class="meta">${esc(x.source)}${x.can_toggle ? "" : " · read-only"}</div></div>`;
    const sw = document.createElement("button"); sw.className = "switch"; sw.setAttribute("role", "switch");
    sw.setAttribute("aria-checked", x.enabled); sw.setAttribute("aria-label", `Start ${x.name} with Windows`); sw.disabled = !x.can_toggle;
    sw.onclick = async () => {
      const next = sw.getAttribute("aria-checked") !== "true";
      try { await api("/api/startup", "PUT", { name: x.name, enabled: next }); sw.setAttribute("aria-checked", next); toast(`${x.name} ${next ? "will" : "won't"} start with Windows`); }
      catch (e) { toast(e.message, true); }
    };
    row.appendChild(sw); $("#startup").appendChild(row);
  });
};
$("#apps-filter").addEventListener("input", renderApps);
$$("#apps-sort button").forEach((b) => b.onclick = () => { $$("#apps-sort button").forEach((x) => x.classList.toggle("on", x === b)); appsSort = b.dataset.sort; renderApps(); });

// -------------------------------------------------------------- assistant --
const chatLog = [];
function openChat(open) {
  $("#chat").classList.toggle("open", open); $("#chat").setAttribute("aria-hidden", !open);
  $("#chat").inert = !open; // closed: nothing inside can take keyboard focus
  $("#chat-fab").classList.toggle("hidden", open); $("#chat-fab").setAttribute("aria-expanded", open);
  if (open) setTimeout(() => $("#chat-in").focus(), 150);
}
$("#chat-fab").onclick = () => openChat(true);
$("#chat-close").onclick = () => openChat(false);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#chat").classList.contains("open")) openChat(false); });
function addMsg(role, html) {
  const m = document.createElement("div"); m.className = `msg ${role}`; m.innerHTML = html;
  $("#chat-log").appendChild(m); $("#chat-log").scrollTop = $("#chat-log").scrollHeight; return m;
}
async function ask(q) {
  q = q.trim(); if (!q) return;
  addMsg("user", esc(q));
  const wait = addMsg("bot", `<span class="typing" aria-label="Thinking"><i></i><i></i><i></i></span>`);
  try {
    const r = await api("/api/chat", "POST", { question: q, history: chatLog.slice(-6) });
    chatLog.push({ role: "user", content: q }, { role: "assistant", content: r.answer });
    const srcs = r.ai && r.sources.length ? `<div class="srcs">${r.sources.map((s, i) => `<span class="src"><b>[${i + 1}] ${esc(s.name)}</b> — ${esc(s.path)}</span>`).join("")}</div>` : "";
    const acts = r.actions.length ? `<div class="chips">${r.actions.map((a) => `<button class="chip" data-go="${esc(a.target)}">${esc(a.label)}</button>`).join("")}</div>` : "";
    wait.innerHTML = `${esc(r.answer)}${srcs}${acts}<span class="ai-tag">${r.ai ? "Written by your local AI from the facts above" : "From DriveMind's own data"}</span>`;
    $$("[data-go]", wait).forEach((b) => b.onclick = () => { openChat(false); show(b.dataset.go); });
  } catch (e) { wait.textContent = e.message; }
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
}
$("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#chat-in").value; $("#chat-in").value = ""; ask(v); });
$("#chat-log").addEventListener("click", (e) => { const q = e.target.closest("[data-q]")?.dataset.q; if (q) ask(q); });

// --------------------------------------------------------------- settings --
const MODES = [
  ["safe", "Safe", "Everything waits for your tap."],
  ["balanced", "Balanced", "Safe, reversible jobs run by themselves; anything that moves your files asks first."],
  ["autopilot", "Autopilot", "Runs everything except permanent changes, which still ask."],
];
loaders.settings = async () => {
  const { settings: s, options } = await api("/api/settings");
  $("#mode-pill").textContent = s.mode;
  $("#modes").innerHTML = MODES.map(([id, name, d]) => `<button class="mode ${s.mode === id ? "on" : ""}" data-mode="${id}"><b>${name}</b><span>${d}</span></button>`).join("");
  $$("[data-mode]").forEach((b) => b.onclick = async () => { await api("/api/settings/mode", "PUT", { mode: b.dataset.mode }); toast(`${b.textContent.split(" ")[0]} mode on`); loaders.settings(); });
  const tbl = $("#opt-tbl");
  tbl.innerHTML = `<thead><tr><th>Option</th><th></th></tr></thead><tbody></tbody>`;
  for (const [k, desc] of Object.entries(options)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(desc)}<div class="desc">${esc(k)}</div></td><td></td>`;
    tr.lastChild.appendChild(seg(s.options[k] || "ask", async (v) => { const r = await api("/api/settings/option", "PUT", { key: k, value: v }); $("#mode-pill").textContent = r.mode; $$(".mode").forEach((m) => m.classList.toggle("on", m.dataset.mode === r.mode)); }));
    $("tbody", tbl).appendChild(tr);
  }
  $("#prefs").innerHTML = `
    <label>Organized root<input class="input" data-k="organize_root" value="${esc(s.organize_root)}"></label>
    <label>Low-space alert (%)<input class="input" type="number" data-k="low_space_percent" value="${s.low_space_percent}"></label>
    <label>AI must be this sure to act alone<input class="input" type="number" step="0.05" min="0" max="1" data-k="confidence_threshold" value="${s.confidence_threshold}"></label>
    <label>Quarantine days<input class="input" type="number" data-k="quarantine_days" value="${s.quarantine_days}"></label>
    <label>Temp Zone days<input class="input" type="number" data-k="temp_zone_days" value="${s.temp_zone_days}"></label>
    <label>Project idle days<input class="input" type="number" data-k="stale_project_days" value="${s.stale_project_days}"></label>
    <label>Never touch (folders, ; separated)<input class="input" data-k="exclusions" value="${esc(s.exclusions.join("; "))}"></label>
    <label>Local AI model (Ollama)<input class="input" data-k="ollama_model" value="${esc(s.ollama_model)}"></label>
    <div class="form-actions"><button class="btn" id="prefs-save">Save</button></div>`;
  $("#prefs-save").onclick = (e) => busy(e.target, async () => {
    const patch = {};
    $$("[data-k]", $("#prefs")).forEach((i) => {
      const k = i.dataset.k;
      patch[k] = k === "exclusions" ? i.value.split(";").map((x) => x.trim()).filter(Boolean) : i.type === "number" ? Number(i.value) : i.value.trim();
    });
    await api("/api/settings", "PUT", patch); toast("Saved");
  });
  loadRules();
  loadDevices();
};
async function loadDevices() {
  const d = await api("/api/devices");
  $("#devices").innerHTML = d.devices.length ? `<div class="list">${d.devices.map((x) => `<div class="li"><div><b>${esc(x.name)}</b>
    <div class="meta">paired ${when(x.created)} · ${x.last_seen ? "last seen " + when(x.last_seen) : "not connected yet"}</div></div>
    <button class="btn danger sm" data-unpair="${esc(x.id)}">Remove</button></div>`).join("")}</div>` : "";
  $$("[data-unpair]").forEach((b) => b.onclick = async () => { await api(`/api/devices/${b.dataset.unpair}`, "DELETE"); toast("Phone removed — it can no longer connect"); loadDevices(); });
}
$("#pair-btn").onclick = (e) => busy(e.target, async () => {
  const r = await api("/api/pair", "POST", { name: "Android phone" });
  // qr_svg is generated locally by DriveMind (segno), not user content
  $("#pair-out").innerHTML = `<div class="pair">${r.qr_svg || ""}<div><p><b>On your phone, tap “Find my PC” and enter</b></p>
    <p class="pin" aria-label="Pairing code ${esc(r.pin.split("").join(" "))}">${esc(r.pin.slice(0, 3))} ${esc(r.pin.slice(3))}</p>
    <p class="muted">The code works once, for 5 minutes. Or scan the QR code with the app.</p>
    <details><summary class="muted">Typing it by hand instead?</summary><p class="path">${esc(r.code)}</p></details>
    ${r.lan_enabled ? "" : `<p style="color:var(--warn)">Phone sync is not listening on Wi-Fi yet. Restart DriveMind to turn it on.</p>`}
    <p class="muted">Windows may ask to allow Python on the network — choose Private networks.</p></div></div>`;
  loadDevices();
});

async function loadRules() {
  const rs = await api("/api/rules");
  $("#rules").innerHTML = rs.length ? `<div class="list">${rs.map((r, i) => `<div class="li"><div><b>${esc(r.name)}</b><div class="meta">→ ${esc(r.destination)}</div></div>
    <button class="btn ghost sm" data-del="${i}">Remove</button></div>`).join("")}</div>` : `<p class="muted">No rules yet.</p>`;
  $$("[data-del]").forEach((b) => b.onclick = async () => { await api(`/api/rules/${b.dataset.del}`, "DELETE"); loadRules(); });
}
$("#rule-btn").onclick = (e) => busy(e.target, async () => {
  await api("/api/rules", "POST", { text: $("#rule-text").value });
  $("#rule-text").value = ""; toast("Rule added"); loadRules();
});

// mode and version in the sidebar are correct on every page, not only Home
api("/api/status").then((st) => { $("#mode-pill").textContent = st.mode; $("#ver").textContent = "v" + st.version; }).catch(() => {});
$("#mcp-cmd").textContent = "claude mcp add drivemind -- python -m drivemind mcp";
applyTheme(theme);
show(location.hash.slice(1) || "home");
liveLoop();
