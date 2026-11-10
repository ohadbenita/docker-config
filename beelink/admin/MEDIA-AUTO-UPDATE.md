# Media image updates

The Beelink media images are checked by WUD at 04:00 Asia/Jerusalem. A per-minute cron guard invokes the WUD media-only Compose trigger at 04:15 Asia/Jerusalem, after the scan completes. It selects only update candidates from the media Compose project.

Monitor the WUD dashboard at http://192.168.1.167:3000 and the run log at /opt/stacks/admin/media-auto-update.log. The active and tracked Compose image references are kept in sync after each update.

WUD is pinned to 9.8.0 with Compose rollback enabled. It waits 60 seconds for each replacement container to remain running. The updater also stores each run's prior image IDs and references under /opt/stacks/admin/media-update-state as a manual fallback. To roll back the last run, run:

    /usr/bin/python3 /opt/stacks/admin/media-update.py --rollback

The rollback restores the prior local images and Compose references, then recreates only services updated in that run. No image pruning is enabled. Telegram reports update availability, start, success, failure, and rollback events. Containers do not have Docker healthchecks, so WUD's 60-second grace period verifies only that a replacement remains running, not application-level health.
