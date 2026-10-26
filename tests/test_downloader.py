import contextlib
import fcntl
import gzip
import http.server
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import downloader as app

ROOT = Path(__file__).resolve().parents[1]
PLAYLIST = b'#EXTM3U url-tvg="guide.xml"\n#EXTINF:-1 tvg-id="one" group-title="News",One\n#EXTVLCOPT:http-user-agent=Player\nhttps://example.test/live.m3u8?key=private\n'
CLEANED = PLAYLIST.replace(b",One\n", b",Cleaned One\n")
EPG = b'<?xml version="1.0"?><tv><channel id="one"><display-name>One</display-name></channel><programme channel="one" start="20261027000000 +0000"><title>News</title></programme></tv>'


@contextlib.contextmanager
def server(routes):
    calls = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append(self.path)
            status, headers, body = routes.get(self.path, (404, {}, b"missing"))
            if "X-Test-Delay" in headers:
                time.sleep(float(headers["X-Test-Delay"]))
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            if "Content-Length" not in headers and "X-Test-No-Length" not in headers:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="downloader test ")
        self.root = Path(self.temp.name)
        self.data = self.root / "output files"
        self.data.mkdir()
        self.routes = {"/list": (200, {}, PLAYLIST), "/guide": (200, {}, EPG)}
        self.http = server(self.routes)
        self.base, self.calls = self.http.__enter__()
        self.cfg = app.DEFAULTS | {
            "playlist_url": self.base + "/list", "epg_url": self.base + "/guide",
            "data_dir": str(self.data), "request_gap_seconds": 0, "min_interval_seconds": 0,
        }
        self.config = self.root / "private.json"
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.http.__exit__(None, None, None))

    def cli(self, clean=False, **kwargs):
        self.config.write_text(json.dumps(self.cfg))
        wrapper = "m3u4uAutoandClean.sh" if clean else "m3u4u.sh"
        return subprocess.run([str(ROOT / wrapper), "--config", str(self.config)],
                              cwd=self.root, capture_output=True, text=True, timeout=20, **kwargs)

    def seed(self):
        (self.data / "playlist.m3u").write_bytes(b"previous playlist")
        (self.data / "epg.xml").write_bytes(b"previous guide")

    def assert_preserved(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.data / "playlist.m3u").read_bytes(), b"previous playlist")
        self.assertEqual((self.data / "epg.xml").read_bytes(), b"previous guide")
        self.assertFalse((self.data / "playlist_backup.m3u").exists())
        self.assertFalse([p for p in self.data.glob(".download-*") if p.is_dir()])

    def fake_docker(self, mode="success"):
        binary = self.root / "bin"
        binary.mkdir()
        executable = binary / "docker"
        executable.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys, time
a = sys.argv[1:]
with open(os.environ['DOCKER_CALLS'], 'a') as f: f.write(json.dumps(a) + '\\n')
mode = os.environ['FAKE_MODE']
if a[0] == 'image': sys.exit(1 if mode == 'missing' else 0)
if a[0] == 'rm': sys.exit(0)
if mode == 'timeout': time.sleep(10)
if mode == 'failure':
 print('SECRET_URL_must_never_be_logged', file=sys.stderr)
 sys.exit(7)
