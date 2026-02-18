"""
Slippi History Advanced — .slp replay parser.

Extracts player identities, game outcomes, match_id (ranked/unranked),
game_number (for set tracking), stage, and character IDs.

Uses py-slippi for completed game analysis, and includes a lightweight binary
parser for reading player info + match metadata from live (in-progress) files.
"""

import os
import time
import unicodedata
from typing import Optional

from slippi import Game
from slippi.id import CSSCharacter, Stage

# ---------------------------------------------------------------------------
# Character / Stage name helpers
# ---------------------------------------------------------------------------

# game.start.players[port].character uses CSS (Character Select Screen) IDs,
# NOT the InGameCharacter IDs.  CSSCharacter is the correct enum here.
CHARACTER_NAMES: dict[int, str] = {}
for _c in CSSCharacter:
    CHARACTER_NAMES[_c.value] = _c.name.replace("_", " ").title()

STAGE_NAMES: dict[int, str] = {}
for _s in Stage:
    STAGE_NAMES[_s.value] = _s.name.replace("_", " ").title()


def char_name(char_id: int) -> str:
    return CHARACTER_NAMES.get(char_id, f"Unknown ({char_id})")


def stage_name(stage_id: int) -> str:
    return STAGE_NAMES.get(stage_id, f"Unknown ({stage_id})")


# ---------------------------------------------------------------------------
# Binary reader for match_id / game_number (not exposed by py-slippi)
# ---------------------------------------------------------------------------

_MATCH_ID_OFFSET = 0x2BE
_MATCH_ID_LEN = 51
_GAME_NUMBER_OFFSET = 0x2F1


def _read_game_start_buf(filepath: str) -> Optional[bytes]:
    """Return the raw game-start command buffer from a .slp file, or None."""
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except (OSError, PermissionError):
        return None

    if len(data) < 16:
        return None

    if data[0] == 0x36:
        raw_pos = 0
    elif data[0:1] == b"{":
        raw_pos = 15
    else:
        return None

    if raw_pos >= len(data) or data[raw_pos] != 0x35:
        return None

    payload_len = data[raw_pos + 1]
    msg_sizes: dict[int, int] = {}
    sizes_buf = data[raw_pos + 2: raw_pos + 2 + payload_len - 1]
    for i in range(0, len(sizes_buf) - 2, 3):
        cmd = sizes_buf[i]
        size = (sizes_buf[i + 1] << 8) | sizes_buf[i + 2]
        msg_sizes[cmd] = size

    game_start_size = msg_sizes.get(0x36)
    if game_start_size is None:
        return None

    gs_offset = raw_pos + 1 + payload_len
    gs_end = gs_offset + 1 + game_start_size
    if gs_end > len(data):
        return None

    if data[gs_offset] != 0x36:
        return None

    return data[gs_offset: gs_end]


def read_match_metadata(filepath: str) -> Optional[dict]:
    """Read match_id and game_number from the binary game-start command.

    Returns ``{"match_id": str, "game_number": int, "game_mode": str}``
    where game_mode is ``"ranked"``, ``"unranked"``, or ``"unknown"``.
    """
    buf = _read_game_start_buf(filepath)
    if buf is None:
        return None

    if _MATCH_ID_OFFSET + _MATCH_ID_LEN > len(buf):
        return None

    match_id_raw = buf[_MATCH_ID_OFFSET: _MATCH_ID_OFFSET + _MATCH_ID_LEN]
    match_id = match_id_raw.split(b"\x00")[0].decode("ascii", errors="replace")

    game_number = 0
    if _GAME_NUMBER_OFFSET + 4 <= len(buf):
        game_number = int.from_bytes(
            buf[_GAME_NUMBER_OFFSET: _GAME_NUMBER_OFFSET + 4], "big"
        )

    if match_id.startswith("mode.ranked"):
        game_mode = "ranked"
    elif match_id.startswith("mode.unranked"):
        game_mode = "unranked"
    else:
        game_mode = "unknown"

    return {
        "match_id": match_id,
        "game_number": game_number,
        "game_mode": game_mode,
    }


# ---------------------------------------------------------------------------
# Lightweight binary reader for live / partial .slp files
# ---------------------------------------------------------------------------

