#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo


SETTINGS = Path.home() / '.config/beelink-config-backup'
NAS_CONFIG = Path('/mnt/synology/jellyfin/config')
DESTINATION = NAS_CONFIG / 'beelink-backups'
S3_COMPLETION_PREFIX = 'beelink-config.hbk/Config/@Share/@AppConfig/complete_list.db.'
S3_CATALOG_PREFIX = 'beelink-config.hbk/Config/@Share/jellyfin/'
S3_MAX_AGE = timedelta(hours=28)
SNAPSHOT_NAME = re.compile(r'beelink-config-\d{8}T\d{6}Z\.tar\.gz\.gpg')
BACKUP_TIMEZONE = ZoneInfo('Asia/Jerusalem')
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


def heartbeat(status, message, target_name='push-url'):
    target = SETTINGS / target_name
    if not target.exists():
        return
    url = urlsplit(target.read_text().strip())
    query = urlencode({'status': status, 'msg': message})
    with urlopen(urlunsplit(url._replace(query=query, fragment='')), timeout=10) as response:
        if response.status != 200:
            raise RuntimeError('Kuma heartbeat failed')


def latest_s3_completion(payload):
    listing = ET.fromstring(payload)
    if listing.findtext('{*}IsTruncated') != 'false':
        raise RuntimeError('Incomplete S3 completion listing')
    versions = []
    for entry in listing.findall('{*}Contents'):
        key = entry.findtext('{*}Key', default='')
        version = key.removeprefix(S3_COMPLETION_PREFIX)
        if key.startswith(S3_COMPLETION_PREFIX) and version.isdecimal():
            modified = datetime.fromisoformat(entry.findtext('{*}LastModified', default=''))
            if modified.tzinfo is None:
                raise ValueError('S3 completion time has no timezone')
            versions.append((modified, version))
    if not versions:
        raise RuntimeError('No completed Hyper Backup version found in S3')
    return max(versions)


def request_s3(key='', query=None, output=None):
    endpoint = (SETTINGS / 's3-endpoint').read_text().strip()
    url = endpoint + quote(key, safe='/')
    if query:
        url += '?' + urlencode(query)
    command = ['curl', '--disable', '--config', str(SETTINGS / 's3-list.curl'),
               '--fail', '--silent', '--show-error', '--connect-timeout', '10',
               '--max-time', '180' if output else '20', '--url', url]
    if output:
        command.extend(['--retry', '1', '--output', str(output)])
    return subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout


def catalog_entries(path):
    # Hyper Backup's internal catalog format can change. A schema mismatch fails the check.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as catalog:
        catalog.execute('PRAGMA trusted_schema=OFF')
        rows = catalog.execute("""
            SELECT entry.file_name, entry.size, entry.mtime_sec, entry.mtime_nsec
            FROM version_list AS entry
            JOIN version_list AS parent ON parent.name_id_v2 = entry.pname_id_v2
            JOIN version_list AS grandparent ON grandparent.name_id_v2 = parent.pname_id_v2
            WHERE parent.file_name = 'beelink-backups' AND grandparent.file_name = 'config'
              AND (entry.mode & 61440) = 32768 AND entry.off_virtual_file > 0
              AND entry.status IN ('C', 'M', 'N', 'U')
        """)
        return {name: [size, sec * 1_000_000_000 + nsec] for name, size, sec, nsec in rows
                if SNAPSHOT_NAME.fullmatch(name)}


def s3_entries(version, completed):
    cache = SETTINGS / 's3-catalog.json'
    identity = [version, completed.isoformat()]
    if cache.exists():
        saved = json.loads(cache.read_text())
        if saved['identity'] == identity:
            return saved['entries']

    with TemporaryDirectory(dir=SETTINGS) as scratch:
        catalog = Path(scratch) / 'catalog.db'
        request_s3(f'{S3_CATALOG_PREFIX}{version}.db.{version}', output=catalog)
        entries = catalog_entries(catalog)
        pending = Path(scratch) / 'catalog.json'
        pending.write_text(json.dumps({'identity': identity, 'entries': entries}))
        pending.replace(cache)
    return entries


def snapshot_state(snapshots, entries, version, now):
    if not snapshots:
        return 'down', 'No published Synology snapshot found'

    filename, stat = max(snapshots.items())
    if entries.get(filename) == stat:
        return 'up', f'{filename} verified in S3 version {version}'
    if filename in entries:
        return 'down', f'{filename} metadata differs in S3 version {version}'

    created = datetime.fromtimestamp(stat[1] // 1_000_000_000, BACKUP_TIMEZONE)
    next_run = datetime.combine(created.date(), time(5, 30), tzinfo=BACKUP_TIMEZONE)
    if created >= next_run:
        next_run += timedelta(days=1)
    deadline = next_run + timedelta(minutes=90)
    if now < deadline and any(entries.get(name) == metadata for name, metadata in snapshots.items()):
        return 'up', f'{filename} pending scheduled S3 upload by {deadline:%Y-%m-%d %H:%M %Z}'
    return 'down', f'{filename} is missing from S3 version {version}'


def check_s3():
    try:
        listing = request_s3(query={'list-type': '2', 'prefix': S3_COMPLETION_PREFIX})
        completed, version = latest_s3_completion(listing)
        now = datetime.now(timezone.utc)
        if not timedelta(0) <= now - completed <= S3_MAX_AGE:
            raise RuntimeError(f'S3 version {version} is outside the 28-hour freshness window')
        snapshots = {}
        for path in DESTINATION.glob('beelink-config-*.tar.gz.gpg'):
            if SNAPSHOT_NAME.fullmatch(path.name) and path.is_file():
                stat = path.stat()
                snapshots[path.name] = [stat.st_size, stat.st_mtime_ns]
        status, message = snapshot_state(snapshots, s3_entries(version, completed), version, now)
    except RuntimeError as error:
        status, message = 'down', str(error)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, sqlite3.Error, ET.ParseError):
        status, message = 'down', 'Could not read the Synology snapshot or S3 Hyper Backup catalog'
    heartbeat(status, message, 's3-push-url')
    print(message, flush=True)
    return status == 'up'


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-s3', action='store_true')
    if parser.parse_args().check_s3:
        raise SystemExit(0 if check_s3() else 1)
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
