# Beelink

Beelink has its own Compose files under `beelink/`. Keep them separate from the existing Synology stacks in the repository root. The two machines have different image versions, mount paths, ports, and runtime data.

The files in this directory describe the active Beelink stacks:

- `beelink/admin/docker-compose.yaml`
- `beelink/media/docker-compose.yaml`

Keep Beelink runtime values in `/opt/stacks/admin/.env` and `/opt/stacks/media/.env`. The matching `.env.example` files list the required variable names. Never commit the real `.env` files.

## Deploy from the shared repository

After the Beelink files are available on the repository's default branch, create a checkout on Beelink:

```sh
git clone https://github.com/ohadbenita/docker-config.git /opt/docker-config
```

Pull changes before each deployment, then run the stack from the repository while keeping the real env files at their current host paths:

```sh
git -C /opt/docker-config pull --ff-only
docker compose -f /opt/docker-config/beelink/admin/docker-compose.yaml --env-file /opt/stacks/admin/.env up -d
docker compose -f /opt/docker-config/beelink/media/docker-compose.yaml --env-file /opt/stacks/media/.env up -d
```

The Compose files use absolute Beelink paths. Keep application data under the existing host directories; do not move it when updating the repository.