_DISPLAY_NAME_START = 0x1A5
_DISPLAY_NAME_LEN = 0x1F
_CONNECT_CODE_START = 0x221
_CONNECT_CODE_LEN = 0x0A
_PLAYER_TYPE_OFFSET = 0x66
_PLAYER_BLOCK_STRIDE = 0x24


def _decode_slp_string(raw: bytes) -> str:
    text = raw.split(b"\x00")[0].decode("cp932", errors="replace")
    return unicodedata.normalize("NFKC", text)


def read_live_player_info(filepath: str) -> Optional[list[dict]]:
    """Read player info from a potentially still-being-written .slp file.

    Returns a list of dicts with ``port``, ``display_name``,
    ``connect_code``, ``character_id``, or None if unreadable.
    """
    buf = _read_game_start_buf(filepath)
    if buf is None:
        return None

    players = []
    for port in range(4):
        type_off = _PLAYER_TYPE_OFFSET + port * _PLAYER_BLOCK_STRIDE
        if type_off >= len(buf):
            continue
        if buf[type_off] == 3:  # empty slot
            continue

        char_off = 0x65 + port * _PLAYER_BLOCK_STRIDE
        char_id = buf[char_off] if char_off < len(buf) else None

        dn_start = _DISPLAY_NAME_START + port * _DISPLAY_NAME_LEN
        dn_end = dn_start + _DISPLAY_NAME_LEN
        display_name = _decode_slp_string(buf[dn_start:dn_end]) if dn_end <= len(buf) else ""

        cc_start = _CONNECT_CODE_START + port * _CONNECT_CODE_LEN
        cc_end = cc_start + _CONNECT_CODE_LEN
        connect_code = _decode_slp_string(buf[cc_start:cc_end]) if cc_end <= len(buf) else ""

        players.append({
            "port": port,
            "display_name": display_name,
            "connect_code": connect_code,
            "character_id": char_id,
        })

    return players if players else None


def read_live_match_metadata(filepath: str) -> Optional[dict]:
    """Read match_id, game_number, game_mode, and stage from a live file."""
    buf = _read_game_start_buf(filepath)
    if buf is None:
        return None

    # match_id
    if _MATCH_ID_OFFSET + _MATCH_ID_LEN > len(buf):
        return None
    match_id_raw = buf[_MATCH_ID_OFFSET: _MATCH_ID_OFFSET + _MATCH_ID_LEN]
    match_id = match_id_raw.split(b"\x00")[0].decode("ascii", errors="replace")

    game_number = 0
    if _GAME_NUMBER_OFFSET + 4 <= len(buf):
        game_number = int.from_bytes(buf[_GAME_NUMBER_OFFSET: _GAME_NUMBER_OFFSET + 4], "big")

    if match_id.startswith("mode.ranked"):
        game_mode = "ranked"
    elif match_id.startswith("mode.unranked"):
        game_mode = "unranked"
    else:
        game_mode = "unknown"

    # stage is at a fixed offset in the game-start command
    # py-slippi reads it from the event; we grab it from metadata.
    # For live files we'll leave stage to be filled after game finishes.
    return {
        "match_id": match_id,
        "game_number": game_number,
        "game_mode": game_mode,
    }


# ---------------------------------------------------------------------------
# Full game analysis using py-slippi
# ---------------------------------------------------------------------------

def _get_player_id(game: Game, port: int) -> Optional[str]:
    """Return ``"DisplayName (CODE#123)"`` for the player at *port*."""
    meta = game.metadata
    if meta and meta.players:
        mp = meta.players[port]
        if mp and mp.netplay and mp.netplay.code:
            name = mp.netplay.name or "Unknown"
            return f"{name} ({mp.netplay.code})"

    p = game.start.players[port]
    if p and p.tag:
        return p.tag
    return f"Player (Port {port + 1})"


def _determine_winner_port(game: Game) -> Optional[int]:
    """Return the port index of the winner, or None if indeterminate."""
    end = game.end
    if end is None:
        return None

    method = end.method.value
    active_ports = [
        i for i, p in enumerate(game.start.players)
        if p is not None and p.type is not None
    ]
    if len(active_ports) != 2:
        return None

    # NO_CONTEST — winner is the player who did NOT quit
    if method == 7:
        lras = end.lras_initiator
        if lras is not None and lras in active_ports:
            return [p for p in active_ports if p != lras][0]
        return None

    # GAME / TIME / CONCLUSIVE
    if method in (1, 2, 3):
        last_frame = game.frames[-1] if game.frames else None
        if last_frame is None:
            return None

        port_data = []
        for p in active_ports:
            fp = last_frame.ports[p]
            if fp is None:
                return None
            stocks = fp.leader.post.stocks
            damage = fp.leader.post.damage
            port_data.append((p, stocks, damage))

        p0, s0, d0 = port_data[0]
        p1, s1, d1 = port_data[1]

        if s0 > s1:
            return p0
        if s1 > s0:
            return p1
        if d0 < d1:
            return p0
        if d1 < d0:
            return p1

    return None


