# Beelink backup and recovery

If Beelink is down, start with the latest encrypted snapshot on the Synology. If the Synology is also unavailable, use the existing S3 Hyper Backup repository. Get the [Beelink Backup Recovery Key](https://start.1password.com/open/i?a=ATF4FB73IJEBLO6AJQYPAXXZQ4&h=lightricks.1password.com&i=itpslnwnpmwbyxwczuwhqqef2q&v=tqvf63zfjfcnnxnj6sm4izmjuy) from 1Password before you restore.

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

Git contains the reusable Compose definitions, environment examples, this guide, and the [backup script](backup-configs.py). Live `.env` files, application databases, credentials, and the recovery key belong in private storage. Video files and Transmission download state are outside this configuration backup.

## Schedule and alerts

- Beelink cron runs the backup daily at **19:15 Beelink host time**, which is **02:15 in Israel** when the time difference is seven hours. The job runs before Hyper Backup even when daylight-saving changes shift the offset.
- Synology Hyper Backup runs daily at **05:30 Synology time**. The latest Jellyfin mirror at that point may be from the previous night.
- Uptime Kuma’s **Beelink Config Backup to Synology** monitor reports a success after the NAS copy passes checksum verification. Kuma sends a Telegram alert on failure or if the heartbeat is more than 26 hours old.
- Uptime Kuma’s **Beelink Config Backup to S3** monitor compares the newest Synology snapshot’s name, size, and modification time with the file catalog for the latest completed S3 version. A new snapshot can wait until 90 minutes after the next 05:30 Israel time upload if an earlier local snapshot is present in S3. Kuma sends a Telegram alert for a missing or mismatched snapshot, a completed version more than 28 hours old, a failed check, or two hours without a heartbeat. Use Backup Explorer to download and verify the archive contents.

## Recover a snapshot

1. Copy the desired encrypted archive from the Synology. For the off-site copy, open **Hyper Backup → Beelink config to S3 → Backup Explorer**, select a restore point, then open **jellyfin / config / beelink-backups**. If the original NAS is unavailable, connect Hyper Backup on a replacement Synology to the existing Amazon S3 repository under the `beelink-config` directory.
2. Open the 1Password item linked above, then use the **Recovery key** field. The item is in the Lightricks **Employee** vault and requires vault access. There are also file copies at `~/.config/beelink-config-backup/recovery.key` on Beelink and the Mac used to set up the job. Keep an offline copy with your other recovery credentials.
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

Run the S3 check on demand with:

```sh
/usr/bin/timeout 7m /usr/bin/python3 /opt/stacks/admin/config-backup/backup-configs.py --check-s3
```

The S3 check log is `/opt/stacks/admin/config-backup/s3-check.log`. The curl credentials, S3 endpoint, Kuma push URL, and cached catalog entries live in `~/.config/beelink-config-backup`. The job caches the file catalog for the current completed version. A Hyper Backup format change that prevents catalog verification causes the monitor to fail.

When rotating the `beelink-s3-backup-monitor` AWS credential, scope `s3:ListBucket` to the completion prefix and `s3:GetObject` to the jellyfin share's catalog database objects. Verify a successful heartbeat before retiring the previous key.
