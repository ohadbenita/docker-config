# Docker configuration

This repository stores Docker Compose files for two hosts:

- The root stack folders are for the Synology host.
- The `beelink/` folder has separate Compose files for the Beelink host.

The hosts have different image versions, paths, ports, and runtime data. Keep each host's configuration in its own files.

## Stacks

- **Admin (Synology):** code-server and prune.
- **Admin (Beelink):** Portainer Agent, code-server, WUD, Uptime Kuma, Homepage, and OpenSpeedTest.
- **Home Assistant (Synology):** Home Assistant, MariaDB, Mosquitto, Tasmoadmin, Zigbee2MQTT, Matter Server, and the GenAI server.
- **Media (Synology):** Sonarr, Radarr, Bazarr, Jackett, Prowlarr, Jellyseerr, and Minecraft.
- **Media (Beelink):** Jellyfin, Transmission, Radarr, Sonarr, Bazarr, Prowlarr, Jellyseerr, iSponsorBlockTV and its Web UI, torrentleech-rss, and media-health.
- **Network (Synology):** Cloudflare Tunnel and its replica.
- **Nextcloud (Synology):** the Nextcloud app and database.
- **Traccar (Synology):** the Traccar app and database.

The Beelink Compose files and environment examples are in [beelink/](./beelink/). Deployment steps are in [docs/beelink.md](./docs/beelink.md). See the host-specific guides for [admin](./docs/admin.md), [Home Assistant](./docs/hass.md), [media](./docs/media.md), [network](./docs/network.md), [Nextcloud](./docs/nextcloud.md), and [Traccar](./docs/traccar.md).

## Runtime values

Keep real environment files on their hosts. Do not commit them. Use the checked-in `.env.example` files to see which variables each Beelink stack needs.

Beelink's active environment files are:

- `/opt/stacks/admin/.env`
- `/opt/stacks/media/.env`

The iSponsorBlockTV Web UI has a separate credentials file at `/opt/stacks/media/isponsorblocktv/webui.env`.

## Image updates

WUD checks Beelink media images at 09:45 Asia/Jerusalem. The media-only updater runs at 10:00, after the scan. WUD can update itself. Media updates use a 60-second running grace period and support rollback of the last run. See [media update notes](./beelink/admin/MEDIA-AUTO-UPDATE.md) for monitoring and rollback steps.

## Validation

The [Docker config validation workflow](./.github/workflows/docker-config-validation.yml) runs `docker compose config --quiet` for every tracked Compose file on pull requests and pushes to `master`. It uses placeholder environment values and does not need host credentials.
