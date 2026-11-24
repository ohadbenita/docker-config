# Backup and Docker recovery

Central guide for Synology and Beelink Docker stacks. Live settings were checked in DSM and on Beelink on **2026-11-24**. Recheck status in DSM before a recovery.

## Hyper Backup tasks

Both tasks target Amazon S3 bucket `hass-config-backup-benita`. Transfer encryption is enabled and client-side encryption is disabled for both, so no Hyper Backup decryption key is required.

| DSM task | Source | S3 target | Schedule and retention | Status observed |
| --- | --- | --- | --- | --- |
| **Backup hass config** | Whole `Media` shared folder; filters off; no applications selected | `hass-config-backup-benita / hass-config` | Daily 19:40; 30 versions, remove earliest first | Success; last 2026-11-23 19:56; next 2026-11-24 19:40. Integrity check 2026-11-22 02:06. |
| **Beelink config to S3** | Whole `jellyfin` shared folder; filters off; no applications selected | `hass-config-backup-benita / beelink-config` | Daily 05:30; Smart Recycle, max 64 versions | Success; last 2026-11-24 05:31; next 2026-11-25 05:30. Integrity check 2026-11-21 00:23. |

Times are DSM local time. Both tasks include DSM system configurations automatically. No other Hyper Backup task appeared in the task list.

**Important source scope:** despite its name, **Backup hass config** selects all of `Media`, not only HA files. **Beelink config to S3** selects all of `jellyfin`, not only `jellyfin/config`. The Beelink GPG archive itself excludes video files and Transmission download state, but the broader Hyper Backup source can include other content in the `jellyfin` share.

## Synology data covered by the HA task

The active Home Assistant Compose definition stores its bind-mounted data under the backed-up `Media` share. The whole-share selection includes:

- HA config: `/volume1/Media/SmartHome/Config/HASS`
- MariaDB database and config: `.../Config/mariadb` and `.../Config/mariadb-conf/conf.d`
- Mosquitto: `.../Config/mqtt/{config,data,log}`
- Tasmoadmin: `.../Config/tasmoadmin/data`
- Zigbee2MQTT: `.../Config/zigbee2mqtt/{main-floor-data,upper-floor-data}`
- Matter Server: `.../Config/matter-server/data`
- HA SSH keys: `.../Config/HomeAssistant/.sshkeys`
- Cloudflare tunnel and code-server config under `/volume1/Media/SmartHome/Config`

The MariaDB data directory at /volume1/Media/SmartHome/Config/mariadb is included as live database files, not as a separate SQL dump. The checked Compose and DSM settings show no MariaDB-specific export, and no MariaDB restore test was performed during this review. Stop MariaDB before a file-level restore and verify the database before starting Home Assistant.

DSM listed 13 running containers, including Home Assistant and MariaDB; no Traccar or Synology media container was running. The whole-share task includes the Docker config checkout at `/volume1/Media/SmartHome/Backup/docker-compose` and tracked Synology media and Traccar bind mounts in `Media`. See the tracked definitions: [HA](../hass/docker-compose.yaml), [Synology media](../media/docker-compose.yaml), [admin](../admin/docker-compose.yaml), [network](../network/docker-compose.yaml), and [Traccar](../traccar/docker-compose.yaml).

### Coverage gaps

Nextcloud is retired. Its tracked Compose file and guide have been removed. No `nextcloud` directory exists under `/volume1/Media/SmartHome/Config`, and no Nextcloud container was running in DSM. Any old Docker-managed named volumes were not located in the shared folders and are not part of the active recovery plan.

- The Portainer data folder exists at `/volume1/Media/SmartHome/Config/portainer` and is covered by the whole-`Media` task. Portainer is running, but its Compose definition is not tracked, so service recreation steps still need documenting.
- DSM showed a custom `telegram-relay` container absent from tracked Compose files. It is created from inline Python rather than a tracked source file; its restore definition is not documented. Keep its token in protected secret storage.
- The tasks cover tracked bind mounts under `Media` and `jellyfin`. They do not prove Docker-managed named volumes outside those shares are protected. Verify each volume’s physical path before relying on it.

## Beelink data and scheduled jobs

