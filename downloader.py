#!/usr/bin/env python3
"""Download and validate a local playlist/XMLTV cache. Linux, Python 3.10+."""

import argparse
import contextlib
import datetime
import email.utils
import fcntl
import gzip
import http.client
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from xml.parsers import expat
import zlib


DEFAULTS = {
    "data_dir": "/opt/mediastream/m3ufiles",
    "request_gap_seconds": 60,
    "min_interval_seconds": 82800,
    "socket_timeout_seconds": 30,
    "download_timeout_seconds": 300,
    "max_download_bytes": 100 * 1024 * 1024,
    "max_epg_bytes": 500 * 1024 * 1024,
    "cleaner_image": "seanriggs/m3u-playlist-cleaner:latest",
    "cleaner_timeout_seconds": 3600,
}


class DownloadError(Exception):
    """A message safe to log without disclosing a private URL."""


class RateLimited(DownloadError):
    def __init__(self, seconds):
        super().__init__("Server requested a later retry; local files were preserved.")
        self.seconds = seconds


def log(message):
    print(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} {message}",
          flush=True)


def validate_url(url):
    try:
        p = urllib.parse.urlsplit(url)
        if (p.scheme not in ("http", "https") or not p.hostname or
                p.username is not None or p.password is not None or
                any(ord(c) <= 32 or ord(c) == 127 for c in url)):
            raise ValueError
        _ = p.port
    except (ValueError, TypeError):
        raise DownloadError("URLs must be HTTP(S), without embedded user/password or whitespace.") from None
    return p


def download_url(url):
    """Only normalize Dropbox share URLs; preserve every non-display query field."""
    p = validate_url(url)
    if p.hostname.lower() in ("dropbox.com", "www.dropbox.com") and (
            p.path.startswith("/s/") or p.path.startswith("/scl/fi/")):
        query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
                 if k not in ("dl", "raw")]
        query.append(("dl", "1"))
        return urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode(query)))
    return url


def load_config(path):
    try:
        supplied = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise DownloadError("Cannot read configuration JSON; copy config.example.json and edit it.") from None
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULTS) - {"playlist_url", "epg_url"}:
        raise DownloadError("Configuration contains unknown keys or is not a JSON object.")
    cfg = DEFAULTS | supplied
    for key in ("playlist_url", "epg_url"):
        if not isinstance(cfg.get(key), str) or "YOUR_" in cfg[key]:
            raise DownloadError(f"Set {key} in the configuration file.")
        cfg[key] = download_url(cfg[key])
    if not isinstance(cfg["data_dir"], str) or not Path(cfg["data_dir"]).is_absolute():
        raise DownloadError("data_dir must be an absolute path.")
    for key, default in DEFAULTS.items():
        if isinstance(default, int):
            value = cfg[key]
            minimum = 0 if key in ("request_gap_seconds", "min_interval_seconds") else 1
            if type(value) is not int or not minimum <= value <= 2**40:
                raise DownloadError(f"{key} must be a positive integer (intervals may be zero).")
    image = cfg["cleaner_image"]
    if not isinstance(image, str) or not image or image.startswith("-") or any(c.isspace() for c in image):
        raise DownloadError("cleaner_image must be a Docker image reference.")
    return cfg


class Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = validate_url(newurl)
        if urllib.parse.urlsplit(req.full_url).scheme == "https" and p.scheme != "https":
            raise DownloadError("Refusing an HTTPS-to-HTTP download redirect.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def retry_delay(header):
    try:
        return max(0, int(header))
    except (TypeError, ValueError):
        try:
            return max(0, math.ceil(email.utils.parsedate_to_datetime(header).timestamp() - time.time()))
        except (TypeError, ValueError, OverflowError):
            return 86400


def download(url, destination, cfg):
    opener = urllib.request.build_opener(Redirects())
    request = urllib.request.Request(url, headers={
        "User-Agent": "Playlist-EPG-Downloader/2.0",
        "Accept-Encoding": "identity",
    })
    started = time.monotonic()
    try:
        with opener.open(request, timeout=cfg["socket_timeout_seconds"]) as response:
            if response.status != 200:
                raise DownloadError(f"Unexpected HTTP {response.status}; download not published.")
            expected = response.headers.get("Content-Length")
            if expected is not None and (not expected.isdigit() or int(expected) > cfg["max_download_bytes"]):
                raise DownloadError("Download has an invalid or excessive Content-Length.")
            total = 0
            with destination.open("wb") as out:
                while True:
                    if time.monotonic() - started > cfg["download_timeout_seconds"]:
                        raise DownloadError("Download exceeded its time limit.")
                    chunk = response.read1(min(65536, cfg["max_download_bytes"] - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > cfg["max_download_bytes"]:
                        raise DownloadError("Download exceeded its size limit.")
                    out.write(chunk)
            if total == 0 or (expected is not None and total != int(expected)):
                raise DownloadError("Download is empty or incomplete.")
    except urllib.error.HTTPError as error:
        if error.code in (429, 503):
            raise RateLimited(retry_delay(error.headers.get("Retry-After"))) from None
        raise DownloadError(f"Download returned HTTP {error.code}; check the source/account settings.") from None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError):
        raise DownloadError("Download failed or timed out; check connectivity and source settings.") from None


def validate_playlist(path, limit):
    if not path.is_file() or path.stat().st_size > limit:
        raise DownloadError("Playlist is missing or too large.")
    try:
        with path.open(encoding="utf-8-sig") as source:
            first = source.readline().strip()
            if not (first == "#EXTM3U" or first.startswith("#EXTM3U ")):
                raise DownloadError("Playlist is not extended M3U; a cloud preview/sign-in page may have been returned.")
            count, pending = 0, False
            for raw in source:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#EXT-X-"):
                    raise DownloadError("Expected a channel list, received an HLS stream manifest.")
                if line.startswith("#EXTINF:"):
                    if pending or "," not in line:
                        raise DownloadError("Playlist contains an incomplete channel entry.")
                    pending = True
                elif not line.startswith("#"):
                    # The downloader preserves stream schemes; the optional cleaner has its own rules.
                    if not pending or not urllib.parse.urlsplit(line).scheme or any(c.isspace() for c in line):
                        raise DownloadError("Playlist contains an invalid channel address.")
                    count += 1
                    pending = False
            if pending or count == 0:
                raise DownloadError("Playlist has no complete channels or ends mid-entry.")
            return count
    except (UnicodeError, ValueError):
        raise DownloadError("Playlist is not valid UTF-8 extended M3U.") from None


def prepare_epg(downloaded, output, limit):
    """Stream XML parsing/decompression; never fetch a DTD or expand custom entities."""
    parser = expat.ParserCreate()
    depth, channels, programmes = 0, 0, 0

    def start(name, attrs):
        nonlocal depth, channels, programmes
        depth += 1
        if depth == 1 and name != "tv":
            raise DownloadError("EPG is not XMLTV; a cloud preview/sign-in page may have been returned.")
        if depth == 2:
            channels += name == "channel" and bool(attrs.get("id"))
            programmes += name == "programme" and bool(attrs.get("channel")) and bool(attrs.get("start"))

    def end(_name):
        nonlocal depth
        depth -= 1

    def no_entities(*_args):
        raise DownloadError("Custom XML entities are not supported.")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.EntityDeclHandler = no_entities
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    with downloaded.open("rb") as source:
        compressed = source.read(2) == b"\x1f\x8b"
    try:
        with (gzip.open(downloaded, "rb") if compressed else downloaded.open("rb")) as source, output.open("wb") as out:
            total = 0
            while True:
                chunk = source.read(min(65536, limit - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise DownloadError("Expanded EPG exceeded its size limit.")
                parser.Parse(chunk, False)
                out.write(chunk)
            parser.Parse(b"", True)
    except (expat.ExpatError, OSError, EOFError, zlib.error):
        raise DownloadError("EPG is malformed, truncated, or has invalid gzip data.") from None
    if not channels or not programmes:
        raise DownloadError("EPG must contain channels and programme listings.")


def atomic_copy(source, destination):
    fd, temporary = tempfile.mkstemp(prefix=".publish-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as incoming:
            shutil.copyfileobj(incoming, out)
            out.flush()
            os.fsync(out.fileno())
        # Preserve existing access mode; new media files are owner/group readable.
        mode = destination.stat().st_mode & 0o777 if destination.exists() else 0o640
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(playlist, epg, data):
    """Each file is atomic. Roll back ordinary errors; a pair is not crash-atomic."""
    pairs = [(playlist, data / "playlist.m3u"), (epg, data / "epg.xml")]
    backups, changed = {}, []
    for _, destination in pairs:
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise DownloadError("Output paths must be regular files, not directories or symlinks.")
    for _, destination in pairs:
        if destination.exists():
            backup = data / ("playlist_backup.m3u" if destination.suffix == ".m3u" else "epg_backup.xml")
            atomic_copy(destination, backup)
            backups[destination] = backup
    try:
        for source, destination in pairs:
            atomic_copy(source, destination)
            changed.append(destination)
    except BaseException:
        for destination in reversed(changed):
            if destination in backups:
                atomic_copy(backups[destination], destination)
            else:
                destination.unlink()
        raise


def save_state(path, state):
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(state, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_state(path):
    if not path.exists():
        return {"next_attempt": 0}
    try:
        state = json.loads(path.read_text())
        value = state["next_attempt"]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError
        return state
    except (ValueError, KeyError, TypeError):
        raise DownloadError("Download state is invalid; inspect .download-state.json before scheduling another run.") from None


def docker_command(args, timeout):
    try:
        return subprocess.run(["docker", *args], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=False).returncode
    except (OSError, subprocess.TimeoutExpired):
        raise DownloadError("Docker is unavailable or timed out; check the local Docker daemon and image.") from None


def clean_playlist(playlist, work, cfg):
    input_dir, output_dir = work / "input", work / "cleaned"
    input_dir.mkdir()
    output_dir.mkdir()
    shutil.copyfile(playlist, input_dir / "source.m3u")
    name = "playlist-cleaner-" + uuid.uuid4().hex
    args = ["run", "--rm", "--pull=never", "--name", name,
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--mount", f"type=bind,source={input_dir},target=/input,readonly",
            "--mount", f"type=bind,source={output_dir},target=/output",
            "-e", "M3U_DIRECTORY=/input", "-e", "OUTPUT_FILE=/output/playlist.m3u",
            "-e", "LOG_FILE=/dev/null", cfg["cleaner_image"]]
    try:
        if docker_command(args, cfg["cleaner_timeout_seconds"]) != 0:
            raise DownloadError("Cleaner failed; local playlist and EPG were preserved.")
    finally:
        # Killing the client alone does not necessarily stop its container.
        with contextlib.suppress(DownloadError):
            docker_command(["rm", "-f", name], 30)
    result = output_dir / "playlist.m3u"
    validate_playlist(result, cfg["max_download_bytes"])
    return result


def run(cfg, clean=False):
    data = Path(cfg["data_dir"]).resolve()
    if clean and "," in str(data):
        raise DownloadError("Docker bind-mount paths cannot contain commas.")
    data.mkdir(parents=True, exist_ok=True, mode=0o750)
    with (data / ".download.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Another download is running; skipped.")
            return 0
        state_path = data / ".download-state.json"
        state = read_state(state_path)
        if time.time() < state["next_attempt"]:
            log("Download interval/backoff has not elapsed; skipped.")
            return 0
        if clean and docker_command(["image", "inspect", cfg["cleaner_image"]], 30) != 0:
            raise DownloadError("Cleaner image is not available locally; docker pull the configured image first.")
        state["next_attempt"] = time.time() + cfg["min_interval_seconds"]
        save_state(state_path, state)  # Failed attempts also count, including interrupted runs.
        try:
            with tempfile.TemporaryDirectory(prefix=".download-", dir=data) as temporary:
                work = Path(temporary)
                playlist, raw_epg, epg = work / "source.m3u", work / "epg.download", work / "epg.xml"
                log("Downloading playlist.")
                download(cfg["playlist_url"], playlist, cfg)
                validate_playlist(playlist, cfg["max_download_bytes"])
                time.sleep(cfg["request_gap_seconds"])
                log("Downloading EPG.")
                download(cfg["epg_url"], raw_epg, cfg)
                prepare_epg(raw_epg, epg, cfg["max_epg_bytes"])
                if clean:
                    log("Checking channels with the Docker cleaner.")
                    playlist = clean_playlist(playlist, work, cfg)
                publish(playlist, epg, data)
                log("Published validated playlist.m3u and epg.xml; previous files backed up.")
        except RateLimited as error:
            state["next_attempt"] = max(state["next_attempt"], time.time() + error.seconds)
            save_state(state_path, state)
            raise
    return 0


def interrupted(_signum, _frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--clean", action="store_true", help="Run the configured local Docker cleaner before publishing")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration without downloading")
    args = parser.parse_args()
    os.umask(0o027)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        cfg = load_config(args.config)
        if args.check_config:
            log("Configuration is valid; no network requests made.")
            return 0
        return run(cfg, args.clean)
    except DownloadError as error:
        log(f"ERROR: {error}")
        return 1
    except OSError:
        log("ERROR: File operation failed; check disk space and directory ownership/permissions.")
        return 1
    except KeyboardInterrupt:
        log("Interrupted; any in-progress download was not published.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
