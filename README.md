# Sentinel packages (backup copy)

While installing, Sentinel downloads a few tools from the official sites of their makers. If one of these sites
does not answer (it has happened: the FFmpeg site for Mac and the ncnn packages for Windows ARM were down for hours),
Sentinel takes **the very same files** from here. It always tries the official source first.

| Release | Contents | Official source |
| --- | --- | --- |
| `ffmpeg` | FFmpeg and ffprobe for Mac (Apple Silicon), Linux and Windows (x86-64 and ARM64), latest and previous version (`-prev`); `manifest.json` with the SHA-256 fingerprints; FFmpeg source code of the copied versions | [Martin Riedl](https://ffmpeg.martin-riedl.de) (Mac), [BtbN](https://github.com/BtbN/FFmpeg-Builds) (Linux, Windows) |
| `uv-<version>` | uv for the 5 systems, with the `.sha256` files | [Astral](https://github.com/astral-sh/uv) |
| `<date>` (e.g. `20261009`) | portable Python 3.12, same files with the same names | [python-build-standalone](https://github.com/astral-sh/python-build-standalone) |
| `yolo11` | YOLO11 model weights (n, s, m, l, x) | [Ultralytics](https://github.com/ultralytics/assets) |

Every Monday `refresh.py` (run by `.github/workflows/refresh.yml`) downloads from the official sources, checks the
fingerprints they publish and uploads here only what changed; then it checks that every file really downloads from
here. `status.json` tells how the last check went.

When Sentinel moves to another version of uv, Python or the YOLO weights, `versions.json` has to follow.

Licenses: see [LICENSES.md](LICENSES.md).
