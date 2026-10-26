"""Small transactional store for dashboard jobs and schedules.

Campaigns and findings continue to use api.json_storage: no migration or second
copy of assessment data. This file stores only new community control state.
"""
import copy
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from api import json_storage as data


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", value):
        raise ValueError("Invalid identifier")
    return value


class Store:
    def __init__(self, root=None):
        self.root = Path(root or data.DATA_DIR / "community")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "state.json"

    def read(self):
        result = data._read_json(self.path)
        return result if isinstance(result, dict) else {"jobs": {}, "schedules": {}}

    def update(self, action):
        with data._file_lock(self.path):
            state = self.read()
            result = action(state)
            data._write_json(self.path, state)
            os.chmod(self.path, 0o600)
            return copy.deepcopy(result)

    def get(self, collection, key):
        return self.read().get(collection, {}).get(identifier(key))

    def items(self, collection):
        return list(self.read().get(collection, {}).values())

    def save(self, collection, item):
        identifier(item["id"])
        def change(state):
            state.setdefault(collection, {})[item["id"]] = item
            return item
        return self.update(change)

    def job_path(self, job_id):
        return self.root / "logs" / (identifier(job_id) + ".log")
