# Upgrade to version 2

The original two scripts embedded URLs and downloaded directly into the live files. Version 2 shares a Python implementation, follows cloud redirects, validates downloads, and stages changes before publication.

1. Pause the old cron entry. Keep a private copy of its URL/path settings and the current playlist/guide outside the checkout.
2. Install Python 3.10+ and obtain the updated repository. If you edited tracked scripts in an existing checkout, preserve those edits before updating; do not force-reset your private settings.
3. Copy `config.example.json` to `config.json`, make it mode `0600`, and transfer `PLAYLIST_URL` to `playlist_url`, `EPG_URL` to `epg_url`, and `M3UFILES_DIR` to `data_dir`. Use an absolute path. Existing output filenames stay `playlist.m3u` and `epg.xml`.
4. Recheck cloud authorization/publication and the actual download URLs in m3u4u. The downloader does not set up Dropbox or push files into it. HTTPS is preferred. See the README's cloud section.
5. Run `./m3u4u.sh --check-config`, then one manual download. For cleanup, pull the fully qualified image and use `./m3u4uAutoandClean.sh` instead. Do not run both modes as a test back-to-back: the shared interval intentionally skips the second attempt.
6. Check the log and your media client's access to both files. New files use mode `0640`; existing file access modes are preserved. Arrange shared group access when the media server uses a separate account. Mount the output directory, not individual output files, into containers.
7. Change cron to point at the new checkout's wrapper. Keep the wrapper, `downloader.py`, and its configuration together. Log output now goes to stdout/stderr; use the README's cron redirection in place of the old embedded `LOGFILE` setting.

The old `m3u` staging directory and cloned cleaner source are no longer needed by this downloader. Leave any copies used by other jobs intact. There is no automatic migration or deletion of those directories.

Both wrappers now return nonzero for download, validation, or cleaner failures. A busy lock, local interval, or server backoff produces a logged skip with exit code 0. Failed attempts also count toward the interval. Existing playlists are not rewritten during an upgrade until a complete new run passes validation.

This update changes repository code and instructions; installing it on a server and updating that server's cron remain separate deployment steps.
