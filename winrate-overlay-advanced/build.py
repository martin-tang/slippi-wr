"""
Build a standalone .exe for Slippi History Advanced using PyInstaller.

Usage:
    pip install pyinstaller
    python build.py

Output:  dist/SlippiHistoryAdvanced.exe
"""

import subprocess
import sys


def main():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name=SlippiHistoryAdvanced",
        "--add-data=imgs;imgs",          # bundle the imgs folder
        "--add-data=slp_parser.py;.",     # bundle helper modules
        "--add-data=watcher.py;.",
        "main.py",
    ]
    print("Building .exe ...\n")
    print("  " + " ".join(cmd) + "\n")
    subprocess.run(cmd, check=True)
    print("\nDone!  Your executable is at:  dist/SlippiHistoryAdvanced.exe")
    print("    Copy the .exe anywhere and run it — no Python install needed.")


if __name__ == "__main__":
    main()
