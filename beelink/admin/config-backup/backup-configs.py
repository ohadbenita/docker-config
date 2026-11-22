#!/usr/bin/env python3
import fcntl
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tarfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import urlopen


SETTINGS = Path.home() / '.config/beelink-config-backup'
NAS_CONFIG = Path('/mnt/synology/jellyfin/config')
DESTINATION = NAS_CONFIG / 'beelink-backups'
DATABASES = (
    Path('/opt/admin/uptime-kuma/kuma.db'),
    Path('/opt/media/sonarr/config/sonarr.db'),
    Path('/opt/media/radarr/config/radarr.db'),
    NAS_CONFIG / 'jellyseerr/db/db.sqlite3',
)
CONFIG_PATHS = (
    '/opt/admin/uptime-kuma/db-config.json',
    '/opt/admin/uptime-kuma/docker-tls',
    '/opt/admin/uptime-kuma/upload',
    '/opt/media/sonarr/config/config.xml',
    '/opt/media/radarr/config/config.xml',
    '/opt/stacks/admin/compose.yaml',
    '/opt/stacks/admin/.env',
    '/opt/stacks/admin/media-update.py',
    '/opt/stacks/media/compose.yaml',
    '/opt/stacks/media/.env',
    '/opt/stacks/media/isponsorblocktv',
    '/opt/stacks/media/media-health/app.py',
    '/opt/stacks/media/torrentleech-rss/app.py',
    NAS_CONFIG / 'jellyseerr/settings.json',
    NAS_CONFIG / 'transmission/settings.json',
    NAS_CONFIG / 'transmission/bandwidth-groups.json',
    NAS_CONFIG / 'transmission/crontabs',
    NAS_CONFIG / 'transmission/blocklist-update.sh',
)


def snapshot_database(source, target):
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as live:
        with closing(sqlite3.connect(target)) as snapshot:
            live.backup(snapshot)
            if snapshot.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError(f'SQLite integrity check failed for {source.name}')


def checksum(path):
    with path.open('rb') as payload:
        return hashlib.file_digest(payload, 'sha256').digest()


def backup():
    subprocess.run(['findmnt', '-n', '-t', 'nfs,nfs4', '-T', str(NAS_CONFIG)],
                   check=True, stdout=subprocess.DEVNULL)
    try:
        DESTINATION.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        DESTINATION.chmod(0o700)
    if DESTINATION.is_symlink() or DESTINATION.stat().st_mode & 0o077:
        raise RuntimeError('Backup destination must be a private directory')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive_name = f'beelink-config-{stamp}.tar.gz.gpg'
    with TemporaryDirectory(prefix='beelink-config-') as scratch:
        workspace = Path(scratch)
        archive = workspace / 'config.tar.gz'
        with tarfile.open(archive, 'w:gz', compresslevel=3) as bundle:
            for config in CONFIG_PATHS:
                source = Path(config)
                bundle.add(source, arcname=str(source).lstrip('/'))
            for source in DATABASES:
                snapshot = workspace / source.name
                snapshot_database(source, snapshot)
                bundle.add(snapshot, arcname=str(source).lstrip('/'))

        encrypted = workspace / archive_name
        subprocess.run(['gpg', '--batch', '--no-symkey-cache', '--pinentry-mode', 'loopback',
                        '--passphrase-file', str(SETTINGS / 'recovery.key'), '--cipher-algo',
                        'AES256', '--compress-algo', 'none', '--output', str(encrypted),
                        '--symmetric', str(archive)], check=True)
        temporary = DESTINATION / f'.{archive_name}.partial'
        try:
            with encrypted.open('rb') as source, temporary.open('xb') as target:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            if checksum(temporary) != checksum(encrypted):
                raise RuntimeError('Synology copy checksum mismatch')
            temporary.rename(DESTINATION / archive_name)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    print(f'Verified Synology backup: {archive_name}', flush=True)
    return archive_name


def heartbeat(status, message):
    target = SETTINGS / 'push-url'
    if not target.exists():
        return
    url = urlsplit(target.read_text().strip())
    query = urlencode({'status': status, 'msg': message})
    with urlopen(urlunsplit(url._replace(query=query, fragment='')), timeout=10) as response:
        if response.status != 200:
            raise RuntimeError('Kuma heartbeat failed')


if __name__ == '__main__':
    os.umask(0o077)
    with (SETTINGS / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            name = backup()
        except Exception:
            try:
                heartbeat('down', 'Beelink config backup failed')
            except Exception:
                print('Could not reach Uptime Kuma', flush=True)
            raise
        heartbeat('up', f'Synology copy verified: {name}')
