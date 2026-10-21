# Licenses

The files in this repo's releases are identical copies (same SHA-256 fingerprint) of the ones published by their
authors, who keep all rights. We only redistribute them, unmodified, under their own licenses.

## FFmpeg (release `ffmpeg`)

- Linux and Windows builds by [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), `gpl` variants:
  **GNU GPL v3** (FFmpeg built with GPL libraries such as x264 and x265).
- Mac builds by [Martin Riedl](https://ffmpeg.martin-riedl.de): **GNU GPL**.

Source code: the same release holds the FFmpeg source code of every copied version (`ffmpeg-source-<version>.tar.gz`,
from the [official FFmpeg repository](https://github.com/FFmpeg/FFmpeg)); `manifest.json` tells which version belongs
to which file. How they were built, and the versions of the libraries used, are in the authors' public build scripts:
[BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) and [git.martin-riedl.de](https://git.martin-riedl.de/ffmpeg/build-script).
On request (open an issue in this repo) we also provide the source code of those libraries, for three years from the
copy.

## uv (release `uv-<version>`)

[Astral](https://github.com/astral-sh/uv): **MIT** or **Apache 2.0**, at your option.

## Portable Python (releases named after a date)

[python-build-standalone](https://github.com/astral-sh/python-build-standalone): CPython under the **PSF** license;
the bundled libraries have their own licenses, listed inside each archive (`python/licenses` or `PYTHON.json`).

## YOLO11 weights (release `yolo11`)

[Ultralytics](https://github.com/ultralytics/ultralytics): **AGPL-3.0**.
