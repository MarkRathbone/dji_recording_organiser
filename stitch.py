#!/usr/bin/env python3
"""
Auto-organize DJI clips into YYYY/MM/DD folders (case‑insensitive .mp4/.mkv), then auto-stitch sequences based on timestamp gaps.
After stitching each sequence, delete the source clips and rename the stitched output to TIME.mp4.

Requires:
  • ffmpeg & ffprobe on PATH
  • Python 3.6+

Usage:
  ./organize_and_stitch.py [--root DIR] [--gap N] [--pattern GLOB] [-v]
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Regex for original DJI filenames
ORG_PATTERN = re.compile(
    r'^DJI_(?P<date>\d{8})(?P<time>\d{6})_\d{4}_D\.(?P<ext>mp4|mkv)$', re.IGNORECASE
)


def check_tools():
    """Ensure ffmpeg & ffprobe are available."""
    for cmd in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run([cmd, "-version"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            print(f"❌ Error: {cmd} not found. Install FFmpeg and ensure it's in PATH.", file=sys.stderr)
            sys.exit(1)


def organize_dji_videos(root: Path, pattern: str, verbose: bool) -> int:
    """
    Move DJI clips from flat structure into YYYY/MM/DD folders,
    renaming from DJI_... to HHMMSS.ext. Returns number moved.
    """
    count = 0
    for src in root.rglob(pattern):
        if not src.is_file():
            continue
        m = ORG_PATTERN.match(src.name)
        if not m:
            continue
        date, time, ext = m.group('date'), m.group('time'), m.group('ext').lower()
        year, month, day = date[:4], date[4:6], date[6:8]
        dest_dir = root / year / month / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        new_name = f"{time}.{ext}"
        dest = dest_dir / new_name
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{time}_{counter}.{ext}"
            counter += 1
        shutil.move(str(src), str(dest))
        count += 1
        if verbose:
            print(f"Moved: {src.name} -> {dest.relative_to(root)}")
    return count


def probe_duration(path: Path) -> float:
    """Return video duration in seconds via ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    return float(result.stdout)


def group_sequences(clips, starts, durations, max_gap, verbose=False):
    """
    Given sorted clips, start times, durations, group into sequences
    where gap ≤ max_gap. Returns list of index lists.
    """
    seqs = []
    current = [0]
    for i in range(1, len(clips)):
        prev_end = starts[i-1] + timedelta(seconds=durations[i-1])
        gap = (starts[i] - prev_end).total_seconds()
        if verbose:
            print(f"Gap: {clips[i-1].name}@{prev_end.time()} → {clips[i].name}@{starts[i].time()} = {gap:.1f}s")
        if gap <= max_gap:
            current.append(i)
        else:
            seqs.append(current)
            current = [i]
    seqs.append(current)
    return seqs


def make_concat_file(paths, verbose=False) -> Path:
    """Write FFmpeg concat list file with absolute paths."""
    tf = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt')
    for p in paths:
        tf.write(f"file '{p.resolve().as_posix()}'\n")
    tf.close()
    if verbose:
        print(f"Concat list: {tf.name}")
        print(Path(tf.name).read_text())
    return Path(tf.name)


def run_concat_and_cleanup(seq_paths, output_dir: Path, start_time: str, verbose: bool) -> None:
    """
    Concatenate seq_paths into a temp file, delete sources, rename to TIME.mp4.
    """
    temp_name = f"stitched_{start_time}.mp4"
    final_name = f"{start_time}.mp4"
    temp_path = output_dir / temp_name
    list_file = make_concat_file(seq_paths, verbose)

    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", "-y"
    ]
    if not verbose:
        cmd += ["-loglevel", "error"]
    print(f"Running concat → {temp_name}") if verbose else None
    subprocess.run(cmd + [str(temp_path)], check=True)

    # Cleanup sources
    for p in seq_paths:
        try:
            p.unlink()
            if verbose:
                print(f"Deleted source: {p.name}")
        except FileNotFoundError:
            if verbose:
                print(f"Warning: source not found: {p.name}")

    # Rename
    final_path = output_dir / final_name
    temp_path.replace(final_path)
    if verbose:
        print(f"Renamed {temp_name} → {final_name}")


def stitch_day_directory(day_dir: Path, max_gap: float, verbose: bool) -> int:
    """
    Stitch all sequences in a YYYY/MM/DD folder. Returns count stitched.
    """
    # Collect .mp4/.mkv sorted by actual start time
    clips = []
    starts, durations = [], []
    for ext in ("mp4", "mkv"):
        for f in sorted(day_dir.glob(f"*.{ext}")):
            # Filename HHMMSS(.counter).ext
            time_str = f.stem.split('_')[0]
            try:
                start_dt = datetime(
                    int(day_dir.parent.parent.name),
                    int(day_dir.parent.name),
                    int(day_dir.name),
                    int(time_str[0:2]),
                    int(time_str[2:4]),
                    int(time_str[4:6])
                )
            except Exception:
                continue
            clips.append(f)
            starts.append(start_dt)
            durations.append(probe_duration(f))

    # Ensure sorted by start time
    order = sorted(range(len(clips)), key=lambda i: starts[i])
    clips = [clips[i] for i in order]
    starts = [starts[i] for i in order]
    durations = [durations[i] for i in order]

    seqs = group_sequences(clips, starts, durations, max_gap, verbose)
    stitched = 0
    for seq in seqs:
        if len(seq) < 2:
            continue
        seq_paths = [clips[i] for i in seq]
        start_time = starts[seq[0]].strftime("%H%M%S")
        print(f"Stitching {len(seq)} clips starting at {start_time}")
        run_concat_and_cleanup(seq_paths, day_dir, start_time, verbose)
        stitched += 1
    return stitched


def main():
    p = argparse.ArgumentParser(description="Organize & auto-stitch DJI clips.")
    p.add_argument("--root", type=Path, default=Path('.'), help="Scan root (default cwd)")
    p.add_argument("--pattern", default="DJI_*.[mM][pP]4", help="Glob for originals")
    p.add_argument("--gap", type=float, default=30, help="Max gap in seconds")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logs")
    args = p.parse_args()

    check_tools()
    moved = organize_dji_videos(args.root, args.pattern, args.verbose)
    print(f"Organized {moved} clips.")

    total = 0
    for year in sorted(args.root.iterdir()):
        if not year.is_dir() or not year.name.isdigit(): continue
        for month in sorted(year.iterdir()):
            if not month.is_dir() or not month.name.isdigit(): continue
            for day in sorted(month.iterdir()):
                if not day.is_dir() or not day.name.isdigit(): continue
                stitched = stitch_day_directory(day, args.gap, args.verbose)
                if stitched and args.verbose:
                    print(f"→ {stitched} stitched in {year.name}/{month.name}/{day.name}")
                total += stitched

    print(f"Done: {total} stitched files created.")

if __name__ == '__main__':
    main()