Active Compose files: `/opt/stacks/admin/compose.yaml` and `/opt/stacks/media/compose.yaml`. Tracked files: [admin](../beelink/admin/docker-compose.yaml) and [media](../beelink/media/docker-compose.yaml). Data is on Beelink disks and the Synology NFS share `172.16.0.9:/volume1/jellyfin` mounted at `/mnt/synology/jellyfin`.

The encrypted snapshot script is [backup-configs.py](../beelink/admin/config-backup/backup-configs.py), installed at `/opt/stacks/admin/config-backup/backup-configs.py`. It includes Uptime Kuma, Sonarr, and Radarr SQLite snapshots and settings; Jellyseerr and Transmission config on Synology; and Beelink Compose, env, updater, iSponsorBlockTV, and helper script files. It writes `beelink-config-<UTC timestamp>.tar.gz.gpg` under `/mnt/synology/jellyfin/config/beelink-backups`, checks SQLite snapshots, verifies the NAS copy by SHA-256, and sends an Uptime Kuma heartbeat.

| Job | Schedule | Destination or log |
| --- | --- | --- |
| Jellyfin config rsync mirror | 04:30 Beelink time | `/mnt/synology/jellyfin/config/jellyfin-local-backup`; excludes transcodes and rotated logs; mirror has no version history |
| Encrypted Beelink snapshot | 19:15 Beelink time | `/mnt/synology/jellyfin/config/beelink-backups`; log `/opt/stacks/admin/config-backup/backup.log` |
| S3 snapshot check | Hourly at minute 25 | `/opt/stacks/admin/config-backup/s3-check.log`; compares local snapshots with Hyper Backup catalog |
| Media image update | WUD scan 09:45; updater at 10:00 Asia/Jerusalem | See [media update notes](../beelink/admin/MEDIA-AUTO-UPDATE.md) |

Home Assistant runs on Synology, not Beelink. Beelink runs the media stack, admin/support containers, and custom Python services `media-health` and `torrentleech-rss`.

Run one encrypted snapshot on demand as the backup-job owner with `/usr/bin/timeout 20m /usr/bin/python3 /opt/stacks/admin/config-backup/backup-configs.py`. To check the S3 copy, add `--check-s3`. After the NAS snapshot is present, use **Back Up Now** on the DSM **Beelink config to S3** task for an immediate offsite upload.

## Restore

### Home Assistant or a Synology bind-mounted stack

1. In DSM, open **Hyper Backup**, select **Backup hass config**, and choose **Restore** or **Backup Explorer**. Select a version from `hass-config-backup-benita / hass-config`.
2. Restore only the needed paths under `Media/SmartHome/Config`. For HA, restore both `HASS` and `mariadb`, plus any required MQTT, Zigbee2MQTT, Matter, Tasmoadmin, or SSH-key folders. Do not replace all of `Media` for a single-service recovery.
3. Stop the affected container first. Restore ownership and permissions, start the stack using its tracked Compose definition and private runtime settings, then confirm HA reconnects to MariaDB and recorder history is available.

### Beelink config snapshot

1. In DSM, open **Hyper Backup -> Beelink config to S3 -> Backup Explorer** and retrieve `jellyfin/config/beelink-backups/beelink-config-<timestamp>.tar.gz.gpg`. The direct NAS copy is `/volume1/jellyfin/config/beelink-backups`.
2. Retrieve the GPG key below. Decrypt in a private staging directory and inspect before extraction:

   ```sh
   umask 077
   gpg --output config.tar.gz --decrypt beelink-config-<timestamp>.tar.gz.gpg
   tar -tzf config.tar.gz
   ```

3. Extract to staging. Check each SQLite database with `PRAGMA quick_check;`. Stop the affected service, save its current files, restore the needed paths and ownership, then start it.
4. Recreate services from tracked Compose files and private env values. Secrets are not in this guide.

The Jellyfin mirror can be copied from `/volume1/jellyfin/config/jellyfin-local-backup` to `/opt/media/jellyfin/config` while Jellyfin is stopped. Use Hyper Backup for version history; rsync mirror alone is not versioned.

## Keys and secrets

- **GPG key for Beelink snapshots:** `~/.config/beelink-config-backup/recovery.key` on Beelink; copies are also on the Mac used to set up the job and in the user's offline recovery credentials. Required to decrypt `.tar.gz.gpg` archives.
- **Hyper Backup key:** none for these two tasks; DSM shows client-side encryption off. Transfer encryption is on.
- **S3 credentials and application secrets:** not stored here or in Git. Retrieve from private credential storage or the existing DSM task configuration.

