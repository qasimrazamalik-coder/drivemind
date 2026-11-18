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
| **Disk Guardian** | Health score per drive, a forecast of when the drive will be full, a low-space alert, and a scan of what is eating space. The scan never downloads OneDrive online-only files. |
| **Organizer** | Six layouts (Developer, Student, Freelancer, By type, Minimal, Johnny Decimal). Project folders move as one unit. Old versions are stacked into `_versions`. Camera and WhatsApp photos get readable names. Exact copies are detected, and same-name files get a `(2)` suffix. |
| **Decision chain** | 1. Your rules. 2. Habits learned from your approvals and rejections (naive Bayes). 3. File-type classifier. 4. Local AI, used only for files the first three are unsure about. |
| **Cache Cleaner** | 17 caches, each with its own Yes / Ask / No switch. Caches of apps that are open are skipped. Temp files are removed only after a day unused. |
| **Temporary files** | 10 junk rules (unfinished downloads, Office lock files, old installers, extracted zips, old builds, and more). Also a Temp Zone that clears itself and a right-click "temporary for N days" option. |
| **Duplicates** | Matched by content (file size, then a partial hash, then a full hash), so renamed copies are caught. The copy in your most organized folder is kept. |
| **Dev junk** | `node_modules`, `.venv`, `build`, `.next`, `.gradle` and similar folders in projects idle for 60+ days. Each one is shown with the command that brings it back. |
| **User folders** | Moves Desktop, Downloads, Documents, Pictures and Videos to another drive, then re-points Windows (as Explorer's Location > Move does), so your apps follow. |
| **History** | Undo any plan, and "Where did my file go?" search across everything DriveMind has moved. |
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
drivemind tag-temp file.zip --days 7
drivemind shell install|uninstall|autostart-on|autostart-off
drivemind serve                         dashboard + background guardian
```

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
  web/           dashboard (no build step, no external requests)
```

## Development

```bash
pip install -e ".[dev]"
pytest -q          # 28 tests, run on Windows and Ubuntu in CI
```

## Roadmap (next)

- Tauri desktop shell with a tray icon, wrapping the same dashboard.
- Elevated helper service for MFT fast-scan and the admin-only caches.
- WSL / Docker / Android SDK mover and `.vhdx` compactor.
- Semantic search over file contents, screenshot OCR, and photo albums (CLIP).
- Git-safe project archiver, SSD SMART health, and phone alerts.

## License

MIT
