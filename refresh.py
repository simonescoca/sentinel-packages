#!/usr/bin/env python3
"""Backup copy of the packages Sentinel downloads: fetch them from the official sources, check their SHA-256
fingerprints and upload to this repo's releases only what changed. Runs every week (.github/workflows/refresh.yml).

Sentinel uses these files ONLY when the official source does not answer (site down, file gone).

Releases:
- `ffmpeg`: FFmpeg for Mac (Martin Riedl) and for Linux and Windows (BtbN), latest and previous stable version
  (`-prev`), `manifest.json` with the fingerprints, and the FFmpeg source code of the copied versions (GPL).
- `uv-<version>`: Astral's uv for the 5 systems, with its `.sha256` files.
- `<tag>` of python-build-standalone (e.g. 20261009): the portable Python that uv installs, with the same file names
  (Sentinel points uv here with UV_PYTHON_INSTALL_MIRROR).
- `yolo11`: Ultralytics' YOLO11 model weights (n, s, m, l, x).

Exits with an error (and GitHub sends an email) only when a file is missing both from the official source and here.
Python standard library only, plus `gh` (preinstalled on GitHub Actions runners).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = os.environ.get("GITHUB_REPOSITORY", "simonescoca/sentinel-packages")
VERSIONS = json.loads((HERE / "versions.json").read_text(encoding="utf-8"))
USER_AGENT = "sentinel-packages"
RELEASE_NOTES = "Backup copy for Sentinel (see README). Refreshed by .github/workflows/refresh.yml."

BTBN_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
BTBN_DOWNLOAD = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
BTBN_PLATS = ("linux64", "linuxarm64", "win64", "winarm64")
RIEDL = "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/{tool}.zip"
FFMPEG_SOURCE = "https://github.com/FFmpeg/FFmpeg/archive/{ref}.tar.gz"
UV_TARGETS = ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu", "aarch64-apple-darwin",
              "x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")
PBS = "https://github.com/astral-sh/python-build-standalone/releases/download/{tag}/{name}"
# Portable Pythons Sentinel needs: (system, architectures, libc)
PY_TARGETS = (("linux", ("x86_64", "x86_64_v2", "x86_64_v3", "x86_64_v4", "aarch64"), "gnu"),
              ("macos", ("aarch64",), "none"), ("windows", ("x86_64", "aarch64"), "none"))
YOLO = "https://github.com/ultralytics/assets/releases/download/{release}/{name}"

problems: list[str] = []   # files with neither an official source NOR a copy here: error
warnings: list[str] = []   # official source down but the copy is already here: fine (that is what it is for)
summary: list[str] = []


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- network and files ------------------------------------------------------------------------------

def _open(url: str, method: str = "GET", timeout: float = 120):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_text(url: str) -> tuple[str, str]:
    """(text, final address after redirects)."""
    with _open(url, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace"), resp.geturl()


def download(url: str, dest: Path, sha256: str | None = None, tries: int = 3) -> str:
    """Download `url` to `dest`; return the final address. With `sha256` the fingerprint must match."""
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            with _open(url) as resp, open(dest, "wb") as out:
                shutil.copyfileobj(resp, out, 1024 * 1024)
                final = resp.geturl()
            if sha256 and sha(dest) != sha256.lower():
                raise ValueError(f"wrong fingerprint for {url}")
            return final
        except ValueError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            last = exc
            dest.unlink(missing_ok=True)
            time.sleep(5 * attempt)
    raise RuntimeError(f"{url}: {last}")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sums(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            out[parts[-1].lstrip("*")] = parts[0].lower()
    return out


# --- this repo's releases (gh) ------------------------------------------------------------------------

def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, check=check)


def assets(tag: str) -> dict[str, int]:
    """Name → size of the files of release `tag` (created empty if missing)."""
    view = gh("release", "view", tag, "--json", "assets,body", check=False)
    if view.returncode != 0:
        gh("release", "create", tag, "--title", tag, "--notes", RELEASE_NOTES)
        return {}
    data = json.loads(view.stdout)
    if data.get("body") != RELEASE_NOTES:
        gh("release", "edit", tag, "--notes", RELEASE_NOTES, check=False)
    return {a["name"]: a["size"] for a in data["assets"]}


def upload(tag: str, path: Path, name: str) -> None:
    """Upload `path` as `name` (replacing what was there)."""
    with tempfile.TemporaryDirectory() as tmp:
        named = Path(tmp) / name
        try:
            os.link(path, named)
        except OSError:
            shutil.copy2(path, named)
        gh("release", "upload", tag, str(named), "--clobber")
    summary.append(f"uploaded {tag}/{name}")


def mirror_url(tag: str, name: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}/{urllib.parse.quote(name)}"


# --- FFmpeg ----------------------------------------------------------------------------------------

def pick_btbn(names: list[str], plat: str, rank: int) -> str | None:
    """Same as Sentinel (installer/fetch.py, pick_btbn_asset): the latest stable (rank 0) or the previous one."""
    pattern = re.compile(rf"^ffmpeg-n(\d+)\.(\d+)-latest-{plat}-gpl-\d+\.\d+\.(zip|tar\.xz)$")
    stable = sorted(((int(m.group(1)), int(m.group(2)), n) for n in names if (m := pattern.match(n))), reverse=True)
    return stable[rank][2] if rank < len(stable) else None


def ffmpeg_version(archive: Path, work: Path) -> str | None:
    """`n9.0.2-31-gc89d6ee1ca-20261021` from the Linux x86-64 FFmpeg (this runner can run it)."""
    out = work / "x"
    shutil.rmtree(out, ignore_errors=True)
    with tarfile.open(archive) as tf:
        tf.extractall(out, filter="data")
    exe = next(out.rglob("bin/ffmpeg"), None)
    if exe is None:
        return None
    first = subprocess.run([str(exe), "-version"], capture_output=True, text=True).stdout.split("\n", 1)[0]
    m = re.match(r"ffmpeg version (\S+)", first)
    return m.group(1) if m else None


def source_ref(version: str) -> str:
    """Tag or commit of the source code: `n9.0.2-31-gc89d6ee1ca-20261021` (BtbN: commit and date) → c89d6ee1ca;
    `9.0.2` (Mac) → n9.0.2."""
    m = re.search(r"-g([0-9a-f]{7,40})(?:-\d{8})?$", version)
    if m:
        return m.group(1)
    return version if version.startswith("n") else f"n{version}"


def ffmpeg(work: Path) -> None:
    tag = "ffmpeg"
    have = assets(tag)
    manifest: dict = {"files": {}}
    if "manifest.json" in have:
        try:
            manifest = json.loads(fetch_text(mirror_url(tag, "manifest.json"))[0])
        except Exception as exc:
            warnings.append(f"manifest.json not read ({exc}): uploading everything again")
    files = manifest.setdefault("files", {})
    # BtbN: Linux and Windows
    try:
        names = [a["name"] for a in json.loads(fetch_text(BTBN_API)[0])["assets"]]
        checks = sums(fetch_text(BTBN_DOWNLOAD + "checksums.sha256")[0])
    except Exception as exc:
        names, checks = [], {}
        warnings.append(f"BtbN does not answer: {exc}")
    for plat in BTBN_PLATS:
        ext = "zip" if plat.startswith("win") else "tar.xz"
        for rank, suffix in ((0, ""), (1, "-prev")):
            mine = f"{plat}{suffix}.{ext}"
            name = pick_btbn(names, plat, rank)
            if name is None or name not in checks:
                (warnings if mine in have else problems).append(f"FFmpeg {mine}: nothing from the official source")
                continue
            entry = files.get(mine) or {}
            if entry.get("sha256") == checks[name] and mine in have:
                continue
            path = work / mine
            try:
                url = download(BTBN_DOWNLOAD + name, path, checks[name])
            except Exception as exc:
                (warnings if mine in have else problems).append(f"FFmpeg {mine}: {exc}")
                continue
            version = ffmpeg_version(path, work) if plat == "linux64" else None
            files[mine] = {"sha256": checks[name], "source": url, "upstream_name": name,
                           "version": version or files.get(f"linux64{suffix}.tar.xz", {}).get("version"),
                           "fetched_at": now()}
            upload(tag, path, mine)
            path.unlink()
    for name, entry in files.items():   # the other builds of the same branch have the Linux x86-64 version
        if name.endswith((".zip", ".tar.xz")) and not name.startswith("macos") and not entry.get("version"):
            entry["version"] = files.get("linux64" + ("-prev" if "-prev" in name else "") + ".tar.xz", {}).get("version")
    # Martin Riedl: Mac Apple Silicon, one file per tool; the fingerprint sits next to the real file
    for tool in ("ffmpeg", "ffprobe"):
        mine = f"macos-arm64-{tool}.zip"
        path = work / mine
        try:
            final = download(RIEDL.format(tool=tool), path)
            digest = fetch_text(final + ".sha256")[0].split()[0].lower()   # "<fingerprint>  ffmpeg.zip"
            if sha(path) != digest:
                raise ValueError("wrong fingerprint")
        except Exception as exc:
            path.unlink(missing_ok=True)
            (warnings if mine in have else problems).append(f"FFmpeg {mine}: {exc}")
            continue
        m = re.search(r"_(\d+\.\d+(?:\.\d+)?)/", final)
        if (files.get(mine) or {}).get("sha256") != digest or mine not in have:
            files[mine] = {"sha256": digest, "source": final, "version": m.group(1) if m else None,
                           "fetched_at": now()}
            upload(tag, path, mine)
        path.unlink()
    # FFmpeg source code of the copied versions (GPL); the ones no longer needed are removed
    wanted = {}
    for entry in files.values():
        if entry.get("version"):
            ref = source_ref(entry["version"])
            wanted[f"ffmpeg-source-{ref}.tar.gz"] = ref
            entry["sources"] = f"ffmpeg-source-{ref}.tar.gz"
    for name, ref in wanted.items():
        if name in have:
            continue
        path = work / name
        try:
            download(FFMPEG_SOURCE.format(ref=ref), path)
            upload(tag, path, name)
        except Exception as exc:
            problems.append(f"FFmpeg source {ref}: {exc}")
        path.unlink(missing_ok=True)
    for name in have:
        if name.startswith("ffmpeg-so") and name not in wanted:
            gh("release", "delete-asset", tag, name, "--yes", check=False)
    manifest["updated_at"] = now()
    path = work / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    upload(tag, path, "manifest.json")


# --- uv and portable Python ---------------------------------------------------------------------------

def uv(work: Path) -> Path | None:
    """Copy uv for the 5 systems; return the Linux x86-64 one (needed to list the Pythons)."""
    version = VERSIONS["uv"]
    tag = f"uv-{version}"
    have = assets(tag)
    local = None
    for target in UV_TARGETS:
        name = f"uv-{target}." + ("zip" if "windows" in target else "tar.gz")
        path = work / name
        need = name not in have or f"{name}.sha256" not in have
        if not need and target != "x86_64-unknown-linux-gnu":
            continue
        base = f"https://github.com/astral-sh/uv/releases/download/{version}/{name}"
        try:
            digest_text = fetch_text(base + ".sha256")[0]
            digest = sums(digest_text).get(name) or digest_text.split()[0].lower()
            download(base, path, digest)
        except Exception as exc:
            if need:
                problems.append(f"uv {name}: {exc}")
                continue
            warnings.append(f"uv {name} from the official source: {exc}")
            download(mirror_url(tag, name), path)   # the Linux x86-64 one is needed here: from the copy
            need = False
        if need:
            (work / f"{name}.sha256").write_text(digest_text, encoding="utf-8")
            upload(tag, path, name)
            upload(tag, work / f"{name}.sha256", f"{name}.sha256")
        if target == "x86_64-unknown-linux-gnu":
            with tarfile.open(path) as tf:
                tf.extractall(work / "uv", filter="data")
            local = next((work / "uv").rglob("uv"), None)
    return local


def python(work: Path, uv_exe: Path | None) -> None:
    if uv_exe is None:
        problems.append("Python: uv is missing, so the files to copy are unknown")
        return
    out = subprocess.run([str(uv_exe), "python", "list", VERSIONS["python"], "--all-platforms", "--all-arches",
                          "--only-downloads", "--output-format", "json"], capture_output=True, text=True, check=True)
    entries = [e for e in json.loads(out.stdout)
               if e["implementation"] == "cpython" and e["variant"] == "default" and e.get("url")
               and any(e["os"] == os_ and e["arch"] in arches and e["libc"] == libc
                       for os_, arches, libc in PY_TARGETS)]
    if not entries:
        problems.append("Python: uv lists no files")
        return
    newest = max(tuple(e["version_parts"].values()) for e in entries)
    shasums: dict[str, dict[str, str]] = {}
    for e in entries:
        if tuple(e["version_parts"].values()) != newest:
            continue
        tag, quoted = e["url"].rsplit("/", 2)[-2:]
        name = urllib.parse.unquote(quoted)
        have = assets(tag)
        if name in have:
            continue
        if tag not in shasums:
            shasums[tag] = sums(fetch_text(PBS.format(tag=tag, name="SHA256SUMS"))[0])
        path = work / name
        try:
            download(e["url"], path, shasums[tag].get(name))
        except Exception:
            try:
                download(PBS.format(tag=tag, name=quoted), path, shasums[tag].get(name))
            except Exception as exc:
                problems.append(f"Python {name}: {exc}")
                continue
        upload(tag, path, name)
        path.unlink()


# --- YOLO weights ---------------------------------------------------------------------------------------

def yolo(work: Path) -> None:
    tag = "yolo11"
    have = assets(tag)
    for model, digest in VERSIONS["yolo11_sha256"].items():
        name = f"{model}.pt"
        if name in have:
            continue
        path = work / name
        try:
            download(YOLO.format(release=VERSIONS["ultralytics_assets"], name=name), path, digest)
        except Exception as exc:
            problems.append(f"YOLO {name}: {exc}")
            continue
        upload(tag, path, name)
        path.unlink()


# --- final check: every file really downloads from the copy ---------------------------------------------

def check() -> None:
    tags = ["ffmpeg", f"uv-{VERSIONS['uv']}", "yolo11"]
    listed = json.loads(gh("release", "list", "--json", "tagName", "--limit", "100").stdout)
    tags += [r["tagName"] for r in listed if r["tagName"].isdigit()]   # Python (python-build-standalone tags)
    count = 0
    for tag in tags:
        for name in assets(tag):
            try:
                with _open(mirror_url(tag, name), method="HEAD", timeout=60) as resp:
                    ok = resp.status == 200
            except Exception as exc:
                ok, resp = False, exc
            if not ok:
                problems.append(f"{tag}/{name} does not download from the copy ({resp})")
            count += 1
    summary.append(f"checked {count} files of the copy")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for part in (ffmpeg, yolo):
            try:
                part(work)
            except Exception as exc:
                problems.append(f"{part.__name__}: {exc}")
        try:
            python(work, uv(work))
        except Exception as exc:
            problems.append(f"uv/Python: {exc}")
        check()
    report = "\n".join(["## Sentinel backup copy", "", *[f"- {s}" for s in summary or ["nothing new"]],
                        "", "### Warnings", *[f"- {w}" for w in warnings or ["none"]],
                        "", "### Problems", *[f"- {p}" for p in problems or ["none"]]])
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    (HERE / "status.json").write_text(json.dumps({"checked_on": time.strftime("%Y-%m-%d", time.gmtime()),
                                                  "problems": problems, "warnings": warnings}, indent=1) + "\n",
                                      encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
