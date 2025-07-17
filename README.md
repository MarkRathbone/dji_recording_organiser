# Organize & Stitch DJI Clips

Auto-organize DJI video files into a `YYYY/MM/DD` directory structure, then automatically stitch contiguous clips together based on configurable timestamp gaps. After stitching, the source clips are deleted and the final file is renamed to `TIME.mp4`.

---

## Features

* **Automatic Discovery**: Scans a root directory (default: current working directory) for DJI clips matching `DJI_YYYYMMDDHHMMSS_####_D.(mp4|mkv)`.
* **Organize**: Moves and renames each file to `root/YYYY/MM/DD/HHMMSS.ext`.
* **Probe & Group**: Uses `ffprobe` to determine each clip’s duration, then groups clips whose start/end gap is within a configurable threshold (default: 30 seconds).
* **Stitching**: Concatenates each group via `ffmpeg` (no re‑encoding), deletes the original clips, and renames the output to `HHMMSS.mp4`.
* **Verbose Mode**: Inspect gap calculations, file moves, concatenation steps, and cleanup operations.

---

## Requirements

* Python 3.6+
* [FFmpeg](https://ffmpeg.org/) (includes `ffmpeg` & `ffprobe`) on your system `PATH`

---

## Installation

Clone this repository and make the script executable:

```bash
git clone <repo-url>
cd <repo-directory>
chmod +x organize_and_stitch.py
```

---

## Usage

```bash
./organize_and_stitch.py [options]
```

### Options

| Flag              | Description                                                |
| ----------------- | ---------------------------------------------------------- |
| `--root DIR`      | Root directory to scan (default: current directory)        |
| `--pattern GLOB`  | Glob for original DJI files (default: `DJI_*.[mM][pP]4`)   |
| `--gap SECONDS`   | Maximum allowed gap between clips to merge (default: 30)   |
| `-v`, `--verbose` | Show detailed logs (moves, gaps, ffmpeg commands, cleanup) |

---

### Examples

Scan current directory with default settings:

```bash
./stitch.py
```

Scan a custom folder, use a 45 s gap threshold, and enable verbose logging:

```bash
./organize_and_stitch.py --root /mnt/e/Drone --gap 45 -v
```

---

## How It Works

1. **Organize Step**:

   * Finds files matching `DJI_YYYYMMDDHHMMSS_####_D.mp4` or `.mkv`.
   * Extracts date & time from filename, creates `YYYY/MM/DD` subdirectory, renames to `HHMMSS.ext`.

2. **Stitch Step**:

   * In each `YYYY/MM/DD` folder, lists all `*.mp4` and `*.mkv`, parses start times, probes durations.
   * Sorts clips chronologically, computes the gap between one clip's end and the next clip's start.
   * Groups contiguous segments where the gap ≤ threshold.
   * For each group of 2+ clips:

     1. Generates a temporary FFmpeg concat list.
     2. Runs `ffmpeg -f concat -safe 0 -i list.txt -c copy` to stitch without re-encoding.
     3. Deletes the original source clips.
     4. Renames the temporary output `stitched_HHMMSS.mp4` to `HHMMSS.mp4`.

---

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.

---
