"""
Screener opener for Plumb
-------------------------
Opens each company on your list on screener.in, one at a time, in your normal browser.
You click "Export to Excel" yourself (you stay logged in as usual, nothing is automated on Screener),
then press Enter here to open the next one. At the end, the downloaded Excel files are moved into one
dated folder so you can drop them all into Plumb at once.

Usage (from this folder):
    python screener_open.py                      # uses watchlist.txt, consolidated figures
    python screener_open.py --batch 5            # open 5 tabs at a time
    python screener_open.py --list hospitals.txt # a different list
    python screener_open.py --standalone         # standalone instead of consolidated
    python screener_open.py --downloads "D:\\Downloads"   # if your browser saves elsewhere

Only uses the Python standard library.
"""
import argparse
import os
import shutil
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read_list(path: Path):
    """One NSE symbol (e.g. APOLLOHOSP) or BSE code (e.g. 543220) per line. '#' starts a comment."""
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            items.append(line.upper())
    return list(dict.fromkeys(items))  # drop duplicates, keep order


def default_downloads():
    if os.name == "nt":  # Windows: ask the shell where Downloads really is (it can be moved)
        try:
            import winreg
            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                val, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
                return Path(os.path.expandvars(val))
        except Exception:
            pass
    return Path.home() / "Downloads"


def collect(downloads: Path, since: float, out: Path):
    """Move Excel files downloaded since the run started into the output folder."""
    if not downloads.exists():
        print(f"\nCould not find your Downloads folder at {downloads}. Use --downloads to point to it.")
        return []
    files = [p for p in downloads.iterdir()
             if p.is_file() and p.suffix.lower() in (".xlsx", ".xls") and p.stat().st_mtime >= since - 5]
    if not files:
        return []
    out.mkdir(parents=True, exist_ok=True)
    moved = []
    for p in sorted(files, key=lambda f: f.stat().st_mtime):
        target = out / p.name
        n = 2
        while target.exists():
            target = out / f"{p.stem} ({n}){p.suffix}"
            n += 1
        shutil.move(str(p), str(target))
        moved.append(target)
    return moved


def main():
    ap = argparse.ArgumentParser(description="Open your shortlist on Screener, one company at a time.")
    ap.add_argument("--list", default=str(HERE / "watchlist.txt"), help="text file with one symbol per line")
    ap.add_argument("--batch", type=int, default=1, help="how many companies to open at once (default 1)")
    ap.add_argument("--standalone", action="store_true", help="open standalone figures instead of consolidated")
    ap.add_argument("--downloads", default=None, help="your browser's download folder")
    ap.add_argument("--out", default=None, help="where to gather the Excel files")
    ap.add_argument("--no-collect", action="store_true", help="leave the files in Downloads")
    a = ap.parse_args()

    lst = Path(a.list)
    if not lst.exists():
        sys.exit(f"List not found: {lst}")
    symbols = read_list(lst)
    if not symbols:
        sys.exit(f"No symbols in {lst}")

    view = "" if a.standalone else "consolidated/"
    batch = max(1, a.batch)
    start = time.time()
    print(f"{len(symbols)} companies from {lst.name}. In each tab, click 'Export to Excel'.")
    print("Press Enter here for the next one, or type q and Enter to stop.\n")

    for i in range(0, len(symbols), batch):
        group = symbols[i:i + batch]
        for s in group:
            webbrowser.open_new_tab(f"https://www.screener.in/company/{s}/{view}")
            time.sleep(0.4)
        done = min(i + batch, len(symbols))
        label = ", ".join(group)
        if done < len(symbols):
            ans = input(f"[{done}/{len(symbols)}] {label}  -> Enter for next, q to stop: ").strip().lower()
            if ans == "q":
                break
        else:
            print(f"[{done}/{len(symbols)}] {label}  (last one)")

    if a.no_collect:
        print("\nDone. Files are in your Downloads folder.")
        return
    input("\nWhen the last download has finished, press Enter to gather the files... ")
    downloads = Path(a.downloads) if a.downloads else default_downloads()
    out = Path(a.out) if a.out else HERE / "exports" / datetime.now().strftime("%Y-%m-%d")
    moved = collect(downloads, start, out)
    if not moved:
        print(f"No new Excel files found in {downloads}. If your browser saves elsewhere, use --downloads.")
        return
    print(f"\nMoved {len(moved)} file(s) to {out}:")
    for p in moved:
        print("  ", p.name)
    print("\nNext: open Plumb, click Upload, and select all of these files at once.")
    if os.name == "nt":
        os.startfile(out)  # open the folder in Explorer


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
