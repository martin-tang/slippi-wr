"""
Slippi History Advanced — live game watcher.

Monitors a Slippi replay directory (recursively) for new .slp files,
detects the current opponent mid-game, and fires callbacks with full
game metadata (ranked/unranked, stage, characters) when games complete.
"""

import os
import time
import threading
from typing import Optional, Callable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from slp_parser import (
    read_live_player_info,
    read_live_match_metadata,
    parse_completed_game,
    char_name,
    stage_name,
)


class SlpWatcher:
    """Watches a replay directory and fires callbacks for live game events.

    Parameters
    ----------
    replay_dir : str
        Path to the Slippi replay directory.
    my_code : str
        The user's connect code (e.g. ``"MOXI#684"``), matched case-insensitively.
    on_game_start : callable(opponent_name, game_mode, opp_char, my_char)
        Called when a new live game is detected.
    on_game_end : callable(opponent_name, i_won, game_mode, stage_id, opp_char_id, my_char_id, match_id, game_number)
        Called when a game finishes with all metadata.
    on_status : callable(msg)
        Called to report status text.
    """

    def __init__(
        self,
        replay_dir: str,
        my_code: str,
        on_game_start: Callable,
        on_game_end: Callable,
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
        self._tracked_opp_char: Optional[int] = None
        self._tracked_my_char: Optional[int] = None
        self._tracked_game_mode: str = "unknown"
        self._tracked_match_id: str = ""
        self._tracked_game_number: int = 0
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
        opp_char = None
        my_char = None
        for p in players:
            code = p["connect_code"]
            if code and self.my_code in code.lower():
                my_char = p["character_id"]
            elif code and self.my_code not in code.lower():
                name = p["display_name"] or "Unknown"
                opp_name = f"{name} ({code})"
                opp_char = p["character_id"]

        if opp_name and path != self._tracked_file:
            self._tracked_file = path
            self._tracked_opponent = opp_name
            self._tracked_opp_char = opp_char
            self._tracked_my_char = my_char
            self._last_size = 0
            self._stable_count = 0

            # Read match metadata
            match_meta = read_live_match_metadata(path)
            if match_meta:
                self._tracked_game_mode = match_meta["game_mode"]
                self._tracked_match_id = match_meta["match_id"]
                self._tracked_game_number = match_meta["game_number"]
            else:
                self._tracked_game_mode = "unknown"
                self._tracked_match_id = ""
                self._tracked_game_number = 0

            self.on_game_start(
                opp_name,
                self._tracked_game_mode,
                opp_char,
                my_char,
            )
            mode_label = self._tracked_game_mode.capitalize()
            self.on_status(f"Game in progress ({mode_label})...")

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

            if self._stable_count >= 3 and self._tracked_opponent:
                self._finalize_game()

    def _finalize_game(self):
        filepath = self._tracked_file
        opponent = self._tracked_opponent
        opp_char = self._tracked_opp_char
        my_char = self._tracked_my_char
        game_mode = self._tracked_game_mode
        match_id = self._tracked_match_id
        game_number = self._tracked_game_number

        self._tracked_file = None
        self._tracked_opponent = None
        self._tracked_opp_char = None
        self._tracked_my_char = None
        self._stable_count = 0

        if filepath is None or opponent is None:
            return

        result = parse_completed_game(filepath)
        i_won = None
        stage_id = 0
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

            stage_id = result.get("stage", 0)
            # Use more accurate char IDs from the full parse
            opp_char = result["characters"].get(opp_port, opp_char or 0)
            my_char = result["characters"].get(my_port, my_char or 0)
            game_mode = result.get("game_mode", game_mode)
            match_id = result.get("match_id", match_id)
            game_number = result.get("game_number", game_number)

        self.on_game_end(
            opponent, i_won, game_mode, stage_id,
            opp_char or 0, my_char or 0,
            match_id, game_number,
        )
        self.on_status("Watching for new games...")


class _SlpHandler(FileSystemEventHandler):
    def __init__(self, watcher: SlpWatcher):
        super().__init__()
        self.watcher = watcher

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            threading.Timer(0.5, self.watcher._on_new_file, args=[event.src_path]).start()

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            if event.src_path.lower().endswith(".slp") and self.watcher._tracked_file is None:
                self.watcher._on_new_file(event.src_path)
