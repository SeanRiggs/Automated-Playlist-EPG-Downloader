# Changelog

## 2.0.0 — 2026-10-27

- Add a shared Python 3.10+ downloader while retaining both shell entry points.
- Support cloud redirects and Dropbox file links with preserved access parameters.
- Validate extended M3U/M3U8 channel lists and plain/gzip XMLTV before publication.
- Add bounded downloads, overlap locking, persistent attempt intervals, and server backoff.
- Stage files, keep previous-file backups, atomically replace each output, and roll back ordinary publication failures.
- Fix unattended Docker cleanup with fully qualified images, isolated input/output, valid-output checks, and container timeout cleanup.
- Add local regression coverage and real Docker integration CI for both published cleaners.
- Replace embedded URL settings with a private JSON config and document cloud setup, deployment, migration, and limits.
