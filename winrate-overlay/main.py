"""
Slippi Winrate Overlay — a small desktop window that displays your win/loss
record against the player you're currently facing in Slippi/Dolphin.

Usage:
    python main.py

Requires: py-slippi, watchdog  (see requirements.txt)
"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from slp_parser import build_winrate_dict
from watcher import SlpWatcher

SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "winrate_data.json")


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


class WinrateApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Slippi Winrate Overlay")
        self.root.resizable(False, False)

        # Persistent state
        saved = _load_saved_state()
        self.replay_dir: str = saved.get("replay_dir", "")
        self.my_code: str = saved.get("my_code", "")
        self.records: dict[str, list[int]] = saved.get("records", {})

        self.watcher: SlpWatcher | None = None
        self.current_opponent: str = ""

        self._build_ui()
        self._update_current_player_display()

        if self.replay_dir and self.my_code:
            self._start_watcher()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- Row 0: Connect code ---
        row_code = tk.Frame(self.root)
        row_code.pack(fill="x", **pad)

        tk.Label(row_code, text="My Code:").pack(side="left")
        self.code_var = tk.StringVar(value=self.my_code)
        self.code_entry = tk.Entry(row_code, textvariable=self.code_var, width=14)
        self.code_entry.pack(side="left", padx=(4, 0))

        # --- Row 1: Replay directory ---
        row_dir = tk.Frame(self.root)
        row_dir.pack(fill="x", **pad)

        self.dir_var = tk.StringVar(value=self.replay_dir or "(no directory selected)")
        self.dir_label = tk.Entry(row_dir, textvariable=self.dir_var, state="readonly", width=40)
        self.dir_label.pack(side="left", fill="x", expand=True)

        self.browse_btn = tk.Button(row_dir, text="...", width=3, command=self._browse_dir)
        self.browse_btn.pack(side="left", padx=(4, 4))

        self.import_btn = tk.Button(row_dir, text="Import", command=self._import_replays)
        self.import_btn.pack(side="left")

        # --- Row 2: Current player / record ---
        row_player = tk.Frame(self.root)
        row_player.pack(fill="x", **pad)

        self.player_var = tk.StringVar(value="Current player: —")
        tk.Label(row_player, textvariable=self.player_var, font=("Segoe UI", 11, "bold"),
                 anchor="w").pack(fill="x")

        # --- Row 3: Win/Loss ---
        row_record = tk.Frame(self.root)
        row_record.pack(fill="x", **pad)

        self.record_var = tk.StringVar(value="")
        tk.Label(row_record, textvariable=self.record_var, font=("Segoe UI", 13),
                 anchor="w").pack(fill="x")

        # --- Row 4: Status ---
        row_status = tk.Frame(self.root)
        row_status.pack(fill="x", **pad)

        self.status_var = tk.StringVar(value="Status: Idle")
        tk.Label(row_status, textvariable=self.status_var, fg="gray",
                 anchor="w").pack(fill="x")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_dir(self):
        initial = self.replay_dir if self.replay_dir else os.path.expanduser("~")
        path = filedialog.askdirectory(initialdir=initial, title="Select Slippi Replay Directory")
        if path:
            self.replay_dir = path
            self.dir_var.set(path)
            self._persist()

    def _import_replays(self):
        code = self.code_var.get().strip()
        if not code:
            messagebox.showwarning("Missing Code", "Enter your connect code first (e.g. NIKK#513).")
            return
        if not self.replay_dir or not os.path.isdir(self.replay_dir):
            messagebox.showwarning("Missing Directory", "Select a valid replay directory first.")
            return

        self.my_code = code
        self.import_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.status_var.set("Status: Importing replays...")

        def run():
            def progress(cur, total):
                self.root.after(0, lambda: self.status_var.set(f"Status: Importing... {cur}/{total}"))

            def save(records):
                # Update records on the main thread and persist to disk
                def do_save():
                    self.records = records
                    self._persist()
                self.root.after(0, do_save)

            records = build_winrate_dict(
                self.replay_dir, code,
                progress_callback=progress,
                save_callback=save,
            )
            self.root.after(0, lambda: self._on_import_done(records))

        threading.Thread(target=run, daemon=True).start()

    def _on_import_done(self, records: dict[str, list[int]]):
        self.records = records
        self.import_btn.config(state="normal")
        self.browse_btn.config(state="normal")

        total_opponents = len(records)
        total_games = sum(w + l for w, l in records.values())
        self.status_var.set(f"Status: Imported {total_games} games vs {total_opponents} opponents.")

        self._persist()
        self._update_current_player_display()
        self._start_watcher()

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

    def _on_game_start(self, opponent_name: str):
        self.root.after(0, lambda: self._set_current_opponent(opponent_name))

    def _on_game_end(self, opponent_name: str, i_won: bool | None):
        def update():
            if opponent_name not in self.records:
                self.records[opponent_name] = [0, 0]
            if i_won is True:
                self.records[opponent_name][0] += 1
            elif i_won is False:
                self.records[opponent_name][1] += 1
            self._persist()
            self._update_current_player_display()
        self.root.after(0, update)

    def _on_watcher_status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(f"Status: {msg}"))

    def _set_current_opponent(self, name: str):
        self.current_opponent = name
        self._update_current_player_display()

    def _update_current_player_display(self):
        opp = self.current_opponent
        if not opp:
            self.player_var.set("Current player: —")
            self.record_var.set("")
            return

        self.player_var.set(f"Current player: {opp}")
        rec = self.records.get(opp, [0, 0])
        wins, losses = rec
        total = wins + losses
        pct = (wins / total * 100) if total > 0 else 0
        self.record_var.set(f"Wins: {wins}    Losses: {losses}    ({pct:.0f}% winrate)")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self):
        _save_state({
            "replay_dir": self.replay_dir,
            "my_code": self.my_code,
            "records": self.records,
        })

    def on_close(self):
        if self.watcher:
            self.watcher.stop()
        self._persist()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = WinrateApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)

    # Centre the window on screen
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()
