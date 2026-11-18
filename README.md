# DriveMind — AI Drive Guardian for Windows

DriveMind organizes your files, clears caches and temporary junk, finds duplicates and old project dependencies, moves your user folders off drive C:, and watches C: so it never fills up by surprise.

**The AI proposes; you approve.** Every change is a plan you can review. Your Yes / Ask / No settings decide what runs on its own. Every step is journaled, and any plan can be undone.

## Install (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/). Tick "Add python.exe to PATH".
2. In this folder, run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
   ```
   The installer creates a virtual environment, installs DriveMind, adds the Explorer right-click menu, and offers to start DriveMind with Windows. It needs no admin rights.
3. Open the dashboard with `scripts\DriveMind.bat`. It runs at http://127.0.0.1:7878.
4. Optional local AI: install [Ollama](https://ollama.com), then run `ollama pull qwen3:4b`. DriveMind uses the AI only for files it cannot place by itself, and it sends only file names, never contents.

## What it does

| Area | What you get |
| --- | --- |
| **Dashboard** | Live Overview in light or dark (follows Windows, or pick one): free space, health, "full in" forecast and waiting changes, refreshed every 30 seconds. Charts: space over 7, 30 or 90 days, a treemap of what fills the drive (click a block for "what is this folder?"), file types, file ages and file sizes, plus big files untouched for 6 months. No build step, no external requests, works at phone width. |
| **Disk Guardian** | Health score per drive, a forecast of when the drive will be full, a low-space alert, and a scan of what is eating space. The scan never downloads OneDrive online-only files. |
| **Organizer** | Six layouts (Developer, Student, Freelancer, By type, Minimal, Johnny Decimal). Project folders move as one unit. Old versions are stacked into `_versions`. Camera and WhatsApp photos get readable names. Exact copies are detected, and same-name files get a `(2)` suffix. |
| **Decision chain** | 1. Your rules. 2. Habits learned from your approvals and rejections (naive Bayes). 3. File-type classifier. 4. Local AI, used only for files the first three are unsure about. |
| **Cache Cleaner** | 17 caches, each with its own Yes / Ask / No switch. Caches of apps that are open are skipped. Temp files are removed only after a day unused. |
| **Temporary files** | 10 junk rules (unfinished downloads, Office lock files, old installers, extracted zips, old builds, and more). Also a Temp Zone that clears itself and a right-click "temporary for N days" option. |
| **Duplicates** | Matched by content (file size, then a partial hash, then a full hash), so renamed copies are caught. The copy in your most organized folder is kept. |
| **Dev junk** | `node_modules`, `.venv`, `build`, `.next`, `.gradle` and similar folders in projects idle for 60+ days. Each one is shown with the command that brings it back. Dependencies are deleted; build outputs go to quarantine, since they might hold hand-made files. |
| **User folders** | Moves Desktop, Downloads, Documents, Pictures and Videos to another drive, then re-points Windows (as Explorer's Location > Move does), so your apps follow. |
| **Search** | Find files by what is inside them (Word, Excel, PowerPoint, text, code, and PDF with `pypdf`), plus type and month/year: *dubai invoice march*. Uses SQLite's built-in full-text search (FTS5 with BM25 ranking), stays on the PC, and refreshes every 6 hours. |
| **Project archiver** | Projects idle for 90+ days are zipped with their full git history, leaving out regenerable dependencies but keeping build folders. Uncommitted, stashed or unpushed work is never archived automatically. The original stays in quarantine, so Undo works. |
| **Disk health** | SSD wear, temperature, error counts and Windows' health status, read from the drive's own reliability counters, with a daily alert if a disk needs attention. |
| **Developer data** | WSL distros, Docker's disk, Android SDK and emulators, Gradle, Ollama models and Steam games: their size on C:, the supported way to move each, and a diskpart script that shrinks WSL and Docker virtual disks. |
| **Tray** | A ring next to the clock, coloured by C: health, with Open dashboard, Tidy now, Pause and Quit. It starts with Windows. |
| **History** | Undo any plan, and "Where did my file go?" search across everything DriveMind has moved. |
| **Assistant** | Ask in English or Roman Urdu: *what is eating my space?*, *find my Dubai invoice*, *C drive saaf karo*. Common questions go straight to DriveMind's own tools; anything else is answered from your indexed documents (RAG), with the files cited. If a local model is running (Ollama), it writes the answer from those facts only; without one, DriveMind answers from the same facts. Nothing leaves the PC. |
| **MCP server** | `drivemind mcp` lets Claude, Cursor or any MCP client check drive health, search files, explain folders and propose cleanups. Plans it builds still wait for your approval: the MCP tools cannot approve. |
| **Apps & startup** | Installed apps by size and install date, and the apps that start with Windows, each with an on/off switch that works exactly like Task Manager (current user only, reversible). |
| **Android app** | Tap **Find my PC** and type the 6-digit code your PC shows (or scan the QR code). See drive health, this week's report and alerts, approve, reject or undo plans, "Tidy now", Yes / Ask / No switches and mode, and **Ask** the assistant. Keeps the last data on the phone, so it still shows something when you are away from home. See `mobile/README.md`. |
| **Live sync** | The PC dashboard and the phone update the moment anything changes on either side: a plan approved on the phone, an alert from the guardian, a finished scan, a new paired phone. Typically well under a second on home Wi-Fi. Plain HTTP long-polling, so it needs nothing extra on Android. |
| **This week** | A weekly report on the Overview, the phone and as a notification: space freed, files organized, plans applied and how much the drive grew. Taken from the undo journal and daily snapshots, never estimated. |
| **Large files** | The biggest files in your folders with when you last used them. Pick what to let go; it goes to quarantine for 30 days. Large files are never removed automatically, not even on Autopilot. |
| **What is this folder?** | Built-in knowledge of about 30 common folders (WinSxS, node_modules, Installer…), with the local AI as a fallback. |

## Settings: Yes / Ask / No

- **Yes** means do it automatically and log it.
- **Ask** means propose it and wait for your tap.
- **No** means never do it.

Three modes set every switch at once:

- **Safe**: everything asks first.
- **Balanced** (default): safe, reversible jobs run on their own, and anything that moves your files asks first.
- **Autopilot**: everything runs, except permanent changes, which still ask.

AI guesses below 80% confidence always wait for you, whatever the mode.

## Safety built in

- Deletes go to a 30-day quarantine, then to the Recycle Bin. A delete is permanent only if you set `skip_quarantine` to Yes.
- Windows, Program Files, ProgramData, `.git` internals and DriveMind's own data are protected. You can add your own "never touch" folders.
- Cache deletion is restricted to an allow-list: the executor refuses any path that is not on the cache catalog or a real dev-junk folder.
- Files that are locked or in use are skipped, never forced.
- Every completed step is written to the journal before the next one starts, so undo works even after a crash.
- The local API answers only on `127.0.0.1`. It requires an `X-DriveMind` header, so other websites cannot drive it, and it checks the Host header to block DNS rebinding.
- Phones use a separate `/m` API on your Wi-Fi. Every call needs that phone's own token (only a hash is stored), and you can remove a phone at any time. The PC listens on Wi-Fi only once a phone is paired.
- Before pairing, a phone can only ask "is DriveMind here?" (it learns the PC's name) and trade a 6-digit code for its token. A code works once, for 5 minutes, and code pairing locks for 5 minutes after 8 wrong codes. Pressing "Pair a phone" again replaces any pairing no phone has used, and unused pairings expire after 15 minutes.

## Command line

```text
drivemind status                        health of every drive
drivemind scan C:\                      biggest folders and files, growth since last scan
drivemind root D:\Organized             where organized files go
drivemind organize %USERPROFILE%\Desktop --dry-run
drivemind clean caches|temp|dev|dupes   build a plan (add --apply to run automatic actions)
drivemind plans | show ID | approve ID [ids] | apply ID | undo ID
drivemind where report.pdf              where did my file go?
drivemind explain "C:\some\folder"      what is this folder and is it safe to delete?
drivemind mode safe|balanced|autopilot
drivemind set organize_moves yes        also: cache.pip no, temp.installers ask
drivemind rule "anything with invoice from Downloads goes to Work/Invoices"
drivemind index / search dubai invoice march
drivemind archive [--apply]             zip idle projects (git-safe)
drivemind ssd                           disk health
drivemind devdata                       WSL / Docker / Android SDK sizes and how to move them
drivemind tray                          tray icon + dashboard + phone sync + guardian
drivemind tag-temp file.zip --days 7
drivemind shell install|uninstall|autostart-on|autostart-off
drivemind serve                         dashboard + background guardian (+ phone sync once paired)
drivemind pair                          pair a phone without the dashboard (prints a code)
drivemind chat "what is eating my space?"   ask the assistant
drivemind report [--days 7]             what DriveMind did this week
drivemind large [folders] [--min-mb 500]  the biggest files in your folders
drivemind mcp                           MCP server over stdio (for Claude, Cursor…)
```

## Use DriveMind from Claude (MCP)

```bash
pip install "drivemind[mcp]"
claude mcp add drivemind -- python -m drivemind mcp
```

For Claude Desktop, add to `claude_desktop_config.json`:

```json
{ "mcpServers": { "drivemind": { "command": "python", "args": ["-m", "drivemind", "mcp"] } } }
```

Tools: `drive_status`, `scan_folder`, `search_files`, `where_is_file`, `explain_folder`, `cache_report`, `plan_cleanup`, `plan_organize`, `get_plan`, `apply_plan`, `undo_plan`, `ask_drivemind`. `apply_plan` runs only the steps you already approved.

## Architecture

```text
drivemind/
  config.py      settings, modes, Yes/Ask/No gate, confidence rule
  paths.py       protected paths, OneDrive placeholders, long paths, Known Folders
  winapi.py      ctypes: Known Folders, battery, fullscreen game, Recycle Bin
  scanner.py     fast iterative scan (no symlink loops, no cloud downloads)
  db.py          SQLite: snapshots, scans, plans, journal, feedback, notices
  disk.py        health score, forecast (least-squares trend), growth
  classify.py    file classifier, layouts, smart rename, version keys
  rules.py       user rules + plain-English rule parser
  learner.py     habit model trained on approvals/rejections
  ai.py          Ollama client with JSON-schema output, validated
  planner.py     organize plans (rules -> habits -> classifier -> AI)
  cleaner.py     cache catalog, temp-junk rules, Temp Zone, expiry tags
  devjunk.py     stale project dependencies and builds
  duplicates.py  content-based duplicate finder
  pathmanager.py move user folders to another drive
  executor.py    apply / undo / quarantine / journal / where-is
  advisor.py     top fixes for the weekly report
  service.py     background guardian (snapshots, alerts, downloads, weekly clean)
  explain.py     "what is this folder?"
  winshell.py    Explorer right-click menu, autostart (HKCU only)
  api.py         local FastAPI server
  cli.py         command line
  devices.py     phone pairing tokens, 6-digit codes, QR code, Wi-Fi address
  events.py      live sync: change events the dashboard and phone long-poll
  insights.py    weekly report and the large-file finder
  archiver.py    git-safe zip archiving of idle projects
  search.py      full-text file search (SQLite FTS5)
  ssd.py         disk health from reliability counters
  devdata.py     WSL / Docker / Android / Gradle / Ollama / Steam report
  tray.py        system-tray app
  winapps.py     installed apps and startup switches (registry)
  chat.py        assistant: intent routing + local RAG + optional Ollama
  mcp_server.py  MCP tools over stdio
  web/           dashboard + charts.js (SVG charts, no build step, no external requests)
mobile/          Android app (Expo SDK 58, React Native, TypeScript)
```

## Development

```bash
pip install -e ".[dev,all]"
pytest -q          # 63 tests, run on Windows and Ubuntu (Python 3.11 and 3.13) in CI
cd mobile && npm install && npx tsc --noEmit   # typecheck the Android app
```

## Not done yet

- **Not yet tried by hand on a real PC or phone:** the tray icon, Known Folder moves, the Explorer menu, disk counters, and the Android app on a device. The test suite does run on Windows in CI.
- **Elevated helper:** fast MFT scan and the admin-only caches (Windows Update, Prefetch, Delivery Optimization).
- **Image understanding:** screenshot OCR, photo albums and "find the photo of…" search (CLIP).
- **Phone away from home:** needs a relay or Tailscale. While the app is closed, alerts still arrive by the 15-minute background check; instant push (FCM) would need a server.
- **Signed installer (MSIX) and auto-update.**

## License

MIT
