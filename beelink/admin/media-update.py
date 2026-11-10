#!/usr/bin/env python3
import base64
import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ACTIVE = Path("/opt/stacks/media/compose.yaml")
TRACKED = Path("/opt/stacks/docker-config/beelink/media/docker-compose.yaml")
ADMIN_ACTIVE = Path("/opt/stacks/admin/compose.yaml")
ADMIN_TRACKED = Path("/opt/stacks/docker-config/beelink/admin/docker-compose.yaml")
STATE_DIR = Path("/opt/stacks/admin/media-update-state")
LOCK_FILE = Path("/opt/stacks/admin/.media-update.lock")
API = "http://127.0.0.1:3000"
ALLOWED = {
    "isponsorblocktv", "isponsorblocktv-webui", "jellyfin", "transmission",
    "radarr", "sonarr", "bazarr", "prowlarr", "jellyseerr",
    "torrentleech-rss", "media-health",
}

def log(message):
    print(message, flush=True)

def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()

def service_block(text, service):
    matches = list(re.finditer(r"(?m)^  ([A-Za-z0-9_-]+):\n", text))
    for i, match in enumerate(matches):
        if match.group(1) == service:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return match.start(), end, text[match.start():end]
    raise RuntimeError("Compose service missing: " + service)

def image_ref(path, service):
    _, _, block = service_block(path.read_text(), service)
    image = re.search(r"(?m)^    image:\s*(.+)$", block)
    if not image:
        raise RuntimeError("Compose image missing: " + service)
    return image.group(1).strip()

def set_image_ref(path, service, ref):
    text = path.read_text()
    start, end, block = service_block(text, service)
    updated, count = re.subn(r"(?m)^    image:.*$", "    image: " + ref, block, count=1)
    if count != 1:
        raise RuntimeError("Could not update image reference for " + service + " in " + str(path))
    path.write_text(text[:start] + updated + text[end:])

def api_request(path, method="GET", auth=None):
    req = urllib.request.Request(API + path, data=b"" if method == "POST" else None, method=method)
    req.add_header("Authorization", "Basic " + auth)
    try:
        with urllib.request.urlopen(req, timeout=900) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError("WUD API returned HTTP " + str(exc.code) + " for " + method + " " + path) from None
    except urllib.error.URLError as exc:
        raise RuntimeError("WUD API unavailable: " + str(exc.reason)) from None

def credentials():
    raw = run(["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", "admin-wud"])
    values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    user, password = values.get("WUD_AUTH_ADMIN_USER"), values.get("WUD_AUTH_ADMIN_PASSWORD")
    if not user or not password:
        raise RuntimeError("WUD API credentials are missing from admin-wud")
    return base64.b64encode((user + ":" + password).encode()).decode()

def inspect_container(name):
    return run(["docker", "inspect", "--format", "{{.Id}} {{.Image}}", name]).split()

def write_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = STATE_DIR / ("rollback-" + state["run_id"] + ".json")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n")
    os.chmod(temp, 0o600)
    temp.replace(path)
    return path

def sync_admin_image():
    ref = image_ref(ADMIN_ACTIVE, "wud")
    if ref != image_ref(ADMIN_TRACKED, "wud"):
        set_image_ref(ADMIN_TRACKED, "wud", ref)
        log("Synchronized WUD image reference to " + ref)

def update():
    auth = credentials()
    containers = api_request("/api/containers", auth=auth)
    candidates = []
    for container in containers:
        if not container.get("name", "").startswith("media-") or not container.get("updateAvailable"):
            continue
        service = (container.get("labels") or {}).get("com.docker.compose.service")
        if service in ALLOWED:
            candidates.append((container, service))
    if not candidates:
        log("No eligible media image updates are available.")
        return

    run_id = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y%m%dT%H%M%S")
    state = {"run_id": run_id, "services": {}}
    state_path = write_state(state)
    for container, service in candidates:
        name, cid = container["name"], container["id"]
        triggers = api_request("/api/containers/" + cid + "/triggers", auth=auth)
        if not any(item.get("id") == "dockercompose.media" for item in triggers):
            raise RuntimeError("WUD media Compose trigger is not available for " + name)

        old_ref = image_ref(ACTIVE, service)
        old_container_id, old_image_id = inspect_container(name)
        state["services"][service] = {
            "container": name,
            "image_ref": old_ref,
            "image_id": old_image_id,
        }
        state_path = write_state(state)

        api_request("/api/containers/" + cid + "/triggers/dockercompose/media", method="POST", auth=auth)
        deadline = time.monotonic() + 600
        new_container_id, new_image_id = old_container_id, old_image_id
        while time.monotonic() < deadline:
            try:
                new_container_id, new_image_id = inspect_container(name)
            except subprocess.CalledProcessError:
                time.sleep(5)
                continue
            new_ref = image_ref(ACTIVE, service)
            if new_container_id != old_container_id or new_image_id != old_image_id or new_ref != old_ref:
                break
            time.sleep(5)
        else:
            raise RuntimeError("Timed out waiting for updated container " + name)

        new_ref = image_ref(ACTIVE, service)
        if new_ref != image_ref(TRACKED, service):
            set_image_ref(TRACKED, service, new_ref)
        kind = container.get("updateKind", {}).get("kind", "image")
        remote = container.get("updateKind", {}).get("remoteValue", "new version")
        log("Updated " + name + " (" + kind + ": " + str(remote) + "); rollback state: " + str(state_path))

def rollback():
    files = sorted(glob.glob(str(STATE_DIR / "rollback-*.json")))
    if not files:
        raise RuntimeError("No saved media update rollback state exists")
    path = Path(files[-1])
    state = json.loads(path.read_text())
    services = state.get("services", {})
    if not services:
        raise RuntimeError("Rollback state contains no updated services")

    for service, old in services.items():
        run(["docker", "image", "tag", old["image_id"], old["image_ref"]])
        set_image_ref(ACTIVE, service, old["image_ref"])
        set_image_ref(TRACKED, service, old["image_ref"])
    run(["docker", "compose", "-f", str(ACTIVE), "up", "-d", "--no-deps", *services.keys()])
    log("Rolled back " + ", ".join(services) + " using " + str(path))

def scheduled_check():
    now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    if not (now.hour == 10 and 0 <= now.minute < 15):
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK_FILE.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = STATE_DIR / "last-scheduled-date"
        today = now.date().isoformat()
        if marker.exists() and marker.read_text().strip() == today:
            return
        marker.write_text(today + "\n")
        log("Scheduled media update run started at " + now.isoformat())
        sync_admin_image()
        update()

if __name__ == "__main__":
    if sys.argv[1:] == ["--rollback"]:
        rollback()
    elif sys.argv[1:] == ["--schedule-check"]:
        scheduled_check()
    elif not sys.argv[1:]:
        update()
    else:
        raise SystemExit("Usage: media-update.py [--schedule-check|--rollback]")
