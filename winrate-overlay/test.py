"""
Tests for the slp_parser module using sample .slp files from the repo.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from slp_parser import (
    read_live_player_info,
    read_game_mode,
    parse_completed_game,
    build_winrate_dict,
    _collect_slp_files,
)

SLP_DIR = os.path.join(os.path.dirname(__file__), "..", "slp")

failed = 0
passed = 0


def check(name, condition, detail=""):
    global failed, passed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")


# ---------------------------------------------------------------
# Test 1: read_live_player_info on a file with connect codes
# ---------------------------------------------------------------
print("\n--- Test read_live_player_info ---")
players = read_live_player_info(os.path.join(SLP_DIR, "unranked_game1.slp"))
check("returns players", players is not None)
if players:
    check("two players", len(players) == 2)
    check("player 0 code", players[0]["connect_code"] == "NIKK#513",
          f"got {players[0]['connect_code']!r}")
    check("player 1 code", players[1]["connect_code"] == "NIKK#142",
          f"got {players[1]['connect_code']!r}")
    check("player 0 name", players[0]["display_name"] == "Nikki Dev1",
          f"got {players[0]['display_name']!r}")

# ---------------------------------------------------------------
# Test 2: read_live_player_info on older file (no connect codes)
# ---------------------------------------------------------------
print("\n--- Test read_live_player_info (older file) ---")
players_old = read_live_player_info(os.path.join(SLP_DIR, "test.slp"))
check("returns players", players_old is not None)
if players_old:
    check("two players", len(players_old) == 2)

# ---------------------------------------------------------------
# Test 3: read_game_mode
# ---------------------------------------------------------------
print("\n--- Test read_game_mode ---")
check("ranked", read_game_mode(os.path.join(SLP_DIR, "ranked_game1_tiebreak.slp")) == "ranked")
check("unranked", read_game_mode(os.path.join(SLP_DIR, "unranked_game1.slp")) == "unranked")
check("old file -> other", read_game_mode(os.path.join(SLP_DIR, "test.slp")) == "other")

# ---------------------------------------------------------------
# Test 4: parse_completed_game — NO_CONTEST (LRAS)
# ---------------------------------------------------------------
print("\n--- Test parse_completed_game (NO_CONTEST) ---")
result = parse_completed_game(os.path.join(SLP_DIR, "unranked_game1.slp"))
check("returns result", result is not None)
if result:
    check("two players", len(result["players"]) == 2)
    check("winner_port is 1 (non-LRAS player)", result["winner_port"] == 1,
          f"got {result['winner_port']}")
    check("player 0 has NIKK#513", "NIKK#513" in result["players"][0])
    check("player 1 has NIKK#142", "NIKK#142" in result["players"][1])
    check("mode is unranked", result["mode"] == "unranked",
          f"got {result['mode']!r}")

# ---------------------------------------------------------------
# Test 5: parse_completed_game — CONCLUSIVE (older replay)
# ---------------------------------------------------------------
print("\n--- Test parse_completed_game (CONCLUSIVE) ---")
result2 = parse_completed_game(os.path.join(SLP_DIR, "test.slp"))
check("returns result", result2 is not None)
if result2:
    check("two active ports", len(result2["active_ports"]) == 2)
    check("winner is port 0 (has 4 stocks)", result2["winner_port"] == 0,
          f"got {result2['winner_port']}")
    check("mode is other", result2["mode"] == "other",
          f"got {result2['mode']!r}")

# ---------------------------------------------------------------
# Test 6: _collect_slp_files is recursive
# ---------------------------------------------------------------
print("\n--- Test recursive file collection ---")
files = _collect_slp_files(SLP_DIR)
check("finds many .slp files", len(files) > 10, f"found {len(files)}")
subdir_files = [f for f in files if os.sep + "consistencyTest" + os.sep in f
                or os.sep + "placementsTest" + os.sep in f]
check("includes files in subdirectories", len(subdir_files) > 0,
      f"found {len(subdir_files)} subdir files")

# ---------------------------------------------------------------
# Test 7: build_winrate_dict (ranked/unranked split)
# ---------------------------------------------------------------
print("\n--- Test build_winrate_dict ---")
records = build_winrate_dict(SLP_DIR, "NIKK#513")
check("returns dict", isinstance(records, dict))
opp_key = None
for k in records:
    if "NIKK#142" in k:
        opp_key = k
        break
check("found opponent NIKK#142", opp_key is not None, f"keys: {list(records.keys())}")
if opp_key:
    rec = records[opp_key]
    check("has ranked key", "ranked" in rec)
    check("has unranked key", "unranked" in rec)
    total = rec["ranked"][0] + rec["ranked"][1] + rec["unranked"][0] + rec["unranked"][1]
    check("recorded some games", total > 0,
          f"ranked={rec['ranked']}, unranked={rec['unranked']}")

# ---------------------------------------------------------------
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
