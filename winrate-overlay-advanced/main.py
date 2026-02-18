"""
Slippi History Advanced — desktop application showing detailed Melee win/loss
records, set tracking, stage winrates (segmented bar), character preferences,
and more.  Parses .slp replay files and monitors the replay directory for live
games.

Stack: Python · tkinter · py-slippi · watchdog · Pillow · PyInstaller

Usage:
    python main.py

Requires: py-slippi, watchdog, Pillow  (see requirements.txt)
"""

import json
import os
import sys
import threading
import time as _time_mod
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from slp_parser import (
    build_advanced_winrate,
    char_name,
    stage_name,
    _empty_opponent_record,
    _empty_overall_record,
    _record_game,
)
from watcher import SlpWatcher


# =====================================================================
# Paths  (works both in dev and in a PyInstaller bundle)
# =====================================================================

def _resource_path(relative: str) -> str:
    """Return the absolute path to a bundled resource."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

SAVE_FILE = os.path.join(_APP_DIR, "winrate_data.json")
IMGS_DIR = _resource_path("imgs")


# =====================================================================
# Character / Stage icon mappings
# =====================================================================

CHAR_ICON_MAP: dict[str, str] = {
    "Captain Falcon": "CaptainFalconHeadSSBM.png",
    "Donkey Kong": "DonkeyKongHeadSSBM.png",
    "Fox": "FoxHeadSSBM.png",
    "Mr Game And Watch": "MrGame&WatchHeadSSBM.png",
    "Kirby": "KirbyHeadSSBM.png",
    "Bowser": "BowserHeadSSBM.png",
    "Link": "LinkHeadSSBM.png",
    "Luigi": "LuigiHeadSSBM.png",
    "Mario": "MarioHeadSSBM.png",
    "Marth": "MarthHeadSSBM.png",
    "Mewtwo": "MewtwoHeadSSBM.png",
    "Ness": "NessHeadSSBM.png",
    "Peach": "PeachHeadSSBM.png",
    "Pikachu": "PikachuHeadSSBM.png",
    "Ice Climbers": "IceClimbersHeadSSBM.png",
    "Jigglypuff": "JigglypuffHeadSSBM.png",
    "Samus": "SamusHeadSSBM.png",
    "Yoshi": "YoshiHeadSSBM.png",
    "Zelda": "ZeldaHeadSSBM.png",
    "Sheik": "SheikHeadSSBM.png",
    "Falco": "FalcoHeadSSBM.png",
    "Young Link": "YoungLinkHeadSSBM.png",
    "Dr Mario": "DrMarioHeadSSBM.png",
    "Roy": "RoyHeadSSBM.png",
    "Pichu": "PichuHeadSSBM.png",
    "Ganondorf": "GanondorfHeadSSBM.png",
}

STAGE_ICON_MAP: dict[str, str] = {
    "Fountain Of Dreams": "fountain_of_dreams.png",
    "Pokemon Stadium": "pokemon_stadium.png",
    "Final Destination": "final_destination.png",
    "Yoshis Story": "yoshis_island.png",
    "Battlefield": "battlefield.png",
    "Dream Land N64": "dream_land.png",
}


# =====================================================================
# Icon cache
# =====================================================================

class IconCache:
    """Loads PIL images, resizes them, and caches the resulting PhotoImages."""

    def __init__(self):
        self._cache: dict[str, ImageTk.PhotoImage] = {}

    def get_char_icon(self, cname: str, size: int = 20) -> ImageTk.PhotoImage | None:
        fname = CHAR_ICON_MAP.get(cname)
        if not fname:
            return None
        path = os.path.join(IMGS_DIR, "stock_icons", fname)
        return self._load_square(path, size)

    def get_stage_icon(self, sname: str, max_height: int = 28) -> ImageTk.PhotoImage | None:
        fname = STAGE_ICON_MAP.get(sname)
        if not fname:
            return None
        path = os.path.join(IMGS_DIR, "stages", fname)
        return self._load_fit(path, max_height)

    def _load_square(self, path: str, size: int) -> ImageTk.PhotoImage | None:
        key = f"{path}_{size}x{size}"
        if key in self._cache:
            return self._cache[key]
        if not os.path.isfile(path):
            return None
        try:
            img = Image.open(path).convert("RGBA")
            img = img.resize((size, size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._cache[key] = photo
            return photo
        except Exception:
            return None

    def _load_fit(self, path: str, max_height: int) -> ImageTk.PhotoImage | None:
        key = f"{path}_h{max_height}"
        if key in self._cache:
            return self._cache[key]
        if not os.path.isfile(path):
            return None
        try:
            img = Image.open(path).convert("RGBA")
            ow, oh = img.size
            ratio = max_height / oh
            new_w = int(ow * ratio)
            img = img.resize((new_w, max_height), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._cache[key] = photo
            return photo
        except Exception:
            return None


# =====================================================================
# Theme system
# =====================================================================

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "BG": "#1a1a2e",
        "BG_CARD": "#16213e",
        "BG_ENTRY": "#0f3460",
        "FG": "#e0e0e0",
        "FG_DIM": "#888899",
        "ACCENT": "#00d4aa",
        "WIN_COLOR": "#22c55e",
        "LOSS_COLOR": "#ef4444",
    },
    "light": {
        "BG": "#f0f2f5",
        "BG_CARD": "#ffffff",
        "BG_ENTRY": "#dfe3e8",
        "FG": "#1a1a2e",
        "FG_DIM": "#5a5a6e",
        "ACCENT": "#0077aa",
        "WIN_COLOR": "#16a34a",
        "LOSS_COLOR": "#dc2626",
    },
}

# Module-level colour variables — set by _apply_theme_colors()
BG = "#1a1a2e"
BG_CARD = "#16213e"
BG_ENTRY = "#0f3460"
FG = "#e0e0e0"
FG_DIM = "#888899"
ACCENT = "#00d4aa"
WIN_COLOR = "#22c55e"
LOSS_COLOR = "#ef4444"

BAR_COLORS = [
    "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899",
    "#14b8a6", "#f97316", "#6366f1", "#10b981", "#e11d48",
]


def _apply_theme_colors(theme_name: str):
    """Set the module-level colour variables from the named theme."""
    global BG, BG_CARD, BG_ENTRY, FG, FG_DIM, ACCENT, WIN_COLOR, LOSS_COLOR
    t = THEMES.get(theme_name, THEMES["dark"])
    BG = t["BG"]
    BG_CARD = t["BG_CARD"]
    BG_ENTRY = t["BG_ENTRY"]
    FG = t["FG"]
    FG_DIM = t["FG_DIM"]
    ACCENT = t["ACCENT"]
    WIN_COLOR = t["WIN_COLOR"]
    LOSS_COLOR = t["LOSS_COLOR"]


# =====================================================================
# Persistence
# =====================================================================

def _load_saved_state() -> dict:
    if os.path.isfile(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


# =====================================================================
# Helpers
# =====================================================================

def _wl(wins: int, losses: int) -> str:
    total = wins + losses
    pct = (wins / total * 100) if total > 0 else 0
    return f"{wins}W \u2013 {losses}L  ({pct:.0f}%)"


def _wl_short(wins: int, losses: int) -> str:
    total = wins + losses
    pct = (wins / total * 100) if total > 0 else 0
    return f"{wins}-{losses} ({pct:.0f}%)"


# =====================================================================
# Stage bar graph canvas widget
# =====================================================================

class StageBarGraph(tk.Canvas):
    """Horizontal segmented bar showing per-stage win rates."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("height", 24)
        kwargs.setdefault("bg", BG_CARD)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)
        self._data: dict[str, list[int]] = {}
        self.bind("<Configure>", lambda e: self._draw())

    def set_data(self, stages: dict[str, list[int]]):
        self._data = stages
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or not self._data:
            return

        items = sorted(self._data.items(), key=lambda x: -(x[1][0] + x[1][1]))
        total_games = sum(v[0] + v[1] for v in self._data.values())
        if total_games == 0:
            return

        bar_h = h

        x = 0
        for i, (sname, (sw, sl)) in enumerate(items):
            seg_total = sw + sl
            seg_w = max(1, int(w * seg_total / total_games))
            if i == len(items) - 1:
                seg_w = w - x

            color = BAR_COLORS[i % len(BAR_COLORS)]
            self.create_rectangle(x, 0, x + seg_w, bar_h,
                                  fill=color, outline="")

            pct = (sw / seg_total * 100) if seg_total > 0 else 0
            label = f"{pct:.0f}%"
            if seg_w > 40:
                self.create_text(
                    x + seg_w // 2, bar_h // 2,
                    text=label, fill="white", font=("Segoe UI", 8, "bold"),
                )

            x += seg_w


