"""Lazy dictionary-compatible records within one control database transaction."""
import copy
import json
from collections.abc import MutableMapping


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def plain(value):
    return {k: plain(v) for k, v in value.items()} if isinstance(value, MutableMapping) else copy.deepcopy(value)


class Collection(MutableMapping):
    def __init__(self, root, name):
        self.root, self.name = root, name
        self.cache, self.original, self.deleted = {}, {}, set()

    def __getitem__(self, key):
        if key in self.deleted:
            raise KeyError(key)
        if key not in self.cache:
            row = self.root.db.execute("SELECT payload FROM records WHERE collection=? AND key=?", (self.name, key)).fetchone()
            if row is None:
                raise KeyError(key)
            self.original[key] = row[0]
            self.cache[key] = json.loads(row[0])
        return self.cache[key]

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise ValueError("Control record keys must be strings")
        if key not in self.original:
            row = self.root.db.execute("SELECT payload FROM records WHERE collection=? AND key=?", (self.name, key)).fetchone()
            self.original[key] = row[0] if row else None
        self.deleted.discard(key)
        self.cache[key] = value

    def __delitem__(self, key):
        self[key]
        self.deleted.add(key)
        self.cache.pop(key, None)

    def __iter__(self):
        keys = [row[0] for row in self.root.db.execute("SELECT key FROM records WHERE collection=? ORDER BY ordinal", (self.name,))]
        known = set(keys)
        keys.extend(k for k in self.cache if self.original.get(k) is None and k not in known)
        return iter([k for k in keys if k not in self.deleted])

    def __len__(self):
        count = self.root.db.execute("SELECT count(*) FROM records WHERE collection=?", (self.name,)).fetchone()[0]
        return count + sum(v is None and k not in self.deleted for k, v in self.original.items()) - sum(
            self.original.get(k) is not None for k in self.deleted)

    def flush(self):
        for key in self.deleted:
            self.root.db.execute("DELETE FROM records WHERE collection=? AND key=?", (self.name, key))
            if self.original.get(key) is not None:
                self.root.changed = True
                self.root.changed_roots.add(self.name)
            self.original.pop(key, None)
        self.deleted.clear()
        for key, value in self.cache.items():
            raw = encode(value)
            if raw == self.original.get(key):
                continue
            item = value if isinstance(value, dict) else {}
            fields = [item.get(k) if isinstance(item.get(k), str) else None for k in
                      ("status", "created_at", "campaign_id", "schedule_id", "idempotency_key")]
            fields[1] = fields[1] or ""
            status = "cancelling" if item.get("status") == "running" and item.get("cancel_requested") else item.get("status")
            self.root.db.execute("""INSERT INTO records(collection,key,payload,status,created_at,campaign_id,schedule_id,idempotency_key,state)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(collection,key) DO UPDATE SET
                payload=excluded.payload,status=excluded.status,created_at=excluded.created_at,campaign_id=excluded.campaign_id,
                schedule_id=excluded.schedule_id,idempotency_key=excluded.idempotency_key,state=excluded.state""",
                (self.name, key, raw, *fields, status if isinstance(status, str) else None))
            self.original[key] = raw
            self.root.changed = True
            self.root.changed_roots.add(self.name)


class State(MutableMapping):
    def __init__(self, db):
        self.db, self.changed = db, False
        self.changed_roots = set()
        self.roots = {name: (kind, raw) for name, kind, raw in db.execute("SELECT name,kind,value FROM roots")}
        self.cache = {}

    def __getitem__(self, key):
        if key not in self.cache:
            kind, raw = self.roots[key]
            self.cache[key] = Collection(self, key) if kind == "collection" else json.loads(raw)
        return self.cache[key]

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise ValueError("Control collection names must be strings")
        if key in self.roots and plain(self[key]) == value:
            return
        if key in self.roots:
            self.__delitem__(key)
        kind = "collection" if isinstance(value, dict) else "value"
        raw = None if kind == "collection" else encode(value)
        self.db.execute("INSERT INTO roots(name,kind,value) VALUES(?,?,?)", (key, kind, raw))
        self.roots[key] = (kind, raw)
        if kind == "collection":
            collection = Collection(self, key)
            for name, item in value.items():
                collection[name] = item
            self.cache[key] = collection
        else:
            self.cache[key] = value
        self.changed = True
        self.changed_roots.add(key)

    def __delitem__(self, key):
        if key not in self.roots:
            raise KeyError(key)
        self.db.execute("DELETE FROM records WHERE collection=?", (key,))
        self.db.execute("DELETE FROM roots WHERE name=?", (key,))
        self.roots.pop(key)
        self.cache.pop(key, None)
        self.changed = True
        self.changed_roots.add(key)

    def __iter__(self):
        return iter(self.roots)

    def __len__(self):
        return len(self.roots)

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def flush(self):
        for key, value in self.cache.items():
            if isinstance(value, Collection):
                value.flush()
            else:
                raw = encode(value)
                if raw != self.roots[key][1]:
                    self.db.execute("UPDATE roots SET value=? WHERE name=?", (raw, key))
                    self.roots[key] = ("value", raw)
                    self.changed = True
                    self.changed_roots.add(key)

    def jobs(self, **query):
        self.flush()
        keys, total = job_keys(self.db, **query)
        rows = self.setdefault("jobs", {})
        return [rows[key] for key in keys], total


def job_keys(db, *, statuses=None, state=None, campaign_id=None, run_id=None, schedule_id=None,
             idempotency_key=None, limit=100, offset=0, ascending=False, before=None):
    clauses, args = ["collection='jobs'"], []
    if statuses is not None:
        if not statuses:
            return [], 0
        clauses.append("status IN (" + ",".join("?" for _ in statuses) + ")")
        args.extend(sorted(statuses))
    for field, value in (("state", state), ("campaign_id", campaign_id), ("key", run_id),
                         ("schedule_id", schedule_id), ("idempotency_key", idempotency_key)):
        if value is not None:
            clauses.append(field + "=?")
            args.append(value)
    where = " AND ".join(clauses)
    total = db.execute("SELECT count(*) FROM records WHERE " + where, args).fetchone()[0]
    if before is not None:
        if ascending or offset:
            raise ValueError("Keyset reads require descending order and zero offset")
        where += " AND (created_at,key) < (?,?)"
        args.extend(before)
    direction = "ASC" if ascending else "DESC"
    keys = [row[0] for row in db.execute("SELECT key FROM records WHERE " + where +
            f" ORDER BY created_at {direction},key {direction} LIMIT ? OFFSET ?", (*args, limit, offset))]
    return keys, total
