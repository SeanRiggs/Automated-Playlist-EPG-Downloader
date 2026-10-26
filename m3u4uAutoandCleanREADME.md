# Optional Docker cleanup

Use the [main setup guide](README.md) to configure cloud delivery, private download URLs, and the output directory first. Then use `m3u4uAutoandClean.sh` in place of `m3u4u.sh`.

## Choose and pull an image

The default remains the basic cleaner:

```sh
docker pull seanriggs/m3u-playlist-cleaner:latest
./m3u4uAutoandClean.sh --check-config
./m3u4uAutoandClean.sh
```

For FFprobe-based audio/video validation, set this property in your `config.json`:

```json
"cleaner_image": "seanriggs/advanced-ffprobe-m3u-cleaner:latest"
```

Then pull it before running:

```sh
docker pull seanriggs/advanced-ffprobe-m3u-cleaner:latest
./m3u4uAutoandClean.sh
```

Both integrations are covered by real Docker CI tests. They have different validation and metadata behavior; consult the [basic cleaner](https://github.com/SeanRiggs/m3u-playlist-cleaner) and [advanced cleaner](https://github.com/SeanRiggs/advanced-ffprobe-m3u-cleaner) documentation. Stream checks contact channel URLs and may consume provider connections. Temporary network failures can exclude channels, so cleanup is optional.

There is no need to clone either cleaner repository, build it locally, or add a Docker Hub publishing token. Docker must be available to the scheduled user on the **same host**. Update images deliberately with `docker pull`; a digest reference can pin an exact release. The job checks that the selected image is installed before downloading files.

## How publication works

1. Download and validate both the channel list and guide in a private temporary directory.
2. Give Docker only that new playlist through a read-only `/input` mount and a separate writable `/output` mount.
3. Run without `-i` or `-t`, with the scheduled user's UID/GID. The cleaner receives `M3U_DIRECTORY=/input`, `OUTPUT_FILE=/output/playlist.m3u`, and `LOG_FILE=/dev/null`.
4. Require a successful process **and a valid, nonempty output playlist**. Read the cleaner output, never fall back to its input. Stop/remove its container on timeout.
5. Publish the cleaned playlist and downloaded XMLTV using the backup/replacement workflow described in the main README.

The published guide is structurally validated but is not filtered to the surviving channels. Detailed cleaner output is suppressed because it may contain private stream URLs; console logs report pipeline success/failure. If you need detailed channel diagnosis, run the cleaner separately with private test files and follow its own logging instructions.

Schedule only this wrapper for cleanup mode; the shared lock and interval state prevent overlapping runs. A cleanup failure leaves the existing playlist and guide available and returns a nonzero exit status.