## Docker configuration

The repository root contains Synology Compose files; `beelink/` contains Beelink files. Keep real env files and credentials in private host storage. The Beelink repository checkout is `/opt/stacks/docker-config`; live Compose files are under `/opt/stacks/{admin,media}`. Use the documented deployment process and update tracked definitions rather than making an undocumented live-only change.

Before adding a persistent path or named volume, add it here and confirm its physical source is covered by a Hyper Backup task. Check current status in DSM Hyper Backup and Beelink's `backup.log` / `s3-check.log` plus the Uptime Kuma **Beelink Config Backup to Synology** monitor.

## Service inventory and recovery order

The inventory separates services observed running on 2026-11-24 from tracked definitions that were not running. Restore Docker, storage, network, and private env values first. Restore databases before their applications. Never copy secrets into this guide.

### Synology

| Services | Dependencies and data | Restore order |
| --- | --- | --- |
| MariaDB (hass-mariadb) | Config/mariadb and Config/mariadb-conf/conf.d; private DB password | Restore both paths while stopped; start and verify MariaDB first. |
| Mosquitto (hass-mosquitto) | Config/mqtt/{config,data,log}; broker config/credentials | Restore paths and start before HA or Zigbee clients that use MQTT. |
| Home Assistant (hass-homeassistant) | MariaDB, Mosquitto; Config/HASS and Config/HomeAssistant/.sshkeys; private env/tokens | Restore data/secrets; start MariaDB and Mosquitto, then HA. Check recorder, integrations, and automations. |
| Zigbee2MQTT, both instances | Config/zigbee2mqtt/{main-floor-data,upper-floor-data}; MQTT and coordinator hardware | Restore each data path; verify coordinator and MQTT settings; then start and check devices. |
| Matter Server | Config/matter-server/data; Docker and network | Restore data, start, then confirm HA reconnects. |
| Tasmoadmin | Config/tasmoadmin/data; network access to devices | Restore data and start; verify devices and credentials. |
| Cloudflare tunnel | Config/cloudflared/hass; internet and private tunnel token | Restore config/token; start after local HA is reachable and verify external access. Replica was defined but not confirmed running. |
| Gen AI server | Custom hass-generative-ai image; private HA/AWS settings; no bind mount shown | Rebuild/load image and restore env; start after HA and network. |
| Code Server | Config/code-server and workspace mounts; Docker socket; private passwords | Restore config and workspace paths; start and verify Docker/workspace access. |
| Portainer | Config/portainer, covered by Media task; Compose definition not tracked | Restore data and start; capture current deployment definition before host rebuild. |
| Prune | Docker socket; no persistent data | Recreate from tracked admin Compose after Docker is ready. |
| Telegram relay | Inline Python command; private token; no tracked source or definition | Recover source/definition from protected copy, then deploy with secret storage. Recovery procedure is incomplete. |

Tracked Synology media and Traccar definitions were not active in the DSM check. If deployed, restore their config from Media and private env first:

| Tracked but not running | Dependencies and restore order |
| --- | --- |
| Synology media: Sonarr, Radarr, Bazarr, Jackett, Prowlarr, Jellyseerr, Minecraft | Media/download paths and per-service Config folders. Restore paths/env; start download/indexer services, then Sonarr/Radarr/Bazarr/Jellyseerr and Minecraft as needed. Jellyfin and Transmission are commented out. |
| Traccar DB and app | Config/traccar-db and Config/traccar/{logs,conf/traccar.xml}; private DB password. Restore/start DB and verify it, then start app. |

### Beelink

Active stacks: /opt/stacks/admin/compose.yaml and /opt/stacks/media/compose.yaml. Mount Synology NFS 172.16.0.9:/volume1/jellyfin at /mnt/synology/jellyfin before starting dependent services.

