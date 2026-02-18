"""
Parses .slp replay files to extract player identities, game mode
(ranked / unranked), and game outcomes.

Uses py-slippi for completed game analysis, and includes a lightweight binary
parser for reading player info from live (in-progress) replay files where the
metadata block hasn't been written yet.
"""

import os
import unicodedata
from typing import Optional

from slippi import Game


# ---------------------------------------------------------------------------
# Lightweight binary reader for live / partial .slp files
# ---------------------------------------------------------------------------

def _decode_slp_string(raw: bytes) -> str:
    """Decode a null-terminated Shift-JIS string from a .slp file,
    converting fullwidth characters to their ASCII equivalents."""
    text = raw.split(b"\x00")[0].decode("cp932", errors="replace")
    return unicodedata.normalize("NFKC", text)


# Offsets within the GAME_START command buffer (including the 0x36 command byte
# at position 0).  These match the slippi-js slpReader.ts source exactly.
_DISPLAY_NAME_START = 0x1A5
_DISPLAY_NAME_LEN = 0x1F
_CONNECT_CODE_START = 0x221
_CONNECT_CODE_LEN = 0x0A
_PLAYER_TYPE_OFFSET = 0x66
_PLAYER_BLOCK_STRIDE = 0x24
_SESSION_ID_START = 0x2BE
_SESSION_ID_LEN = 51


def _read_game_start_buffer(filepath: str) -> Optional[bytes]:
    """Read the raw GAME_START command buffer from a .slp file.
    Works on both complete and partial (live) files."""
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


def read_game_mode(filepath: str) -> str:
    """Return ``"ranked"``, ``"unranked"``, or ``"other"`` based on the
    session ID embedded in the game-start command."""
    buf = _read_game_start_buffer(filepath)
    if buf is None:
        return "other"

    sid_end = _SESSION_ID_START + _SESSION_ID_LEN
    if sid_end > len(buf):
        return "other"

    try:
        session_id = buf[_SESSION_ID_START:sid_end].split(b"\x00")[0].decode("utf-8")
    except UnicodeDecodeError:
        return "other"

    if session_id.startswith("mode.ranked"):
        return "ranked"
    if session_id.startswith("mode.unranked"):
        return "unranked"
    return "other"


def read_live_player_info(filepath: str) -> Optional[list[dict]]:
    """Read display names and connect codes directly from the game-start
    command of a .slp file that may still be in the process of being written.

    Returns a list of dicts with keys ``port``, ``display_name``,
    ``connect_code``, and ``character_id`` for each active player,
    or *None* if the file can't be read yet.
    """
    buf = _read_game_start_buffer(filepath)
    if buf is None:
        return None

    players = []
    for port in range(4):
        type_off = _PLAYER_TYPE_OFFSET + port * _PLAYER_BLOCK_STRIDE
        if type_off >= len(buf):
            continue
        ptype = buf[type_off]
        # type 3 = empty slot
        if ptype == 3:
            continue

        char_off = 0x65 + port * _PLAYER_BLOCK_STRIDE
        char_id = buf[char_off] if char_off < len(buf) else None

        dn_start = _DISPLAY_NAME_START + port * _DISPLAY_NAME_LEN
        dn_end = dn_start + _DISPLAY_NAME_LEN
        if dn_end <= len(buf):
            display_name = _decode_slp_string(buf[dn_start:dn_end])
        else:
            display_name = ""

        cc_start = _CONNECT_CODE_START + port * _CONNECT_CODE_LEN
        cc_end = cc_start + _CONNECT_CODE_LEN
        if cc_end <= len(buf):
            connect_code = _decode_slp_string(buf[cc_start:cc_end])
        else:
            connect_code = ""

        players.append({
            "port": port,
            "display_name": display_name,
            "connect_code": connect_code,
            "character_id": char_id,
        })

    return players if players else None


# ---------------------------------------------------------------------------
# Full game analysis using py-slippi
# ---------------------------------------------------------------------------

def _get_player_id(game: Game, port: int) -> Optional[str]:
    """Return ``"DisplayName (CODE#123)"`` for the player at *port*, pulling
    from metadata netplay info first, falling back to game-start tag, then
    a generic port label as last resort."""
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

    # GAME / CONCLUSIVE / TIME
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
        # Tied stocks — lower damage wins
        if d0 < d1:
            return p0
        if d1 < d0:
            return p1

    return None


def parse_completed_game(filepath: str) -> Optional[dict]:
    """Parse a completed .slp file and return a dict with::

        {
            "players": { port: "DisplayName (CODE#123)", ... },
            "winner_port": int or None,
            "active_ports": [int, ...],
            "mode": "ranked" | "unranked" | "other",
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
    for port in active_ports:
        pid = _get_player_id(game, port)
        if pid:
            players[port] = pid

    if len(players) != 2:
        return None

    winner_port = _determine_winner_port(game)
    mode = read_game_mode(filepath)

    return {
        "players": players,
        "winner_port": winner_port,
        "active_ports": active_ports,
        "mode": mode,
    }


def _collect_slp_files(replay_dir: str) -> list[str]:
    """Recursively find all .slp files under *replay_dir*."""
    slp_files = []
    for dirpath, _dirnames, filenames in os.walk(replay_dir):
        for fname in filenames:
            if fname.lower().endswith(".slp"):
                slp_files.append(os.path.join(dirpath, fname))
    return slp_files


def build_winrate_dict(
    replay_dir: str,
    my_code: str,
    progress_callback=None,
) -> dict[str, dict[str, list[int]]]:
    """Scan *replay_dir* (recursively) for ``.slp`` files and build a
    win/loss dictionary.

    *my_code* should be a substring that appears in the user's player-id
    string (e.g. ``"NIKK#513"``).  It is matched case-insensitively.

    Returns::

        {
            "Opponent (CODE#123)": {
                "ranked":   [wins, losses],
                "unranked": [wins, losses],
            },
            ...
        }

    *progress_callback*, if provided, is called with ``(current, total)``
    after each file.
    """
    my_code_lower = my_code.strip().lower()
    records: dict[str, dict[str, list[int]]] = {}

    slp_files = _collect_slp_files(replay_dir)
    total = len(slp_files)

    for idx, fpath in enumerate(slp_files):
        result = parse_completed_game(fpath)
        if progress_callback:
            progress_callback(idx + 1, total)
        if result is None:
            continue

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
        mode = result["mode"]
        if mode not in ("ranked", "unranked"):
            continue

        if opp_name not in records:
            records[opp_name] = {"ranked": [0, 0], "unranked": [0, 0]}

        winner = result["winner_port"]
        if winner == my_port:
            records[opp_name][mode][0] += 1
        elif winner == opp_port:
            records[opp_name][mode][1] += 1

    return records