# =====================================================================
# Settings dialog
# =====================================================================

class SettingsDialog(tk.Toplevel):
    """Modal settings window for theme and favicon preferences."""

    def __init__(self, parent: tk.Tk, app: "SlippiHistoryApp"):
        super().__init__(parent)
        self.app = app
        self.title("Settings")
        self.configure(bg=BG)
        self.geometry("340x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        pad_section = {"padx": 16, "pady": (14, 2)}

        # ---- Theme ----
        tk.Label(self, text="Theme", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", **pad_section)

        self.theme_var = tk.StringVar(value=app.settings.get("theme", "dark"))
        theme_frame = tk.Frame(self, bg=BG)
        theme_frame.pack(anchor="w", padx=16, pady=(0, 10))
        for val, label in [("dark", "\u263e Dark"), ("light", "\u2600 Light")]:
            tk.Radiobutton(
                theme_frame, text=label, variable=self.theme_var, value=val,
                bg=BG, fg=FG, selectcolor=BG_ENTRY,
                activebackground=BG, activeforeground=FG,
                font=("Segoe UI", 10), indicatoron=1,
            ).pack(side="left", padx=(0, 16))

        # ---- Window Icon ----
        tk.Label(self, text="Window Icon", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", **pad_section)

        current_fav = app.settings.get("favicon", "auto")
        self.favicon_var = tk.StringVar(value=current_fav)

        choices = ["auto"] + sorted(CHAR_ICON_MAP.keys())
        fav_frame = tk.Frame(self, bg=BG)
        fav_frame.pack(anchor="w", padx=16, pady=(0, 4))
        menu = tk.OptionMenu(fav_frame, self.favicon_var, *choices)
        menu.configure(
            bg=BG_ENTRY, fg=FG, activebackground=ACCENT,
            activeforeground="#000", font=("Segoe UI", 9),
            highlightthickness=0, relief="flat",
        )
        menu["menu"].configure(
            bg=BG_ENTRY, fg=FG, activebackground=ACCENT,
            activeforeground="#000", font=("Segoe UI", 9),
        )
        menu.pack(side="left")

        # Preview
        self._preview_frame = tk.Frame(self, bg=BG)
        self._preview_frame.pack(anchor="w", padx=16, pady=(6, 0))
        self.favicon_var.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

        # ---- Apply ----
        tk.Button(
            self, text="Apply", command=self._apply,
            bg=ACCENT, fg="#000", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=24, pady=4,
            activebackground="#00b894",
        ).pack(pady=24)

    def _update_preview(self):
        for w in self._preview_frame.winfo_children():
            w.destroy()
        fav = self.favicon_var.get()
        display_name = fav
        if fav == "auto":
            chars = self.app.overall.get("my_chars", {})
            if chars:
                display_name = max(chars, key=chars.get)
                fav = display_name
            else:
                tk.Label(self._preview_frame, text="(no data yet)", bg=BG,
                         fg=FG_DIM, font=("Segoe UI", 9)).pack(side="left")
                return
        icon = self.app.icons.get_char_icon(fav, size=32)
        if icon:
            lbl = tk.Label(self._preview_frame, image=icon, bg=BG)
            lbl.image = icon
            lbl.pack(side="left")
            tk.Label(self._preview_frame, text=f"  {display_name}", bg=BG, fg=FG,
                     font=("Segoe UI", 9)).pack(side="left")

    def _apply(self):
        new_theme = self.theme_var.get()
        new_favicon = self.favicon_var.get()
        old_theme = self.app.settings.get("theme", "dark")

        self.app.settings["theme"] = new_theme
        self.app.settings["favicon"] = new_favicon
        self.app._persist()
        self.destroy()

        self.app._set_favicon()
        if new_theme != old_theme:
            self.app._apply_theme(new_theme)


# =====================================================================
# Main application
# =====================================================================

class SlippiHistoryApp:
    def __init__(self, root: tk.Tk):
        self.root = root

        # Persistent state
        saved = _load_saved_state()
        self.replay_dir: str = saved.get("replay_dir", "")
        self.my_code: str = saved.get("my_code", "")
        self.records: dict[str, dict] = saved.get("records", {})
        self.overall: dict = saved.get("overall", _empty_overall_record())
        self.settings: dict = saved.get("settings", {"theme": "dark", "favicon": "auto"})

        # Apply saved theme BEFORE building any widgets
        _apply_theme_colors(self.settings.get("theme", "dark"))

        self.root.title("Slippi History Advanced")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(520, 480)

        self.watcher: SlpWatcher | None = None
        self.current_opponent: str = ""
        self.icons = IconCache()

        # Track ranked sets live
        self._live_sets: dict[str, list[dict]] = {}

        self._build_ui()
        self._set_favicon()
        self._refresh_opponent_list()
        self._show_overall()

        if self.replay_dir and self.my_code:
            self._start_watcher()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- Top bar: code + directory + import ----
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 4))

        tk.Label(top, text="My Code:", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(side="left")
        self.code_var = tk.StringVar(value=self.my_code)
        self.code_entry = tk.Entry(
            top, textvariable=self.code_var, width=12,
            bg=BG_ENTRY, fg=FG, insertbackground=FG,
            font=("Segoe UI", 10), relief="flat",
        )
        self.code_entry.pack(side="left", padx=(4, 10))

        self.dir_var = tk.StringVar(value=self.replay_dir or "(no dir)")
        self.dir_label = tk.Entry(
            top, textvariable=self.dir_var, state="readonly", width=30,
            bg=BG_ENTRY, fg=FG_DIM, readonlybackground=BG_ENTRY,
            font=("Segoe UI", 9), relief="flat",
        )
        self.dir_label.pack(side="left", fill="x", expand=True)

        self.browse_btn = tk.Button(
            top, text="\u2026", width=3, command=self._browse_dir,
            bg=BG_CARD, fg=FG, relief="flat", activebackground=ACCENT,
        )
        self.browse_btn.pack(side="left", padx=(4, 4))

        self.import_btn = tk.Button(
            top, text="Import", command=self._import_replays,
            bg=ACCENT, fg="#000", relief="flat", font=("Segoe UI", 9, "bold"),
            activebackground="#00b894", padx=10,
        )
        self.import_btn.pack(side="left")

        # ---- Status ----
        self.status_var = tk.StringVar(value="Status: Idle")
        tk.Label(
            self.root, textvariable=self.status_var, bg=BG, fg=FG_DIM,
            font=("Segoe UI", 8), anchor="w",
        ).pack(fill="x", padx=10)

        # ---- Main paned area ----
        pane = tk.PanedWindow(
            self.root, orient="horizontal", bg=BG,
            sashwidth=4, sashrelief="flat",
        )
        pane.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        # ---- Left panel ----
        left = tk.Frame(pane, bg=BG_CARD)
        pane.add(left, width=250)

        tk.Label(
            left, text="Opponents", bg=BG_CARD, fg=ACCENT,
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(fill="x", padx=6, pady=(6, 2))

        # Search
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_opponent_list())
        tk.Entry(
            left, textvariable=self.search_var, bg=BG_ENTRY, fg=FG,
            insertbackground=FG, font=("Segoe UI", 9), relief="flat",
        ).pack(fill="x", padx=6, pady=(0, 4))

        # Sort
        sort_frame = tk.Frame(left, bg=BG_CARD)
        sort_frame.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(sort_frame, text="Sort:", bg=BG_CARD, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self.sort_var = tk.StringVar(value="recent")
        for val, label in [("recent", "Recent"), ("games", "Games"),
                           ("wr", "WR%"), ("name", "Name")]:
            tk.Radiobutton(
                sort_frame, text=label, variable=self.sort_var, value=val,
                command=self._refresh_opponent_list,
                bg=BG_CARD, fg=FG_DIM, selectcolor=BG_ENTRY,
                activebackground=BG_CARD, activeforeground=FG,
                font=("Segoe UI", 8),
            ).pack(side="left", padx=2)

        # Opponent listbox
        list_frame = tk.Frame(left, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.opp_listbox = tk.Listbox(
            list_frame, bg=BG_ENTRY, fg=FG, selectbackground=ACCENT,
            selectforeground="#000", font=("Segoe UI", 9),
            relief="flat", borderwidth=0, activestyle="none",
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.opp_listbox.yview)
        self.opp_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.opp_listbox.pack(side="left", fill="both", expand=True)
        self.opp_listbox.bind("<<ListboxSelect>>", self._on_opponent_select)

        # Bottom buttons
        btn_frame = tk.Frame(left, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=6, pady=(0, 6))

        tk.Button(
            btn_frame, text="Overall", command=self._show_overall,
            bg=BG_ENTRY, fg=FG, relief="flat", font=("Segoe UI", 9),
            activebackground=ACCENT, activeforeground="#000",
        ).pack(fill="x", pady=(0, 3))

        tk.Button(
            btn_frame, text="Export History", command=self._export_history,
            bg=BG_ENTRY, fg=FG, relief="flat", font=("Segoe UI", 9),
            activebackground=ACCENT, activeforeground="#000",
        ).pack(fill="x", pady=(0, 3))

        tk.Button(
            btn_frame, text="\u2699 Settings", command=self._open_settings,
            bg=BG_ENTRY, fg=FG, relief="flat", font=("Segoe UI", 9),
            activebackground=ACCENT, activeforeground="#000",
        ).pack(fill="x")

        # ---- Right panel (scrollable detail) ----
        right = tk.Frame(pane, bg=BG_CARD)
        pane.add(right, width=340)

        self.detail_canvas = tk.Canvas(right, bg=BG_CARD, highlightthickness=0)
        detail_scroll = tk.Scrollbar(right, command=self.detail_canvas.yview)
        self.detail_canvas.config(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side="right", fill="y")
        self.detail_canvas.pack(side="left", fill="both", expand=True)

        self.detail_frame = tk.Frame(self.detail_canvas, bg=BG_CARD)
        self.detail_window = self.detail_canvas.create_window(
            (0, 0), window=self.detail_frame, anchor="nw",
        )

        self.detail_frame.bind("<Configure>", self._on_detail_configure)
        self.detail_canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel scrolling — active when the cursor is over the detail panel
        self.detail_canvas.bind(
            "<Enter>",
            lambda e: self.detail_canvas.bind_all("<MouseWheel>", self._on_mousewheel),
        )
        self.detail_canvas.bind(
            "<Leave>",
            lambda e: self.detail_canvas.unbind_all("<MouseWheel>"),
        )

    # ---- Layout helpers ----

    def _on_detail_configure(self, event):
        self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.detail_canvas.itemconfig(self.detail_window, width=event.width)

    def _on_mousewheel(self, event):
        self.detail_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        # Clamp to top so user can't scroll into empty space above content
        if self.detail_canvas.yview()[0] < 0:
            self.detail_canvas.yview_moveto(0)

    # ------------------------------------------------------------------
    # Opponent list
    # ------------------------------------------------------------------

    def _refresh_opponent_list(self):
        self.opp_listbox.delete(0, "end")
        search = self.search_var.get().strip().lower()
        sort_key = self.sort_var.get()

        items = []
        for name, rec in self.records.items():
            if search and search not in name.lower():
                continue
            w, l = rec.get("total", [0, 0])
            total = w + l
            pct = (w / total * 100) if total > 0 else 0
            last_played = rec.get("last_played", "")
            items.append((name, total, pct, w, l, last_played))

        if sort_key == "recent":
            items.sort(key=lambda x: x[5], reverse=True)
        elif sort_key == "games":
            items.sort(key=lambda x: -x[1])
        elif sort_key == "wr":
            items.sort(key=lambda x: (-x[2], -x[1]))
        elif sort_key == "name":
            items.sort(key=lambda x: x[0].lower())

        for name, total, pct, w, l, _lp in items:
            self.opp_listbox.insert("end", f"{name}  [{w}-{l}]")

        self._opponent_names = [x[0] for x in items]

    def _on_opponent_select(self, event):
        sel = self.opp_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._opponent_names):
            self._show_opponent(self._opponent_names[idx])

    # ------------------------------------------------------------------
    # Detail panel rendering
    # ------------------------------------------------------------------

    def _clear_detail(self):
        for widget in self.detail_frame.winfo_children():
            widget.destroy()
        # Reset scroll to the top so there's no gap above the content
        self.detail_canvas.yview_moveto(0)

    def _add_section_title(self, text: str):
        tk.Label(
            self.detail_frame, text=text, bg=BG_CARD, fg=ACCENT,
            font=("Segoe UI", 11, "bold"), anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 2))

    def _add_stat_row(self, label: str, value: str, bold: bool = False):
        row = tk.Frame(self.detail_frame, bg=BG_CARD)
        row.pack(fill="x", padx=10, pady=1)
        tk.Label(
            row, text=label, bg=BG_CARD, fg=FG_DIM,
            font=("Segoe UI", 9), anchor="w", width=18,
        ).pack(side="left")
        font = ("Segoe UI", 10, "bold") if bold else ("Segoe UI", 10)
        tk.Label(
            row, text=value, bg=BG_CARD, fg=FG,
            font=font, anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def _add_wr_bar(self, wins: int, losses: int):
        """Small inline win/loss bar."""
        total = wins + losses
        if total == 0:
            return
        frame = tk.Frame(self.detail_frame, bg=BG_CARD, height=10)
        frame.pack(fill="x", padx=10, pady=(0, 4))
        canvas = tk.Canvas(frame, height=10, bg=BG_CARD, highlightthickness=0)
        canvas.pack(fill="x")

        def draw(event=None):
            canvas.delete("all")
            w = canvas.winfo_width()
            if w < 2:
                return
            win_w = max(1, int(w * wins / total))
            canvas.create_rectangle(0, 0, win_w, 10, fill=WIN_COLOR, outline="")
            canvas.create_rectangle(win_w, 0, w, 10, fill=LOSS_COLOR, outline="")

        canvas.bind("<Configure>", draw)

    def _add_stage_bar(self, stages: dict[str, list[int]],
                       title: str = "Stage Win Rates",
                       show_images_below_bar: bool = False):
        """Render the stage win-rate section.

        *show_images_below_bar*:
            True  -> opponent view: stage thumbnails under the bar + text list.
            False -> overall view: small inline icons next to each stage name.
        """
        if not stages:
            return
        self._add_section_title(title)
        bar = StageBarGraph(self.detail_frame, width=300)
        bar.pack(fill="x", padx=10, pady=(2, 2))
        bar.set_data(stages)

        items = sorted(stages.items(), key=lambda x: -(x[1][0] + x[1][1]))

        # -- Opponent view: stage image cards underneath the bar --
        if show_images_below_bar:
            img_frame = tk.Frame(self.detail_frame, bg=BG_CARD)
            img_frame.pack(fill="x", padx=10, pady=(2, 4))
            for sname, (sw, sl) in items:
                total = sw + sl
                if total == 0:
                    continue
                pct = (sw / total * 100) if total > 0 else 0
                card = tk.Frame(img_frame, bg=BG_CARD)
                card.pack(side="left", padx=(0, 6), pady=2)
                icon = self.icons.get_stage_icon(sname, max_height=44)
                if icon:
                    lbl = tk.Label(card, image=icon, bg=BG_CARD)
                    lbl.image = icon
                    lbl.pack()
                short = (sname
                         .replace("Fountain Of Dreams", "FoD")
                         .replace("Pokemon Stadium", "PS")
                         .replace("Final Destination", "FD")
                         .replace("Yoshis Story", "YS")
                         .replace("Battlefield", "BF")
                         .replace("Dream Land N64", "DL"))
                tk.Label(card, text=short, bg=BG_CARD, fg=FG_DIM,
                         font=("Segoe UI", 7)).pack()
                tk.Label(card, text=f"{pct:.0f}%  {sw}-{sl}", bg=BG_CARD, fg=FG,
                         font=("Segoe UI", 8)).pack()

        # -- Overall view: inline icons next to each stage name --
        if not show_images_below_bar:
            for sname, (sw, sl) in items:
                total = sw + sl
                if total == 0:
                    continue
                row = tk.Frame(self.detail_frame, bg=BG_CARD)
                row.pack(fill="x", padx=10, pady=1)
                icon = self.icons.get_stage_icon(sname, max_height=18)
                if icon:
                    lbl = tk.Label(row, image=icon, bg=BG_CARD)
                    lbl.image = icon
                    lbl.pack(side="left", padx=(0, 4))
                tk.Label(
                    row, text=sname, bg=BG_CARD, fg=FG_DIM,
                    font=("Segoe UI", 9), anchor="w", width=18,
                ).pack(side="left")
                tk.Label(
                    row, text=_wl_short(sw, sl), bg=BG_CARD, fg=FG,
                    font=("Segoe UI", 10), anchor="w",
                ).pack(side="left", fill="x", expand=True)

    def _add_char_list(self, chars: dict[str, int], title: str):
        if not chars:
            return
        self._add_section_title(title)
        items = sorted(chars.items(), key=lambda x: -x[1])
        for cname, count in items:
            row = tk.Frame(self.detail_frame, bg=BG_CARD)
            row.pack(fill="x", padx=10, pady=1)
            icon = self.icons.get_char_icon(cname, size=20)
            if icon:
                lbl = tk.Label(row, image=icon, bg=BG_CARD)
                lbl.image = icon
                lbl.pack(side="left", padx=(0, 4))
            tk.Label(
                row, text=cname, bg=BG_CARD, fg=FG_DIM,
                font=("Segoe UI", 9), anchor="w", width=18,
            ).pack(side="left")
            tk.Label(
                row, text=f"{count} games", bg=BG_CARD, fg=FG,
                font=("Segoe UI", 10), anchor="w",
            ).pack(side="left", fill="x", expand=True)

    # ------ Overall view ------

    def _show_overall(self):
        self._clear_detail()
        self.current_opponent = ""
        o = self.overall

        self._add_section_title("Overall Stats")
        w, l = o.get("total", [0, 0])
        self._add_stat_row("Total", _wl(w, l), bold=True)
        self._add_wr_bar(w, l)

        rw, rl = o.get("ranked", [0, 0])
        uw, ul = o.get("unranked", [0, 0])
        self._add_stat_row("Ranked", _wl(rw, rl))
        self._add_stat_row("Unranked", _wl(uw, ul))

        sw, sl = o.get("sets", [0, 0])
        self._add_stat_row("Sets (Ranked)", _wl(sw, sl))

        self._add_stat_row("Unique Opponents", str(len(self.records)))

        self._add_stage_bar(o.get("stages", {}), "Overall Stage Win Rates",
                            show_images_below_bar=False)
        self._add_char_list(o.get("my_chars", {}), "My Characters")

    # ------ Per-opponent view ------

    def _show_opponent(self, opp_name: str):
        self._clear_detail()
        self.current_opponent = opp_name
        rec = self.records.get(opp_name, _empty_opponent_record())

        self._add_section_title(opp_name)

        w, l = rec.get("total", [0, 0])
        self._add_stat_row("Total", _wl(w, l), bold=True)
        self._add_wr_bar(w, l)

        rw, rl = rec.get("ranked", [0, 0])
        uw, ul = rec.get("unranked", [0, 0])
        self._add_stat_row("Ranked", _wl(rw, rl))
        self._add_stat_row("Unranked", _wl(uw, ul))

        sw, sl = rec.get("sets", [0, 0])
        self._add_stat_row("Sets (Ranked)", _wl(sw, sl))

        self._add_char_list(rec.get("their_chars", {}), "Their Characters")
        self._add_stage_bar(rec.get("stages", {}), "Stage Win Rates",
                            show_images_below_bar=True)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_dir(self):
        initial = self.replay_dir if self.replay_dir else os.path.expanduser("~")
        path = filedialog.askdirectory(initialdir=initial,
                                       title="Select Slippi Replay Directory")
        if path:
            self.replay_dir = path
            self.dir_var.set(path)
            self._persist()

    def _import_replays(self):
        code = self.code_var.get().strip()
        if not code:
            messagebox.showwarning("Missing Code",
                                   "Enter your connect code first (e.g. MOXI#684).")
            return
        if not self.replay_dir or not os.path.isdir(self.replay_dir):
            messagebox.showwarning("Missing Directory",
                                   "Select a valid replay directory first.")
            return

        self.my_code = code
        self.import_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.status_var.set("Status: Importing replays\u2026")

        def run():
            def progress(cur, total):
                self.root.after(0, lambda: self.status_var.set(
                    f"Status: Importing\u2026 {cur}/{total}"
                ))

            def save(records, overall):
                def do_save():
                    self.records = records
                    self.overall = overall
                    self._persist()
                self.root.after(0, do_save)

            records, overall = build_advanced_winrate(
                self.replay_dir, code,
                progress_callback=progress,
                save_callback=save,
            )
            self.root.after(0, lambda: self._on_import_done(records, overall))

        threading.Thread(target=run, daemon=True).start()

    def _on_import_done(self, records: dict, overall: dict):
        self.records = records
        self.overall = overall
        self.import_btn.config(state="normal")
        self.browse_btn.config(state="normal")

        total_opponents = len(records)
        tw, tl = overall.get("total", [0, 0])
        self.status_var.set(
            f"Status: Imported {tw + tl} games vs {total_opponents} opponents."
        )

        self._persist()
        self._set_favicon()
        self._refresh_opponent_list()
        self._show_overall()
        self._start_watcher()

    def _export_history(self):
        """Save the full history JSON to a user-chosen location."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="slippi_history.json",
            title="Export History",
        )
        if not path:
            return
        try:
            data = {
                "replay_dir": self.replay_dir,
                "my_code": self.my_code,
                "records": self.records,
                "overall": self.overall,
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self.status_var.set(f"Status: History exported to {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Export Error", f"Could not export:\n{exc}")

    def _open_settings(self):
        SettingsDialog(self.root, self)

    def _set_favicon(self):
        """Set the window icon to the chosen (or most-played) character."""
        fav = self.settings.get("favicon", "auto")
        if fav == "auto":
            chars = self.overall.get("my_chars", {})
            if chars:
                fav = max(chars, key=chars.get)
            else:
                return
        icon = self.icons.get_char_icon(fav, size=32)
        if icon:
            try:
                self.root.iconphoto(True, icon)
            except Exception:
                pass

    def _apply_theme(self, theme_name: str):
        """Live-swap the theme by rebuilding all widgets."""
        _apply_theme_colors(theme_name)
        # Clear the icon cache so widgets pick up new bg colours if needed
        self.icons = IconCache()
        # Destroy all children and rebuild
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self._build_ui()
        self._set_favicon()
        self._refresh_opponent_list()
        if self.current_opponent:
            self._show_opponent(self.current_opponent)
        else:
            self._show_overall()

    def _start_watcher(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

        if not self.replay_dir or not self.my_code:
            return

        self.watcher = SlpWatcher(
            replay_dir=self.replay_dir,
            my_code=self.my_code,
            on_game_start=self._on_game_start,
            on_game_end=self._on_game_end,
            on_status=self._on_watcher_status,
        )
        self.watcher.start()

    # ------------------------------------------------------------------
    # Watcher callbacks
    # ------------------------------------------------------------------

    def _on_game_start(self, opponent_name: str, game_mode: str,
                       opp_char: int | None, my_char: int | None):
        def update():
            self.current_opponent = opponent_name
            mode = game_mode.capitalize()
            char_str = char_name(opp_char) if opp_char is not None else "?"
            self.status_var.set(f"Playing: {opponent_name} ({mode}) \u2014 {char_str}")
            self._show_opponent(opponent_name)
        self.root.after(0, update)

    def _on_game_end(self, opponent_name: str, i_won: bool | None,
                     game_mode: str, stage_id: int,
                     opp_char_id: int, my_char_id: int,
                     match_id: str, game_number: int):
        def update():
            now = _time_mod.strftime("%Y-%m-%dT%H:%M:%S", _time_mod.gmtime())
            _record_game(
                self.records, self.overall, opponent_name, i_won,
                game_mode, stage_id, opp_char_id, my_char_id,
                timestamp=now,
            )

            if game_mode == "ranked" and match_id:
                if match_id not in self._live_sets:
                    self._live_sets[match_id] = []
                self._live_sets[match_id].append({
                    "i_won": i_won,
                    "game_number": game_number,
                })
                self._check_live_set(match_id, opponent_name)

            self._persist()
            self._refresh_opponent_list()

            if self.current_opponent == opponent_name:
                self._show_opponent(opponent_name)
            elif self.current_opponent == "":
                self._show_overall()
        self.root.after(0, update)

    def _check_live_set(self, match_id: str, opponent_name: str):
        """Check if a live ranked set has been decided (first to 2 wins)."""
        games = self._live_sets[match_id]
        my_wins = sum(1 for g in games if g["i_won"] is True)
        opp_wins = sum(1 for g in games if g["i_won"] is False)

        if opponent_name not in self.records:
            self.records[opponent_name] = _empty_opponent_record()

        if my_wins >= 2:
            self.records[opponent_name]["sets"][0] += 1
            self.overall["sets"][0] += 1
            del self._live_sets[match_id]
        elif opp_wins >= 2:
            self.records[opponent_name]["sets"][1] += 1
            self.overall["sets"][1] += 1
            del self._live_sets[match_id]

    def _on_watcher_status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(f"Status: {msg}"))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self):
        _save_state({
            "replay_dir": self.replay_dir,
            "my_code": self.my_code,
            "records": self.records,
            "overall": self.overall,
            "settings": self.settings,
        })

    def on_close(self):
        if self.watcher:
            self.watcher.stop()
        self._persist()
        self.root.destroy()


# =====================================================================
# Entry point
# =====================================================================

def main():
    root = tk.Tk()
    app = SlippiHistoryApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)

    # Centre on screen
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()