if mode == 'empty': sys.exit(0)
mount = next(s for s in a if 'target=/output' in s)
out = pathlib.Path(mount.split('source=', 1)[1].split(',target=', 1)[0])
out.joinpath('playlist.m3u').write_bytes(bytes.fromhex(os.environ['CLEANED_HEX']))
''')
        executable.chmod(0o755)
        self.docker_calls = self.root / "docker-calls.jsonl"
        return os.environ | {"PATH": str(binary) + os.pathsep + os.environ["PATH"],
                             "DOCKER_CALLS": str(self.docker_calls), "FAKE_MODE": mode,
                             "CLEANED_HEX": CLEANED.hex()}

    def test_wrappers_publish_preserving_metadata_and_backups(self):
        self.seed()
        os.chmod(self.data / "playlist.m3u", 0o644)
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.data / "playlist.m3u").read_bytes(), PLAYLIST)
        self.assertEqual((self.data / "epg.xml").read_bytes(), EPG)
        self.assertEqual((self.data / "playlist_backup.m3u").read_bytes(), b"previous playlist")
        self.assertEqual((self.data / "epg_backup.xml").read_bytes(), b"previous guide")
        self.assertEqual((self.data / "playlist.m3u").stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.calls, ["/list", "/guide"])

    def test_redirect_chain_and_gzip_without_filename_extension(self):
        self.routes["/list"] = (302, {"Location": "/cloud.m3u8"}, b"")
        self.routes["/cloud.m3u8"] = (307, {"Location": "/content"}, b"")
        self.routes["/content"] = (200, {}, PLAYLIST)
        self.routes["/guide"] = (200, {}, gzip.compress(EPG))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.data / "epg.xml").read_bytes(), EPG)
        self.assertEqual((self.data / "playlist.m3u").read_bytes(), PLAYLIST)

    def test_dropbox_normalization_preserves_access_key(self):
        url = "https://www.dropbox.com/scl/fi/id/file.m3u8?rlkey=secret%2Bkey&dl=0&raw=1&extra="
        self.assertEqual(app.download_url(url),
                         "https://www.dropbox.com/scl/fi/id/file.m3u8?rlkey=secret%2Bkey&extra=&dl=1")
        self.assertEqual(app.download_url("https://m3u4u.com/m3u/abc?dl=0"), "https://m3u4u.com/m3u/abc?dl=0")
        self.assertEqual(app.download_url("https://dropbox.com.evil.test/s/a?dl=0"),
                         "https://dropbox.com.evil.test/s/a?dl=0")

    def test_playlist_html_empty_incomplete_and_hls_rejected(self):
        self.seed()
        for body in (b"<html>Sign in</html>", b"", b"#EXTM3U\n", b"#EXTM3U\n#EXTINF:-1,Incomplete\n",
                     b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n"):
            with self.subTest(body=body):
                self.routes["/list"] = (200, {}, body)
                self.assert_preserved(self.cli())
        self.assertNotIn("/guide", self.calls)

    def test_guide_html_truncated_empty_and_custom_entities_rejected(self):
        self.seed()
        for body in (b"<html>Sign in</html>", b"<tv><channel>", b"<tv/>",
                     b'<!DOCTYPE tv [<!ENTITY bad "secret">]><tv>&bad;</tv>',
                     gzip.compress(EPG)[:-5]):
            with self.subTest(body=body):
                self.routes["/guide"] = (200, {}, body)
                self.assert_preserved(self.cli())

    def test_xmltv_external_doctype_is_not_fetched(self):
        self.routes["/guide"] = (200, {}, b'<!DOCTYPE tv SYSTEM "' + self.base.encode() + b'/must-not-fetch.dtd">' + EPG.split(b"?>", 1)[1])
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.calls, ["/list", "/guide"])

    def test_http_error_and_private_urls_not_logged(self):
        self.seed()
        self.cfg["epg_url"] = self.base + "/secret-token?password=secret"
        self.assert_preserved(result := self.cli())
        self.assertNotIn("secret", result.stdout + result.stderr)

    def test_partial_content_and_truncated_transfer_rejected(self):
        self.seed()
        for status, headers in ((206, {}), (200, {"Content-Length": str(len(PLAYLIST) + 100)})):
            self.routes["/list"] = (status, headers, PLAYLIST)
            self.assert_preserved(self.cli())

    def test_redirect_loop_and_non_http_redirect_rejected(self):
        self.seed()
        for location in ("/list", "file:///etc/passwd"):
            self.routes["/list"] = (302, {"Location": location}, b"")
            self.assert_preserved(self.cli())

    def test_https_downgrade_rejected(self):
        req = urllib.request.Request("https://example.test/list")
        with self.assertRaises(app.DownloadError):
            app.Redirects().redirect_request(req, None, 302, "Found", {}, "http://example.test/list")

    def test_size_limits_with_and_without_content_length(self):
        self.seed()
        self.cfg["max_download_bytes"] = 20
        for headers in ({}, {"X-Test-No-Length": "yes"}):
            self.routes["/list"] = (200, headers, PLAYLIST)
            self.assert_preserved(self.cli())

    def test_gzip_expansion_limit(self):
        self.seed()
        self.cfg["max_epg_bytes"] = 40
        self.routes["/guide"] = (200, {}, gzip.compress(EPG))
        self.assert_preserved(self.cli())

    def test_socket_timeout_keeps_files(self):
        self.seed()
        self.cfg["socket_timeout_seconds"] = 1
        self.routes["/list"] = (200, {"X-Test-Delay": "2"}, PLAYLIST)
        self.assert_preserved(self.cli())

    def test_elapsed_download_budget_keeps_files(self):
        self.seed()
        self.cfg["download_timeout_seconds"] = 1
        self.routes["/list"] = (200, {"X-Test-Delay": "2"}, PLAYLIST)
        self.assert_preserved(self.cli())

    def test_sigterm_keeps_files_and_cleans_temporary_directory(self):
        self.seed()
        self.routes["/list"] = (200, {"X-Test-Delay": "2"}, PLAYLIST)
        self.config.write_text(json.dumps(self.cfg))
        with subprocess.Popen([str(ROOT / "m3u4u.sh"), "--config", str(self.config)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            deadline = time.monotonic() + 5
            while not self.calls and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(self.calls, "process did not start its request")
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 130, stdout + stderr)
            self.assert_preserved(subprocess.CompletedProcess([], process.returncode, stdout, stderr))

    def test_failed_attempt_also_obeys_interval(self):
        self.cfg["min_interval_seconds"] = 82800
        self.routes["/list"] = (403, {}, b"Forbidden")
        self.assertEqual(self.cli().returncode, 1)
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.calls, ["/list"])

    def test_retry_after_extends_backoff(self):
        self.routes["/list"] = (429, {"Retry-After": "172800"}, b"Slow down")
        self.assertEqual(self.cli().returncode, 1)
        state = json.loads((self.data / ".download-state.json").read_text())
        self.assertGreater(state["next_attempt"], time.time() + 172790)
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(len(self.calls), 1)

    def test_retry_after_date_and_invalid_header(self):
        self.assertEqual(app.retry_delay("invalid"), 86400)
        self.assertEqual(app.retry_delay("Thu, 01 Jan 1970 00:00:00 GMT"), 0)
        self.assertEqual(app.retry_delay("120"), 120)

    def test_overlap_lock_prevents_requests(self):
        with (self.data / ".download.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Another download", result.stdout)
        self.assertEqual(self.calls, [])

    def test_bad_state_fails_closed(self):
        (self.data / ".download-state.json").write_text('{"next_attempt": "invalid"}')
        self.assertEqual(self.cli().returncode, 1)
        self.assertEqual(self.calls, [])

    def test_cleaner_uses_actual_output_and_cron_safe_arguments(self):
        result = self.cli(clean=True, env=self.fake_docker())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.data / "playlist.m3u").read_bytes(), CLEANED)
        calls = [json.loads(s) for s in self.docker_calls.read_text().splitlines()]
        command = next(c for c in calls if c[0] == "run")
        self.assertEqual(command[-1], "seanriggs/m3u-playlist-cleaner:latest")
        self.assertNotIn("-ti", command)
        self.assertNotIn("-it", command)
        self.assertIn("OUTPUT_FILE=/output/playlist.m3u", command)
        self.assertTrue(any("target=/input,readonly" in s for s in command))
        self.assertIn("rm", calls[-1])

    def test_cleaner_failure_and_empty_success_preserve_files(self):
        self.seed()
        env = self.fake_docker()
        for mode in ("failure", "empty"):
            with self.subTest(mode=mode):
                self.assert_preserved(result := self.cli(clean=True, env=env | {"FAKE_MODE": mode}))
                self.assertNotIn("SECRET_URL", result.stdout + result.stderr)

    def test_cleaner_timeout_removes_container(self):
        self.seed()
        self.cfg["cleaner_timeout_seconds"] = 1
        self.assert_preserved(self.cli(clean=True, env=self.fake_docker("timeout")))
        self.assertEqual(json.loads(self.docker_calls.read_text().splitlines()[-1])[:2], ["rm", "-f"])

    def test_missing_cleaner_fails_before_download(self):
        self.assertEqual(self.cli(clean=True, env=self.fake_docker("missing")).returncode, 1)
        self.assertEqual(self.calls, [])

    def test_atomic_publish_failure_rolls_back_first_file(self):
        self.seed()
        playlist, epg = self.root / "new.m3u", self.root / "new.xml"
        playlist.write_bytes(PLAYLIST)
        epg.write_bytes(EPG)
        original = app.atomic_copy

        def fail_second(source, destination):
            if source == epg:
                raise OSError("simulated full disk")
            original(source, destination)

        with patch.object(app, "atomic_copy", side_effect=fail_second), self.assertRaises(OSError):
            app.publish(playlist, epg, self.data)
        self.assertEqual((self.data / "playlist.m3u").read_bytes(), b"previous playlist")
        self.assertEqual((self.data / "epg.xml").read_bytes(), b"previous guide")

    def test_config_validation_and_check_does_not_download(self):
        for changes in ({"playlist_url": "file:///etc/passwd"}, {"playlist_url": "https://user:secret@example.test/a"},
                        {"epg_url": "https://m3u4u.com/xml/YOUR_EPG_CODE"},
                        {"max_download_bytes": True}, {"unknown": 1}, {"data_dir": "relative"}):
            with self.subTest(changes=changes):
                self.config.write_text(json.dumps(self.cfg | changes))
                with self.assertRaises(app.DownloadError):
                    app.load_config(self.config)
        self.config.write_text(json.dumps(self.cfg))
        result = subprocess.run([sys.executable, str(ROOT / "downloader.py"), "--config", str(self.config), "--check-config"], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls, [])


@unittest.skipUnless(os.environ.get("RUN_DOCKER_TESTS") == "1", "real Docker integration is opt-in")
class DockerIntegrationTests(unittest.TestCase):
    def test_published_cleaner_end_to_end(self):
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\0\0" * 8000)
        routes = {"/guide": (200, {}, gzip.compress(EPG)),
                  "/media.wav": (200, {"Content-Type": "audio/wav"}, stream.getvalue())}
        with server(routes) as (base, _), tempfile.TemporaryDirectory() as tmp:
            host = os.environ.get("DOCKER_TEST_HOST", "172.17.0.1")
            media_base = base.replace("127.0.0.1", host)
            routes["/list"] = (200, {}, b"#EXTM3U\n#EXTINF:-1 tvg-id=\"one\",One\n" + media_base.encode() + b"/media.wav\n")
            cfg = app.DEFAULTS | {"playlist_url": base + "/list", "epg_url": base + "/guide",
                                  "data_dir": tmp, "request_gap_seconds": 0, "min_interval_seconds": 0,
                                  "cleaner_image": os.environ.get("CLEANER_TEST_IMAGE", app.DEFAULTS["cleaner_image"])}
            self.assertEqual(app.run(cfg, clean=True), 0)
            playlist = Path(tmp) / "playlist.m3u"
            self.assertEqual(app.validate_playlist(playlist, cfg["max_download_bytes"]), 1)
            before = playlist.read_bytes()
            self.assertIn(b"/media.wav", before)
            self.assertEqual((Path(tmp) / "epg.xml").read_bytes(), EPG)
            # The simple cleaner exits zero even if all channels fail: missing output must fail closed.
            routes["/media.wav"] = (404, {}, b"gone")
            with self.assertRaises(app.DownloadError):
                app.run(cfg, clean=True)
            self.assertEqual(playlist.read_bytes(), before)
            self.assertEqual((Path(tmp) / "epg.xml").read_bytes(), EPG)


if __name__ == "__main__":
    unittest.main()
