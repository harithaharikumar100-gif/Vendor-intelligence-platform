"""Persistent JSON stores and rate limiters.

SQLite persists single-machine jobs/reports; Redis shares state and quotas across
replicas. In-memory implementations support isolated tests. Configured Redis
failure stops startup rather than silently switching to a different store.
"""

import json
import time
import threading
import uuid
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional

import config


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


# ─── Key-value store (analysis cache, job records, PDF index) ────────────────

class KVStore:
    def keys(self, prefix):
        raise NotImplementedError

    def get_json(self, key: str) -> Optional[dict]:
        raise NotImplementedError

    def set_json(self, key: str, value: dict, ttl_seconds: Optional[float] = None):
        raise NotImplementedError

    def delete(self, key: str):
        raise NotImplementedError

    def try_claim(self, key: str, value: dict, ttl_seconds: Optional[float] = None) -> bool:
        """Atomic "set only if absent". Returns True if THIS call created
        the key, False if it already existed (someone else's claim wins).
        Needed for in-flight job dedup: a plain get-then-set from two
        near-simultaneous requests would both see "not present" and both
        proceed under a naive check, even though get_json/set_json are each
        individually atomic - the SEQUENCE of the two isn't, across
        processes. A single process's threading.Lock happens to make that
        sequence atomic too (which is why the in-memory dedup logic worked
        even before this method existed), but that guarantee disappears the
        moment state moves to Redis and is shared across replicas - this
        method exists specifically to keep the guarantee real either way.
        """
        raise NotImplementedError


class InMemoryKVStore(KVStore):
    def renew_claim(self, key, value, ttl_seconds):
        with self._lock:
            entry = self._data.get(key)
            if not entry or json.loads(entry[0]) != value or (entry[1] and entry[1] <= time.time()):
                return False
            self._data[key] = (entry[0], time.time() + ttl_seconds)
            return True

    def release_claim(self, key, value):
        with self._lock:
            entry = self._data.get(key)
            if entry and json.loads(entry[0]) == value:
                del self._data[key]

    def keys(self, prefix):
        with self._lock:
            keys = [key for key in self._data if key.startswith(prefix)]
        return [key for key in keys if self.get_json(key) is not None]

    """Stores each value as its JSON-serialized string, deserializing fresh
    on every get_json - not a dict-of-references. Deliberately matches
    RedisKVStore's actual behavior (Redis always hands back a freshly
    deserialized object from a serialized string, never a shared
    reference), because callers rely on that: a background worker thread
    mutates its own job dict in place and re-saves it, while a concurrent
    GET request reads and serializes it for an HTTP response - if get_json
    handed back the SAME object the worker holds, that read could race a
    later in-place mutation (or a JSON encoder crash on "dictionary changed
    size during iteration"). Round-tripping through JSON costs a little
    CPU but makes that whole class of bug structurally impossible, the same
    way it already is for the Redis backend."""

    def __init__(self):
        self._data = {}  # key -> (json_string, expires_at_epoch_or_None)
        self._lock = threading.Lock()

    def get_json(self, key):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            raw, expires_at = entry
            if expires_at is not None and time.time() > expires_at:
                del self._data[key]
                return None
            return json.loads(raw)

    def set_json(self, key, value, ttl_seconds=None):
        raw = json.dumps(value)
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        with self._lock:
            self._data[key] = (raw, expires_at)

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def try_claim(self, key, value, ttl_seconds=None):
        raw = json.dumps(value)
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        with self._lock:
            entry = self._data.get(key)
            if entry is not None:
                _existing_raw, existing_expires_at = entry
                if existing_expires_at is None or time.time() <= existing_expires_at:
                    return False  # still live, someone else's claim
            self._data[key] = (raw, expires_at)
            return True


class RedisKVStore(KVStore):
    def __init__(self, client):
        self._r = client

    def keys(self, prefix):
        return list(self._r.scan_iter(match=prefix + '*', count=100))

    def _change_claim(self, key, value, ttl_seconds=None):
        from redis.exceptions import WatchError
        with self._r.pipeline() as pipe:
            try:
                pipe.watch(key)
                if pipe.get(key) != json.dumps(value):
                    return False
                pipe.multi()
                if ttl_seconds is None:
                    pipe.delete(key)
                else:
                    pipe.expire(key, max(1, int(ttl_seconds)))
                pipe.execute()
                return True
            except WatchError:
                return False

    def renew_claim(self, key, value, ttl_seconds):
        return self._change_claim(key, value, ttl_seconds)

    def release_claim(self, key, value):
        return self._change_claim(key, value)

    def get_json(self, key):
        raw = self._r.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set_json(self, key, value, ttl_seconds=None):
        raw = json.dumps(value)
        if ttl_seconds:
            # Redis TTLs are whole seconds - round up rather than down so a
            # sub-second ttl_seconds (nothing in this codebase's actual
            # usage needs one, but the interface doesn't forbid it) doesn't
            # silently become 0, which SETEX rejects outright.
            self._r.set(key, raw, ex=max(1, int(ttl_seconds + 0.999)))
        else:
            self._r.set(key, raw)

    def delete(self, key):
        self._r.delete(key)

    def try_claim(self, key, value, ttl_seconds=None):
        raw = json.dumps(value)
        kwargs = {"nx": True}
        if ttl_seconds:
            kwargs["ex"] = max(1, int(ttl_seconds + 0.999))
        # SET ... NX is atomic in Redis: returns None if the key already
        # existed (claim failed), the (truthy) success value otherwise.
        return bool(self._r.set(key, raw, **kwargs))


