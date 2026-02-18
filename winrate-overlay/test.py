"""
Tests for the slp_parser module using sample .slp files from the repo.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from slp_parser import read_live_player_info, parse_completed_game, build_winrate_dict

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
# Test 3: parse_completed_game — NO_CONTEST (LRAS)
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

# ---------------------------------------------------------------
# Test 4: parse_completed_game — CONCLUSIVE (older replay)
# ---------------------------------------------------------------
print("\n--- Test parse_completed_game (CONCLUSIVE) ---")
result2 = parse_completed_game(os.path.join(SLP_DIR, "test.slp"))
check("returns result", result2 is not None)
if result2:
    check("two active ports", len(result2["active_ports"]) == 2)
    check("winner is port 0 (has 4 stocks)", result2["winner_port"] == 0,
          f"got {result2['winner_port']}")
    check("has player ids", len(result2["players"]) == 2)

# ---------------------------------------------------------------
# Test 5: build_winrate_dict
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
    w, l = records[opp_key]
    check("recorded some games", w + l > 0, f"wins={w}, losses={l}")

# ---------------------------------------------------------------
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