def parse_completed_game(filepath: str) -> Optional[dict]:
    """Parse a completed .slp file and return rich game data.

    Returns::

        {
            "players": { port: "DisplayName (CODE#123)", ... },
            "winner_port": int | None,
            "active_ports": [int, ...],
            "stage": int,               # Stage enum value
            "characters": { port: int, ... },  # InGameCharacter values
            "game_mode": "ranked" | "unranked" | "unknown",
            "match_id": str,
            "game_number": int,
        }

    Returns None if the file can't be parsed or isn't a 1v1.
    """
    try:
        game = Game(filepath)
    except Exception:
        return None

    if game.start is None or game.end is None:
        return None

    active_ports = [
        i for i, p in enumerate(game.start.players)
        if p is not None and p.type is not None
    ]
    if len(active_ports) != 2:
        return None

    players = {}
    characters = {}
    for port in active_ports:
        pid = _get_player_id(game, port)
        if pid:
            players[port] = pid
        p = game.start.players[port]
        if p is not None:
            characters[port] = p.character.value if hasattr(p.character, 'value') else int(p.character)

    if len(players) != 2:
        return None

    winner_port = _determine_winner_port(game)

    # Stage
    stage_val = game.start.stage
    if hasattr(stage_val, 'value'):
        stage_val = stage_val.value
    stage_id = int(stage_val) if stage_val is not None else 0

    # Match metadata from binary
    match_meta = read_match_metadata(filepath)
    game_mode = match_meta["game_mode"] if match_meta else "unknown"
    match_id = match_meta["match_id"] if match_meta else ""
    game_number = match_meta["game_number"] if match_meta else 0

    # Timestamp from metadata (ISO string) or file modification time
    timestamp = ""
    if game.metadata and game.metadata.date:
        timestamp = game.metadata.date.isoformat()
    else:
        try:
            timestamp = time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.gmtime(os.path.getmtime(filepath)),
            )
        except OSError:
            pass

    return {
        "players": players,
        "winner_port": winner_port,
        "active_ports": active_ports,
        "stage": stage_id,
        "characters": characters,
        "game_mode": game_mode,
        "match_id": match_id,
        "game_number": game_number,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Build the full advanced winrate data
# ---------------------------------------------------------------------------

def _empty_opponent_record() -> dict:
    """Return a fresh per-opponent record structure."""
    return {
        "total": [0, 0],
        "ranked": [0, 0],
        "unranked": [0, 0],
        "sets": [0, 0],
        "stages": {},
        "their_chars": {},
        "last_played": "",
    }


def _empty_overall_record() -> dict:
    """Return a fresh overall (aggregate) record structure."""
    return {
        "total": [0, 0],
        "ranked": [0, 0],
        "unranked": [0, 0],
        "sets": [0, 0],
        "stages": {},
        "my_chars": {},
    }


def _record_game(
    records: dict,
    overall: dict,
    opp_name: str,
    i_won: Optional[bool],
    game_mode: str,
    stage_id: int,
    opp_char_id: int,
    my_char_id: int,
    timestamp: str = "",
):
    """Update records and overall dicts with a single game result."""
    if opp_name not in records:
        records[opp_name] = _empty_opponent_record()
    rec = records[opp_name]

    # Update last_played if this game is newer
    if timestamp and timestamp > rec.get("last_played", ""):
        rec["last_played"] = timestamp

    s_name = stage_name(stage_id)
    opp_c = char_name(opp_char_id)
    my_c = char_name(my_char_id)

    # Character tracking
    rec["their_chars"][opp_c] = rec["their_chars"].get(opp_c, 0) + 1
    overall["my_chars"][my_c] = overall["my_chars"].get(my_c, 0) + 1

    if i_won is None:
        return  # indeterminate — only count char appearances

    idx = 0 if i_won else 1

    # Total
    rec["total"][idx] += 1
    overall["total"][idx] += 1

    # Mode-specific
    if game_mode == "ranked":
        rec["ranked"][idx] += 1
        overall["ranked"][idx] += 1
    elif game_mode == "unranked":
        rec["unranked"][idx] += 1
        overall["unranked"][idx] += 1

    # Stage
    if s_name not in rec["stages"]:
        rec["stages"][s_name] = [0, 0]
    rec["stages"][s_name][idx] += 1
    if s_name not in overall["stages"]:
        overall["stages"][s_name] = [0, 0]
    overall["stages"][s_name][idx] += 1


def _compute_sets(
    set_games: dict[str, list[dict]],
    records: dict,
    overall: dict,
    my_code_lower: str,
):
    """Compute set wins/losses from grouped ranked games.

    *set_games* maps match_id → list of game result dicts (sorted by
    game_number).  Only ranked games should be included.
    """
    for match_id, games in set_games.items():
        games.sort(key=lambda g: g["game_number"])

        my_wins = 0
        opp_wins = 0
        opp_name = None

        for g in games:
            for port, pid in g["players"].items():
                if my_code_lower not in pid.lower():
                    opp_name = pid
                    break

            winner = g["winner_port"]
            if winner is None:
                continue

            my_port = None
            for port, pid in g["players"].items():
                if my_code_lower in pid.lower():
                    my_port = port
                    break

            if my_port is not None:
                if winner == my_port:
                    my_wins += 1
                else:
                    opp_wins += 1

            if my_wins >= 2 or opp_wins >= 2:
                break

        if opp_name is None:
            continue

        if opp_name not in records:
            records[opp_name] = _empty_opponent_record()

        if my_wins >= 2:
            records[opp_name]["sets"][0] += 1
            overall["sets"][0] += 1
        elif opp_wins >= 2:
            records[opp_name]["sets"][1] += 1
            overall["sets"][1] += 1
        # Incomplete sets (e.g. disconnect) are not counted


def build_advanced_winrate(
    replay_dir: str,
    my_code: str,
    progress_callback=None,
    save_callback=None,
) -> tuple[dict, dict]:
    """Scan replay_dir recursively and build advanced winrate data.

    Returns ``(records, overall)`` where:
    - records: ``{ "Opponent (CODE)": { per-opponent data } }``
    - overall: ``{ aggregate data across all opponents }``
    """
    my_code_lower = my_code.strip().lower()
    records: dict[str, dict] = {}
    overall = _empty_overall_record()

    # Collect ranked games for set analysis
    ranked_sets: dict[str, list[dict]] = {}

    # Recursively find all .slp files
    slp_files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(replay_dir):
        for fname in filenames:
            if fname.lower().endswith(".slp"):
                slp_files.append(os.path.join(dirpath, fname))
    total = len(slp_files)

    for idx, fpath in enumerate(slp_files):
        result = parse_completed_game(fpath)
        if progress_callback:
            progress_callback(idx + 1, total)
        if result is None:
            continue

        # Identify self vs opponent
        my_port = None
        opp_port = None
        for port, pid in result["players"].items():
            if my_code_lower in pid.lower():
                my_port = port
            else:
                opp_port = port

        if my_port is None or opp_port is None:
            continue

        opp_name = result["players"][opp_port]
        winner = result["winner_port"]
        i_won = None
        if winner == my_port:
            i_won = True
        elif winner == opp_port:
            i_won = False

        my_char = result["characters"].get(my_port, 0)
        opp_char = result["characters"].get(opp_port, 0)

        _record_game(
            records, overall, opp_name, i_won,
            result["game_mode"], result["stage"],
            opp_char, my_char,
            timestamp=result.get("timestamp", ""),
        )

        # Accumulate ranked games for set tracking
        if result["game_mode"] == "ranked" and result["match_id"]:
            mid = result["match_id"]
            if mid not in ranked_sets:
                ranked_sets[mid] = []
            ranked_sets[mid].append(result)

        # Periodic save
        if save_callback and (idx + 1) % 100 == 0:
            save_callback(records, overall)

    # Compute set W/L from grouped ranked games
    _compute_sets(ranked_sets, records, overall, my_code_lower)

    # Final save
    if save_callback:
        save_callback(records, overall)

    return records, overall
