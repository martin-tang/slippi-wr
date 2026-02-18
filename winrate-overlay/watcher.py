"""
Monitors a Slippi replay directory for new .slp files being written, detects
the current opponent mid-game, and updates the win/loss dictionary when
games complete.
"""

import os
import time
import threading
from typing import Optional, Callable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from slp_parser import read_live_player_info, parse_completed_game


class SlpWatcher:
    """Watches a replay directory and fires callbacks for live game events.

    Parameters
    ----------
    replay_dir : str
        Path to the Slippi replay directory.
    my_code : str
        The user's connect code (e.g. ``"NIKK#513"``), matched case-insensitively.
    on_game_start : callable(opponent_name: str)
        Called when a new live game is detected with the opponent's identity.
    on_game_end : callable(opponent_name: str, i_won: bool | None)
        Called when a game finishes.  ``i_won`` is None if indeterminate.
    on_status : callable(msg: str)
        Called to report status text.
    """

    def __init__(
        self,
        replay_dir: str,
        my_code: str,
        on_game_start: Callable[[str], None],
        on_game_end: Callable[[str, Optional[bool]], None],
        on_status: Callable[[str], None],
    ):
        self.replay_dir = replay_dir
        self.my_code = my_code.strip().lower()
        self.on_game_start = on_game_start
        self.on_game_end = on_game_end
        self.on_status = on_status

        self._observer: Optional[Observer] = None
        self._tracked_file: Optional[str] = None
        self._tracked_opponent: Optional[str] = None
        self._last_size: int = 0
        self._stable_count: int = 0
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        if self._observer is not None:
            return

        self._running = True
        handler = _SlpHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, self.replay_dir, recursive=True)
        self._observer.daemon = True
        self._observer.start()

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        self.on_status("Watching for new games...")

    def stop(self):
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def _on_new_file(self, path: str):
        if not path.lower().endswith(".slp"):
            return

        players = read_live_player_info(path)
        if players is None:
            return

        opp_name = None
        for p in players:
            code = p["connect_code"]
            if code and self.my_code not in code.lower():
                name = p["display_name"] or "Unknown"
                cc = code
                opp_name = f"{name} ({cc})"
                break

        if opp_name and path != self._tracked_file:
            self._tracked_file = path
            self._tracked_opponent = opp_name
            self._last_size = 0
            self._stable_count = 0
            self.on_game_start(opp_name)
            self.on_status("Game in progress...")

    def _poll_loop(self):
        """Poll the tracked live file to detect when writing stops (game over)."""
        while self._running:
            time.sleep(1.0)
            if self._tracked_file is None:
                continue

            try:
                size = os.path.getsize(self._tracked_file)
            except OSError:
                continue

            if size == self._last_size:
                self._stable_count += 1
            else:
                self._stable_count = 0
                self._last_size = size

            # File hasn't grown for 3 seconds — game is likely over
            if self._stable_count >= 3 and self._tracked_opponent:
                self._finalize_game()

    def _finalize_game(self):
        filepath = self._tracked_file
        opponent = self._tracked_opponent
        self._tracked_file = None
        self._tracked_opponent = None
        self._stable_count = 0

        if filepath is None or opponent is None:
            return

        result = parse_completed_game(filepath)
        i_won = None
        if result is not None:
            my_port = None
            opp_port = None
            for port, pid in result["players"].items():
                if self.my_code in pid.lower():
                    my_port = port
                else:
                    opp_port = port
            if my_port is not None and result["winner_port"] is not None:
                i_won = result["winner_port"] == my_port

        self.on_game_end(opponent, i_won)
        self.on_status("Watching for new games...")


class _SlpHandler(FileSystemEventHandler):
    def __init__(self, watcher: SlpWatcher):
        super().__init__()
        self.watcher = watcher

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            # Small delay to let Dolphin start writing
            threading.Timer(0.5, self.watcher._on_new_file, args=[event.src_path]).start()

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            if event.src_path.lower().endswith(".slp") and self.watcher._tracked_file is None:
                self.watcher._on_new_file(event.src_path)