| Services | Dependencies and data | Restore order |
| --- | --- | --- |
| NFS media storage | Synology, network, /mnt/synology/jellyfin; media, downloads, and some app configs | Restore Synology/network first; mount and verify paths/permissions before media services. |
| Jellyfin | NFS libraries; /opt/media/jellyfin/{config,cache}; GPU and private IDs/env | Restore config/cache; start after NFS and verify libraries/transcoding. |
| Transmission | NFS config/transmission, downloads and watch paths | Restore config; start after NFS and verify paths/torrents. |
| Sonarr and Radarr | Local /opt/media/{sonarr,radarr}/config; NFS downloads/libraries; Transmission if used | Restore config; start after NFS and download client; verify library/client paths. |
| Bazarr and Prowlarr | NFS configs/media; Sonarr/Radarr integration | Restore config and start after NFS and related services; verify integrations. |
| Jellyseerr | NFS config/jellyseerr; Jellyfin, Sonarr/Radarr | Restore config; start after NFS and dependencies; verify URLs/API keys. |
| iSponsorBlockTV and web UI | /opt/stacks/media/isponsorblocktv; private web UI env | Restore data/env; start core service before web UI (Compose dependency). |
| torrentleech-rss and media-health | Tracked /opt/stacks/media scripts; private RSS env; media-health needs NFS and Synology Portainer API | Restore scripts/env; start after NFS; media-health also needs Portainer and its private API key. |
| Uptime Kuma | /opt/admin/uptime-kuma; Docker socket and network | Restore data; start after Docker/network; verify monitors after services. |
| WUD | /opt/admin/wud; Docker socket, Compose paths, private auth/notification values | Restore data/config/secrets; start after Docker/stacks; verify schedules before updates. |
| Homepage | /opt/admin/homepage; Docker socket; admin/media networks | Restore config; start after linked services and check links. |
| Code Server | /opt/admin/code-server; /opt/stacks, /opt/admin, /opt/media and NFS mounts; Docker socket/passwords | Restore config and paths; start after storage and Docker. |
| Portainer Agent | Docker socket, /var/lib/docker/volumes, admin network | Recreate after Docker; confirm Portainer can reach it. |
| OpenSpeedTest | No persistent data; admin network | Recreate from admin Compose after Docker/network. |
| Docker Engine and networks | Host OS, Compose files, private env files | Restore Docker first, then env and mounts; bring up admin before media; only start NFS-dependent containers after mount checks. |

## Synology outage and full NAS recovery

A failed Synology does not mean the Synology data has no offsite copy. The DSM task **Backup hass config** selects the whole Media shared folder with filters off and backs it up to the Amazon S3 bucket hass-config-backup-benita under hass-config. This includes the SmartHome/Config tree, including Home Assistant and MariaDB files. The task also backs up DSM system configuration. Client-side encryption is off, so no Hyper Backup decryption key is required. S3 credentials are still required.

If DSM or the NAS is unavailable:

1. Beelink containers that use the Synology NFS mount at /mnt/synology/jellyfin will lose media, downloads, and some app configuration. Stop or leave them stopped until the share is available. Jellyfin and media managers may report missing paths. Home Assistant is hosted on Synology and will be unavailable.
2. Repair the NAS or prepare a replacement Synology. Install DSM and Hyper Backup, then connect to the existing S3 repository using the credentials in private credential storage.
3. Restore DSM system configuration and the Media share from hass-config-backup-benita / hass-config. Restore the Docker Compose checkout and SmartHome/Config data, including MariaDB, MQTT, HA, and each other required service folder. The MariaDB backup is a live data directory, not an SQL dump. Restore it while MariaDB is stopped.
4. Restore or verify private environment files and secrets from 1Password. Recreate Docker and Container Manager if needed. Start MariaDB and Mosquitto first, then Home Assistant and its dependent services. Start the Cloudflare tunnel after local HA works.
5. Recreate the NFS share and mount 172.16.0.9:/volume1/jellyfin at /mnt/synology/jellyfin on Beelink. Check paths and permissions, then start Beelink media services in the order in the service table.
6. If the Synology copy of a Beelink snapshot is also unavailable, retrieve the encrypted archive from the Beelink config to S3 task under beelink-config. Decrypt it with the Beelink GPG recovery key before restoring host config.

The Beelink GPG key is needed only for the encrypted Beelink snapshots. Hyper Backup client-side decryption keys are not needed for either verified task. Protect the S3 access credentials and Beelink GPG recovery key in 1Password, and keep an independent offline recovery copy of the GPG key.
