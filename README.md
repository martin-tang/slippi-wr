# Slippi History Advanced

A standalone desktop application that parses **Super Smash Bros. Melee** replay files (`.slp`) and presents rich win/loss analytics, stage breakdowns, character preferences, and set tracking — all in a clean, themed UI.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

| Feature | Description |
|---|---|
| **Total Win Rate** | Overall W–L record across all games |
| **Ranked / Unranked Split** | Separate stats for ranked and unranked play |
| **Set Win Rate** | Ranked set W–L (Bo3 tracking via `match_id`) |
| **Stage Win Rates** | Segmented bar graph + per-stage breakdown with stage thumbnails |
| **Character Preferences** | What characters opponents play against you, with stock icons |
| **My Characters** | Your own character usage stats with icons |
| **Opponent History** | Per-opponent detailed view with all the above stats |
| **Search & Sort** | Filter opponents by name; sort by Recent, Games, WR%, or Name |
| **Live Game Tracking** | Monitors replay directory for in-progress games |
| **Dark / Light Theme** | Toggle via Settings; applies instantly |
| **Custom Window Icon** | Auto-selects your most-played character, or pick manually |
| **Export History** | Save your full history as a portable JSON file |

---

## Stack

| Component | Technology |
|---|---|
| Language | **Python 3.10+** |
| GUI | **tkinter** (standard library) |
| Replay Parsing | **[py-slippi](https://pypi.org/project/py-slippi/)** — pure Python, no Slippi JS SDK required |
| File Monitoring | **[watchdog](https://pypi.org/project/watchdog/)** |
| Image Processing | **[Pillow](https://pypi.org/project/Pillow/)** |
| Packaging | **[PyInstaller](https://pypi.org/project/pyinstaller/)** (for `.exe` distribution) |

> **Note:** This project is entirely standalone Python. It does **not** depend on the JavaScript Slippi SDK (`@slippi/slippi-js`) or Node.js.

---

## Quick Start

### From source

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/slippi-history-advanced.git
cd slippi-history-advanced

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py
```

### First run

1. Enter your **connect code** (e.g. `MOXI#684`).
2. Click **…** to select your Slippi replay directory (usually `Documents/Slippi`).
3. Click **Import** — the app will recursively scan all `.slp` files.
4. Browse opponents, check your overall stats, and leave the app running to track live games.

---

## Building a standalone `.exe`

```bash
pip install pyinstaller
python build.py
```

The output is `dist/SlippiHistoryAdvanced.exe` — a single-file executable that can be shared with anyone, no Python install required. The `winrate_data.json` file is created next to the `.exe` on first run.

---

## Project Structure

```
winrate-overlay-advanced/
├── main.py            # GUI application (tkinter)
├── slp_parser.py      # .slp replay parser + data model
├── watcher.py         # Live file-system watcher
├── build.py           # PyInstaller build script
├── requirements.txt   # Python dependencies
├── imgs/
│   ├── stages/        # Stage thumbnails (battlefield, FD, etc.)
│   └── stock_icons/   # Character stock icons (24×24 PNGs)
├── winrate_data.json  # Persisted data (gitignored)
└── README.md
```

---

## How It Works

1. **Parsing** — `slp_parser.py` uses [py-slippi](https://pypi.org/project/py-slippi/) to read completed `.slp` files. It also includes a lightweight binary reader that extracts `match_id` and `game_number` directly from the game-start command (these fields are not exposed by py-slippi), enabling ranked set tracking and game-mode detection.

2. **Live Monitoring** — `watcher.py` uses [watchdog](https://pypi.org/project/watchdog/) to recursively monitor the replay directory. When a new `.slp` appears, it reads player info from the raw binary header while the game is still in progress, then parses the full file once writing stops.

3. **Data Model** — Each opponent gets a record with total/ranked/unranked W–L, set W–L, per-stage stats, character usage, and a `last_played` timestamp. An overall record aggregates everything. All data is persisted to `winrate_data.json`.

4. **GUI** — `main.py` builds a tkinter interface with a searchable/sortable opponent list, a scrollable detail panel, segmented bar graphs, and inline stage/character icons loaded via Pillow.

---

## License

MIT
