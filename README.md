# Automated Playlist & EPG Downloader

A dependable local copy of your channel list and TV guide—even when the next download fails.

Download an extended M3U/M3U8 playlist and XMLTV guide, validate both, optionally check channels with a Docker cleaner, then publish `playlist.m3u` and `epg.xml` for your media server. The original shell entry points remain available; a shared Python implementation now handles downloads and validation.

[![Tests](https://github.com/SeanRiggs/Automated-Playlist-EPG-Downloader/actions/workflows/test.yml/badge.svg)](https://github.com/SeanRiggs/Automated-Playlist-EPG-Downloader/actions/workflows/test.yml)

## Does this still help with m3u4u's cloud downloads?

**Yes, when you want local files, controlled refreshes, backups, or optional channel checks.** If your player already reads your cloud playlist and guide reliably and you do not need those features, you can use those URLs directly without this project.

Set up m3u4u's Dropbox delivery in your m3u4u account first. This downloader consumes the resulting download URLs; it does not replace cloud setup, synchronize your provider into m3u4u, publish updates to Dropbox, or manage Dropbox app keys, secrets, and access codes. A successful download cannot make an upstream file fresher than its last publication.

1. Follow the current cloud setup instructions in [m3u4u](https://m3u4u.com/) / its [help wiki](https://wiki.m3u4u.com/).
2. Ensure your playlist and guide have been published successfully. Copy the actual download URLs shown in your account; the example code strings in this repository are placeholders.
3. Put those URLs in your private `config.json`. Prefer the stable m3u4u download URLs when provided. Do not copy a temporary final CDN redirect URL.
4. If using a Dropbox **file** sharing link instead, the downloader converts its display parameters to `dl=1`, preserves access parameters such as `rlkey`, and follows HTTP(S) redirects. Sign-in pages, preview HTML, and missing/expired links fail validation.

Dropbox documents both download-link parameters and redirects in its [download-link guide](https://help.dropbox.com/share/force-download). A [2026 Dropbox Community discussion](https://community.dropbox.com/en/discussion/857034/dropbox-access-code-for-m3u4u-exceeds-256-characters-how-can-i-solve-this) also describes m3u4u's Dropbox setup. We could not independently inspect m3u4u's signed-in settings or read its wiki during this refresh; exact account screens, publication schedules, and service limits must be checked there. No live account credentials are used in this project's tests.

## What it does

- Follows cloud download redirects, with TLS verification and no HTTPS-to-HTTP downgrade.
- Accepts UTF-8 extended channel playlists regardless of the URL's file extension. An HLS `.m3u8` URL **inside** a channel list is fine; an HLS segment/master manifest is not a channel list.
- Accepts plain XMLTV or gzip-compressed XMLTV, detected by file content. Published `epg.xml` is always uncompressed.
- Rejects empty, malformed, partial, oversized, or HTML responses. XMLTV must contain channels and programme listings; custom XML entities are rejected and external DTDs are not fetched.
- Downloads to temporary files on the destination filesystem. Only after both files and optional cleaner output pass does it replace the local files.
- Preserves the previous published files as `playlist_backup.m3u` and `epg_backup.xml`.
- Prevents overlapping runs and records failed attempts as well as successful ones for its local download interval. HTTP 429/503 responses extend the delay using `Retry-After` when supplied.
- Keeps private source URLs and cleaner diagnostics out of its console log.

It downloads playlist/guide **metadata**, not recordings of the channels. The default mode checks file structure; it does not probe channel availability or prove that guide listings are current.

## Install

Use Linux with **Python 3.10 or newer**. No pip packages, curl, PHP, or Composer are required for downloads. Docker is optional and must run on the same host for cleanup mode.

On Debian/Ubuntu, for example:

```sh
sudo apt-get update
sudo apt-get install git python3 ca-certificates
git clone https://github.com/SeanRiggs/Automated-Playlist-EPG-Downloader.git
cd Automated-Playlist-EPG-Downloader
cp config.example.json config.json
chmod 600 config.json
```

Edit `config.json` with your playlist URL, EPG URL, and an absolute output directory. Keep the URLs private; `config.json` is ignored by Git. Configure a directory your scheduled user can write:

```sh
sudo install -d -m 750 -o "$(id -u)" -g "$(id -g)" /opt/mediastream/m3ufiles
./m3u4u.sh --check-config
./m3u4u.sh
```

The config check makes no network requests. A normal run waits 60 seconds between the playlist and EPG downloads by default. Run it as your normal service user, not through sudo, after directory permissions are set.

Both wrappers find `downloader.py` beside themselves and default to that directory's `config.json`, regardless of the working directory. Keep the checkout together. An external config works too:

```sh
/path/to/Automated-Playlist-EPG-Downloader/m3u4u.sh --config /path/to/private/config.json
```

## Optional Docker cleanup

The downloader has **no Docker image of its own**. Cleanup uses an existing published cleaner image:

```sh
docker pull seanriggs/m3u-playlist-cleaner:latest
./m3u4uAutoandClean.sh
```

The scheduled user needs access to the local Docker daemon. See the [cleanup guide](m3u4uAutoandCleanREADME.md) for the advanced FFprobe alternative, image updates, and limits. Pull the selected image before running: scheduled jobs deliberately use the locally installed image and do not silently upgrade it.

## Schedule one mode

Use `crontab -e` as the same user who owns the output directory. Replace the checkout path with its real absolute path. This example runs at 02:17 in the **server's timezone**:

```cron
17 2 * * * /path/to/Automated-Playlist-EPG-Downloader/m3u4u.sh >> /opt/mediastream/m3ufiles/m3u4u.log 2>&1
```

For cleanup, replace `m3u4u.sh` with `m3u4uAutoandClean.sh`; do not schedule both. Use a time after your upstream cloud publication normally completes. Rotate the log using your host's log rotation tools.

The default local interval is **23 hours between attempt starts**, allowing a daily cron job some timing variation. The 60-second request gap and 23-hour interval are conservative project defaults, **not verified m3u4u limits and not a guarantee against throttling**. Follow your service's current rules and increase them as needed. There are no automatic retries within a run.

A second run during the interval, server backoff, or an active download skips without contacting the source and exits 0. An error exits 1; an interrupted run exits 130. Check the log to distinguish a published update from a skipped run. Keep the same `data_dir` to retain scheduling state. Do not delete state to repeatedly retry a throttled service.

## Configuration

All settings belong in the JSON file. URLs are required; unspecified optional settings use these defaults. JSON does not support comments.

| Key | Default | Purpose |
| --- | --- | --- |
| `playlist_url` | Required | Extended M3U/M3U8 download URL, HTTP(S). |
| `epg_url` | Required | XMLTV or gzip XMLTV download URL, HTTP(S). |
| `data_dir` | `/opt/mediastream/m3ufiles` | Absolute directory for published files, backups, lock, and state. |
| `request_gap_seconds` | `60` | Wait between the two source downloads. |
| `min_interval_seconds` | `82800` | Minimum time between attempt starts, including failures. |
| `socket_timeout_seconds` | `30` | Timeout for blocking network operations. |
| `download_timeout_seconds` | `300` | Elapsed download budget checked between reads; a blocked network operation can add up to its socket timeout. |
| `max_download_bytes` | `104857600` | Maximum bytes for each downloaded file (100 MiB). |
| `max_epg_bytes` | `524288000` | Maximum uncompressed XMLTV size (500 MiB). |
| `cleaner_image` | `seanriggs/m3u-playlist-cleaner:latest` | Local image used only in cleanup mode. |
| `cleaner_timeout_seconds` | `3600` | Maximum cleaner runtime before stopping its container. |

Unknown config keys fail early. Intervals may be zero for isolated tests; do not copy test settings into a scheduled production job. URLs with embedded `user:password@host` are rejected; ordinary credential-bearing query/path parameters are preserved but not printed.

## Connect your media server

Point a client that supports local M3U/XMLTV inputs at:

```text
/opt/mediastream/m3ufiles/playlist.m3u
/opt/mediastream/m3ufiles/epg.xml
```

For a containerized media server, add a read-only **directory** mount to its existing Compose service, for example:

```yaml
volumes:
  - /opt/mediastream/m3ufiles:/iptv:ro
```

Then configure the client to read `/iptv/playlist.m3u` and `/iptv/epg.xml`. Mount the directory rather than individual files so atomic replacements remain visible. Arrange shared-group access if the reader uses a different account: new media files are created with mode `0640`; existing file modes are preserved. Keep the directory writable only by its owner, and keep credentials/backups out of public web roots.

## Safety and troubleshooting

- **HTTP error or HTML response:** confirm cloud authorization, successful publication, and the current download URLs in your account. The script cannot sign in or renew your cloud access.
- **Guide not updated:** this checks syntax and nonempty listings, not listing dates or channel-ID matches. Check upstream publication and your media server's refresh settings.
- **Skipped after a failed attempt:** expected interval/backoff protection. Correct the problem and wait for the next eligible scheduled attempt.
- **Cleaner failed or produced no channels:** both current local files remain. Confirm the image is pulled and the Docker daemon is accessible. A valid cleaner output can still omit temporarily unavailable channels; use download-only mode if that tradeoff is unsuitable.
- **Permission error:** the scheduled account must own/write the destination directory. For cleanup, Docker uses that account's UID/GID. Remote Docker daemons and bind-mount paths containing commas are not supported.
- **Recovery:** stop the scheduled job before restoring `playlist_backup.m3u` or `epg_backup.xml`. These are the immediately previous files, not a versioned backup archive.

Each published file is replaced atomically, so readers do not see half-written files. The two files are separate replacements, **not a transaction across both names**. Ordinary publication errors trigger rollback, but a power loss or forced kill between replacements can leave different generations; keep backups. Download/validation/cleaner failures happen before publication and preserve both existing files. A forced kill can leave a private temporary directory to remove after confirming no job is active.

## Upgrade from the original scripts

See [UPGRADING.md](UPGRADING.md) before replacing an existing scheduled installation. The shell filenames and final output filenames are retained, but URLs/configuration now live in JSON and Python 3.10+ is required. Embedded settings in an old copied shell script are not imported automatically.

## Tests and contributions

```sh
sh -n m3u4u.sh m3u4uAutoandClean.sh
python3 -m unittest discover -s tests -v
```

Tests use a local HTTP server, generated XMLTV/media, and a controlled Docker stub. They cover redirects, gzip, invalid downloads, timeouts, cooldowns, locking, credential-safe errors, cleaner failures, and publication rollback. GitHub Actions also runs the complete pipeline with the **real published basic and advanced cleaner images** against a locally generated WAV stream. It uses no live provider accounts. See the workflow for the opt-in Docker test command.

Useful contributions include new cloud redirect fixtures, XMLTV compatibility cases, and clear troubleshooting examples. Include a regression test for behavior changes. Use synthetic playlists and guides; remove private URLs, access codes, and customer/channel data from bug reports.

MIT licensed; see [LICENSE](LICENSE).
