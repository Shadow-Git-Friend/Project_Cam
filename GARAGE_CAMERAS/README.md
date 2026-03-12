# Multi-camera Recording (ffmpeg)

This script detects V4L2 webcams (`/dev/video*`) and records multiple cameras simultaneously using `ffmpeg`. It is designed for multi-camera calibration sessions.

## Requirements
- Linux with V4L2 devices (`/dev/video*`)
- `ffmpeg`
- Optional (better device names/capture filtering): `v4l2-ctl` from `v4l-utils`

## Quick start
List devices and identify the built-in webcam:

```bash
./record_cams.py --list
```

Record up to 4 cameras, excluding the built-in webcam by name or by device path:

```bash
./record_cams.py --exclude-name "Integrated" --max-cams 4
# or
./record_cams.py --exclude-dev /dev/video0 --max-cams 4
```

Record specific devices in a fixed order:

```bash
./record_cams.py --include-dev /dev/video0 --include-dev /dev/video2 --include-dev /dev/video4 --include-dev /dev/video6
```

Show a live 2x2 preview grid while recording (requires 4 cameras):

```bash
./record_cams.py --preview-grid --include-dev /dev/video0 --include-dev /dev/video2 --include-dev /dev/video4 --include-dev /dev/video6
```

Stop recording with `Ctrl+C`. All ffmpeg processes are terminated and files are closed.

## Common options
- `--resolution 1920x1080`
- `--framerate 30`
- `--input-format mjpeg`
- `--no-copy` (re-encode if stream copy fails)
- `--preview-grid` (live 2x2 preview window)
- `--preview-scale 0.5` (scale preview window)
- `--thread-queue-size 512` (input buffering; set 0 to disable)
- `--rtbufsize 256M` (V4L2 input buffer; set 0 to disable)
- `--use-wallclock-timestamps` / `--no-wallclock-timestamps`
- `--genpts` / `--no-genpts`
- `--out-dir recordings/session_01`
- `--loglevel info`

## Notes
- The script prefers MJPEG input (`--input-format mjpeg`) and uses `-c:v copy` by default.
- If a camera does not output MJPEG at the requested resolution/fps, try `--no-copy` or adjust `--resolution` and `--framerate`.
- Preview mode uses the SDL output of `ffmpeg`. If your build lacks SDL support, run without `--preview-grid`.
