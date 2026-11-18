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
  history.replaceState(null, "", "#" + view);
  loaders[view]?.();
}
$$("#nav a").forEach((a) => a.addEventListener("click", () => show(a.dataset.view)));

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

function ring(percentUsed, status) {
  const r = 62, c = 2 * Math.PI * r, used = Math.min(100, Math.max(0, percentUsed));
  const color = status === "critical" ? "var(--bad)" : status === "watch" ? "var(--warn)" : "var(--accent)";
  return `<svg class="ring" viewBox="0 0 150 150" role="img" aria-label="${used.toFixed(0)}% used">
    <circle cx="75" cy="75" r="${r}" fill="none" stroke="var(--line)" stroke-width="12"/>
    <circle cx="75" cy="75" r="${r}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${(c * used) / 100} ${c}" transform="rotate(-90 75 75)"/>
    <text x="75" y="80" text-anchor="middle">${used.toFixed(0)}%</text>
    <text x="75" y="100" text-anchor="middle" class="lbl">used</text></svg>`;
}

function bars(rows, total, label = (r) => r.path) {
  if (!rows.length) return `<p class="empty">Nothing here.</p>`;
  const max = Math.max(...rows.map((r) => r.size), 1);
  return `<div class="bars">${rows.map((r) => `
    <div class="brow"><div class="track"><span class="fill" style="width:${(100 * r.size) / max}%"></span>
      <span class="name path" title="${esc(r.path || r.ext)}">${esc(label(r))}</span></div>
      <span class="num">${human(r.size)}</span></div>`).join("")}</div>`;
}

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

// ------------------------------------------------------------------- home --
let status = null;
loaders.home = async () => {
  try {
    status = await api("/api/status");
    $("#ver").textContent = "v" + status.version;
    $("#mode-pill").textContent = status.mode;
    const sys = status.drives.find((d) => d.drive === status.system_drive) || status.drives[0];
    if (!$("#scan-root").value) $("#scan-root").value = sys?.drive || "/";
    if (sys) {
      const msg = { good: "Plenty of room.", watch: "Getting full — worth a clean.", critical: "Almost full — fix this now." }[sys.status];
      $("#home-sub").textContent = `${sys.drive} has ${human(sys.free)} free. ${msg}`;
      $("#hero").innerHTML = `${ring(100 - sys.free_percent, sys.status)}<div>
        <p class="big">Health ${sys.score}/100</p><span class="pill ${sys.status === "good" ? "yes" : "ask"}">${esc(sys.status)}</span>
        <dl><dt>Free</dt><dd>${human(sys.free)}</dd><dt>Used</dt><dd>${human(sys.used)}</dd><dt>Size</dt><dd>${human(sys.total)}</dd>
        <dt>Full in</dt><dd>${sys.days_to_full ? `~${Math.round(sys.days_to_full)} days` : sys.trend === "learning" ? "learning (needs a few days)" : "not filling up"}</dd></dl></div>`;
    }
    $("#drives").innerHTML = status.drives.map((d) => `<div class="drive"><b>${esc(d.drive)}</b>
      <div class="bar ${d.status}"><i style="width:${100 - d.free_percent}%"></i></div>
      <span class="muted">${human(d.free)} free of ${human(d.total)}</span></div>`).join("");
  } catch (e) { toast(e.message, true); }
  loadNotices();
  api("/api/advice").then((a) => {
    $("#tips").innerHTML = a.tips.length ? a.tips.map((t) => `<div class="tip"><b>${esc(t.title)}</b><p>${esc(t.detail)}</p>
      <button class="btn sm" data-tip="${esc(t.action)}">Fix</button></div>`).join("")
      : (status?.drives?.find((d) => d.drive === status.system_drive)?.status || "good") === "good"
        ? `<p class="muted">No big wins right now. Your drive is in good shape.</p>`
        : `<p class="muted">No single cache or project is the culprit. Scan the drive below to see which folders take the space.</p>`;
    $$("[data-tip]").forEach((b) => b.onclick = () => show({ clean_caches: "caches", clean_dev_junk: "more", move_user_folders: "folders" }[b.dataset.tip] || "home"));
  }).catch(() => ($("#tips").innerHTML = `<p class="muted">Could not build tips.</p>`));
  api("/api/scan/latest").then((s) => s.root && renderScan(s));
};

async function loadNotices() {
  const n = await api("/api/notices");
  $("#notices").innerHTML = n.length ? n.slice(0, 8).map((x) => `<div class="notice ${esc(x.level)}"><b>${esc(x.title)}</b>
    <div class="muted">${esc(x.body || "")} · ${when(x.ts)}</div></div>`).join("") : `<p class="muted">No alerts.</p>`;
}
$("#read-btn").onclick = async () => { await api("/api/notices/read", "POST"); loadNotices(); };

function renderScan(s) {
  $("#scan-out").innerHTML = `<p class="muted">${human(s.total_size)} in ${s.file_count.toLocaleString()} files · ${s.seconds}s
    ${s.cloud_skipped ? ` · ${s.cloud_skipped} cloud-only files skipped (not downloaded)` : ""}</p>
    ${bars(s.children, s.total_size, (r) => r.path.split(/[\\/]/).pop() || r.path)}
    <div class="cols"><div><h3>Largest files</h3>${bars(s.largest_files.slice(0, 10), 0, (r) => r.path.split(/[\\/]/).pop())}</div>
    <div><h3>By file type</h3>${bars(s.by_type.slice(0, 10), 0, (r) => r.ext)}</div></div>
    ${s.growth.length ? `<h3 class="muted" style="margin-top:16px">Grew since the last scan</h3>${bars(s.growth.filter((g) => g.delta > 0).slice(0, 6).map((g) => ({ path: g.path, size: g.delta })), 0, (r) => rel(r.path, s.root))}` : ""}`;
}

$("#scan-btn").onclick = (e) => busy(e.target, async () => {
  const { job } = await api("/api/scan", "POST", { root: $("#scan-root").value });
  $("#scan-out").innerHTML = `<p class="muted">Scanning… large drives take a minute.</p>`;
  for (;;) {
    await new Promise((r) => setTimeout(r, 700));
    const j = await api(`/api/jobs/${job}`);
    if (j.status === "done") return renderScan(j.result);
    if (j.status !== "running") throw new Error(j.error || "Scan failed");
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
};
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

show(location.hash.slice(1) || "home");