# ─── Sliding-window counter (per-IP rate limit AND per-API-key daily quota -
# same mechanism, different window/max) ────────────────────────────────────

class RateLimiter:
    def hit(self, key: str, window_seconds: float, max_hits: int) -> bool:
        """Records one hit for `key`. Returns True if this hit is within the
        allowed limit, False if it should be rejected (and is NOT counted
        against future hits - a rejected request doesn't consume budget)."""
        raise NotImplementedError


class InMemoryRateLimiter(RateLimiter):
    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def hit(self, key, window_seconds, max_hits):
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]
            if len(hits) >= max_hits:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


class RedisRateLimiter(RateLimiter):
    """A Redis sorted set per key: score = hit timestamp. Old entries are
    trimmed on every call (ZREMRANGEBYSCORE) rather than relying purely on
    TTL, so the window is a genuine sliding window, not a fixed bucket."""

    def __init__(self, client):
        self._r = client

    def hit(self, key, window_seconds, max_hits):
        now = time.time()
        rkey = f"ratelimit:{key}"
        cutoff = now - window_seconds
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(rkey, 0, cutoff)
        pipe.zcard(rkey)
        _, count = pipe.execute()
        if count >= max_hits:
            return False
        # Unique member per hit - two hits landing on the same float
        # timestamp must not collide and overwrite each other in the set.
        self._r.zadd(rkey, {f"{now}:{uuid.uuid4().hex[:8]}": now})
        self._r.expire(rkey, int(window_seconds) + 1)
        return True


# ─── Backend selection ────────────────────────────────────────────────────

class SQLiteKVStore(KVStore):
    """Durable single-machine state. Redis remains the multi-replica backend."""
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get_json(self, key):
        with self._connect() as db:
            row = db.execute('SELECT value FROM kv WHERE key=? AND (expires IS NULL OR expires>?)', (key, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def set_json(self, key, value, ttl_seconds=None):
        with self._connect() as db:
            db.execute('INSERT OR REPLACE INTO kv VALUES(?,?,?)',
                       (key, json.dumps(value), time.time() + ttl_seconds if ttl_seconds else None))

    def delete(self, key):
        with self._connect() as db:
            db.execute('DELETE FROM kv WHERE key=?', (key,))

    def try_claim(self, key, value, ttl_seconds=None):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM kv WHERE key=? AND expires<=?', (key, time.time()))
            cursor = db.execute('INSERT OR IGNORE INTO kv VALUES(?,?,?)',
                                (key, json.dumps(value), time.time() + ttl_seconds if ttl_seconds else None))
            return cursor.rowcount == 1

    def keys(self, prefix):
        with self._connect() as db:
            rows = db.execute('SELECT key FROM kv WHERE substr(key,1,?)=? AND (expires IS NULL OR expires>?)',
                              (len(prefix), prefix, time.time())).fetchall()
        return [row[0] for row in rows]

    def renew_claim(self, key, value, ttl_seconds):
        with self._connect() as db:
            cursor = db.execute('UPDATE kv SET expires=? WHERE key=? AND value=? AND expires>?',
                                (time.time() + ttl_seconds, key, json.dumps(value), time.time()))
            return cursor.rowcount == 1

    def release_claim(self, key, value):
        with self._connect() as db:
            db.execute('DELETE FROM kv WHERE key=? AND value=?', (key, json.dumps(value)))


def create_stores():
    """Use configured Redis or local SQLite; never silently discard configured shared state."""
    if config.REDIS_URL:
        try:
            import redis
            client = redis.from_url(
                config.REDIS_URL, decode_responses=True,
                socket_connect_timeout=5, socket_timeout=5,
            )
            client.ping()
            _safe_print('[store] Connected to Redis; shared state enabled.')
            return RedisKVStore(client), RedisRateLimiter(client)
        except Exception as e:
            raise RuntimeError('Configured Redis is unavailable. Refusing to silently switch state backends.') from None
    return SQLiteKVStore(config.STATE_DB_PATH), InMemoryRateLimiter()
