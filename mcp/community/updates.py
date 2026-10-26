"""Explicit read-only image-update check, with no automatic deployment."""
import datetime
import json
import os
import platform
import re
import urllib.request


def status(check=False):
    running = os.environ.get("DARKMOON_IMAGE_BUILT_AT")
    available = os.environ.get("DARKMOON_AVAILABLE_BUILD")
    result = {"running_build": running, "available_build": available,
              "update_available": available != running if running and available else None,
              "source": "operator-provided build stamp", "checked": False}
    if not check:
        return result
    image = os.environ.get("DARKMOON_IMAGE_NAME", "ascit/opencode-darkmoon")
    if not re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_.-]+", image):
        raise ValueError("Image name must be Docker Hub namespace/repository")
    with urllib.request.urlopen("https://hub.docker.com/v2/repositories/"+image+"/tags/latest", timeout=15) as response:
        body = response.read(1024*1024+1)
    if len(body) > 1024*1024:
        raise ValueError("Registry response exceeds 1 MiB")
    metadata = json.loads(body)
    arch = "arm64" if platform.machine().lower() in {"aarch64", "arm64"} else "amd64"
    selected = next((item for item in metadata.get("images", []) if item.get("architecture") == arch), {})
    digest, current_digest = selected.get("digest"), os.environ.get("DARKMOON_IMAGE_DIGEST")
    available = metadata.get("tag_last_pushed") or metadata.get("last_updated")
    newer = None
    if digest and current_digest:
        newer = digest != current_digest
    elif available and running:
        newer = datetime.datetime.fromisoformat(available.replace("Z", "+00:00")) > datetime.datetime.fromisoformat(running.replace("Z", "+00:00"))
    return {"running_build": running, "available_build": available, "running_digest": current_digest,
            "available_digest": digest, "image": image, "update_available": newer, "source": "Docker Hub latest tag metadata", "checked": True}
