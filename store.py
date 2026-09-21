"""
store.py - Persistent state backends for server.py
----------------------------------------------------
server.py previously kept the analysis cache, job store, and rate limiter
as plain in-process dicts. That's fine for a single instance, but breaks
the moment this is deployed behind more than one replica (each replica has
its own, different cache/job-list/rate-limit state) or the process
restarts (everything - including in-flight job records - is silently
dropped).

This module provides the same two primitives server.py actually needs
(a JSON key-value store with TTL, and a sliding-window counter) behind a
small interface, with two implementations:
- InMemory*: today's behavior, unchanged, still the default with no config.
- Redis*: backed by a real Redis instance (REDIS_URL), so state survives a
  restart and is shared correctly across replicas.

create_stores() picks one based on config.REDIS_URL, and falls back to
in-memory (with a logged warning, not a crash) if Redis is configured but
unreachable at startup - a broken cache backend shouldn't take the whole
service down.
"""

import json
import time
import threading
import uuid
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

def create_stores():
    """Returns (kv_store, rate_limiter). Falls back to in-memory - logging
    why, not raising - whenever REDIS_URL is unset or Redis is unreachable
    at startup, so a misconfigured/down cache backend degrades this to
    single-instance behavior instead of taking the whole service down."""
    if config.REDIS_URL:
        try:
            import redis
            client = redis.from_url(
                config.REDIS_URL, decode_responses=True,
                socket_connect_timeout=5, socket_timeout=5,
            )
            client.ping()
            _safe_print(f"[store] Connected to Redis ({config.REDIS_URL}) - state is shared and persistent.")
            return RedisKVStore(client), RedisRateLimiter(client)
        except Exception as e:
            _safe_print(f"[store] REDIS_URL is set but Redis is unreachable ({e}) - "
                        f"falling back to in-memory state (single-instance only).")
    return InMemoryKVStore(), InMemoryRateLimiter()
