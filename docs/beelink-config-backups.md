# Beelink configuration backups

## Where things are stored

| Data | Live location | Synology copy |
| --- | --- | --- |
| Uptime Kuma monitors, groups, history, settings, and uploads | Beelink `/opt/admin/uptime-kuma` | Encrypted daily snapshot |
| Sonarr and Radarr databases and settings | Beelink `/opt/media/{sonarr,radarr}/config` | Encrypted daily snapshot. Both apps also keep weekly ZIPs in their live `Backups/scheduled` directories. |
| Jellyseerr database and settings | Synology `/volume1/jellyfin/config/jellyseerr` | Encrypted daily snapshot |
| Transmission settings, bandwidth groups, and scheduled scripts | Synology `/volume1/jellyfin/config/transmission` | Encrypted daily snapshot |
| iSponsorBlockTV settings, helper scripts, and active Compose and environment files | Beelink `/opt/stacks/{admin,media}` | Encrypted daily snapshot |
| Jellyfin | Beelink `/opt/media/jellyfin/config` | Existing nightly mirror at `/volume1/jellyfin/config/jellyfin-local-backup` |
| Bazarr and Prowlarr | Synology `/volume1/jellyfin/config/{bazarr,prowlarr}` | Existing app backups in `bazarr/backup` and `prowlarr/Backups/scheduled` |

The encrypted snapshots are in `/volume1/jellyfin/config/beelink-backups` on the Synology, mounted at `/mnt/synology/jellyfin/config/beelink-backups` on Beelink. Names end in `.tar.gz.gpg` and use a UTC timestamp. The snapshot job keeps each successful run. Synology Hyper Backup sends the `jellyfin/config` subtree to the existing **Beelink config to S3** task. Use that task’s Backup Explorer to retrieve an off-site version.

Git contains the reusable Compose definitions, environment examples, this guide, and the [backup script](../beelink/admin/backup-configs.py). Live `.env` files, application databases, credentials, and the recovery key belong in private storage. Video files and Transmission download state are outside this configuration backup.

## Schedule and alerts

- Beelink cron runs the backup daily at **19:15 Beelink host time**, which is **02:15 in Israel** when the time difference is seven hours. The job runs before Hyper Backup even when daylight-saving changes shift the offset.
- Synology Hyper Backup runs daily at **05:30 Synology time**. The latest Jellyfin mirror at that point may be from the previous night.
- Uptime Kuma’s **Beelink Config Backup to Synology** monitor reports a success after the NAS copy passes checksum verification. Kuma sends a Telegram alert on failure or if the heartbeat is more than 26 hours old. Check the Hyper Backup task separately for S3 status.

## Recover a snapshot

1. Copy the desired encrypted archive from the Synology or restore it through Hyper Backup’s Backup Explorer.
2. Use the recovery key in `~/.config/beelink-config-backup/recovery.key`. There are copies on Beelink and the Mac used to set up the job. Keep an offline copy with your other recovery credentials.
3. Decrypt to a private staging directory on a machine with GnuPG. List the archive before extracting it.

   ```sh
   umask 077
   gpg --output config.tar.gz --decrypt beelink-config-<timestamp>.tar.gz.gpg
   tar -tzf config.tar.gz
   ```

   Enter the recovery key at the prompt. Archive entries use paths relative to `/`. The SQLite files are standalone snapshots with their committed data included.

4. Extract into a staging directory and run `PRAGMA quick_check;` against any database you plan to restore. Stop the affected container before replacing its live files. Save a copy of its current config and restore the original ownership and permissions before starting it again.

## Run on demand

Run on Beelink as the account that owns the backup job:

```sh
/usr/bin/timeout 20m /usr/bin/python3 /opt/stacks/admin/config-backup/backup-configs.py
```

The cron log is `/opt/stacks/admin/config-backup/backup.log`. The Kuma push URL is in the private `~/.config/beelink-config-backup/push-url` file. To send a snapshot to S3 immediately, run **Back Up Now** on the **Beelink config to S3** task after confirming the NAS copy is present.
