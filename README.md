# How to use:

1. Download the .exe via Right click > Save Link As ... or Download the repo through <> code, download as .zip (only need .exe, rest can be deleted.)
2. Use the file selector to select your Slippi replay folder. You can do the top level folder or an individual month. By default it's at C:/Users/YOURUSERNAME/Documents/Slippi
3. Press Import and wait for completion.
4. Voila! Keep this up to see your opponents counter picks & your ongoing w/r
5. P.S. If you upgrade your PC and don't migrate all your .slp replays, you can keep your history via Export. (But I suggest keeping your .slps if you can afford the HD space.)
6. P.P.S. There is a miniature

![Overall Stats Screenshot](https://i.imgur.com/mlcRTex.png)


# Slippi History Advanced

A Slippi companion app that parses **Super Smash Bros. Melee** replay files (`.slp`) and presents rich win/loss analytics, stage breakdowns, character preferences, and set tracking — all in a clean, themed UI.

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

> **Note:** This project is entirely standalone Python. It does **not** depend on the JavaScript Slippi SDK (`@slippi/slippi-js`) or Node.js. The original SDK source is kept in `slippi-sdk/` for reference only.

---

## For developers

### From source

```bash
# 1. Clone the repo
git clone https://github.com/martin-tang/slippi-wr.git
cd slippi-wr/winrate-overlay-advanced

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
cd winrate-overlay-advanced
pip install pyinstaller
python build.py
```

The output is `dist/SlippiHistoryAdvanced.exe` — a single-file executable that can be shared with anyone, no Python install required. The `winrate_data.json` file is created next to the `.exe` on first run.

---


## How It Works

1. **Parsing** — `slp_parser.py` uses [py-slippi](https://pypi.org/project/py-slippi/) to read completed `.slp` files. It also includes a lightweight binary reader that extracts `match_id` and `game_number` directly from the game-start command (these fields are not exposed by py-slippi), enabling ranked set tracking and game-mode detection.

2. **Live Monitoring** — `watcher.py` uses [watchdog](https://pypi.org/project/watchdog/) to recursively monitor the replay directory. When a new `.slp` appears, it reads player info from the raw binary header while the game is still in progress, then parses the full file once writing stops.

3. **Data Model** — Each opponent gets a record with total/ranked/unranked W–L, set W–L, per-stage stats, character usage, and a `last_played` timestamp. An overall record aggregates everything. All data is persisted to `winrate_data.json`.

4. **GUI** — `main.py` builds a tkinter interface with a searchable/sortable opponent list, a scrollable detail panel, segmented bar graphs, and inline stage/character icons loaded via Pillow.

---

## License

MIT
