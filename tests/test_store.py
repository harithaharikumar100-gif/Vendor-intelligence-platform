"""
Tests for store.py's KVStore and RateLimiter implementations. Runs the SAME
test bodies against both InMemory* and Redis* (backed by fakeredis, a
high-fidelity in-process fake implementing real Redis command semantics -
not a real Redis server, so this doesn't verify actual network behavior,
but does verify the command logic itself) so the two backends are held to
an identical behavioral contract.
"""
import time

import pytest
import fakeredis

import store


@pytest.fixture(params=["memory", "redis"])
def kv(request):
    if request.param == "memory":
        return store.InMemoryKVStore()
    return store.RedisKVStore(fakeredis.FakeStrictRedis(decode_responses=True))


@pytest.fixture(params=["memory", "redis"])
def limiter(request):
    if request.param == "memory":
        return store.InMemoryRateLimiter()
    return store.RedisRateLimiter(fakeredis.FakeStrictRedis(decode_responses=True))


class TestKVStore:
    def test_get_missing_key_returns_none(self, kv):
        assert kv.get_json("nope") is None

    def test_set_then_get_roundtrips(self, kv):
        kv.set_json("k1", {"a": 1, "b": "two"})
        assert kv.get_json("k1") == {"a": 1, "b": "two"}

    def test_overwrite_replaces_value(self, kv):
        kv.set_json("k1", {"v": 1})
        kv.set_json("k1", {"v": 2})
        assert kv.get_json("k1") == {"v": 2}

    def test_delete_removes_key(self, kv):
        kv.set_json("k1", {"v": 1})
        kv.delete("k1")
        assert kv.get_json("k1") is None

    def test_delete_missing_key_does_not_raise(self, kv):
        kv.delete("never-existed")  # must not throw

    def test_ttl_expiry(self, kv):
        # Redis TTLs are whole seconds, so this needs >=1s to behave
        # identically across both backends.
        kv.set_json("k1", {"v": 1}, ttl_seconds=1)
        assert kv.get_json("k1") == {"v": 1}
        time.sleep(1.3)
        assert kv.get_json("k1") is None

    def test_no_ttl_never_expires(self, kv):
        kv.set_json("k1", {"v": 1})
        time.sleep(0.1)
        assert kv.get_json("k1") == {"v": 1}


class TestTryClaim:
    def test_first_claim_succeeds(self, kv):
        assert kv.try_claim("lock1", {"owner": "a"}) is True
        assert kv.get_json("lock1") == {"owner": "a"}

    def test_second_claim_on_same_key_fails(self, kv):
        """The exact race this exists to close: two near-simultaneous
        requests for the same key must not both "win"."""
        assert kv.try_claim("lock1", {"owner": "a"}) is True
        assert kv.try_claim("lock1", {"owner": "b"}) is False
        # the first claim's value is untouched by the failed second attempt
        assert kv.get_json("lock1") == {"owner": "a"}

    def test_claim_succeeds_again_after_ttl_expiry(self, kv):
        assert kv.try_claim("lock1", {"owner": "a"}, ttl_seconds=1) is True
        time.sleep(1.3)
        assert kv.try_claim("lock1", {"owner": "b"}) is True
        assert kv.get_json("lock1") == {"owner": "b"}

    def test_claim_succeeds_again_after_explicit_delete(self, kv):
        kv.try_claim("lock1", {"owner": "a"})
        kv.delete("lock1")
        assert kv.try_claim("lock1", {"owner": "b"}) is True


class TestRateLimiter:
    def test_allows_up_to_max_hits(self, limiter):
        for _ in range(3):
            assert limiter.hit("client-a", window_seconds=60, max_hits=3) is True

    def test_rejects_beyond_max_hits(self, limiter):
        for _ in range(3):
            limiter.hit("client-a", window_seconds=60, max_hits=3)
        assert limiter.hit("client-a", window_seconds=60, max_hits=3) is False

    def test_rejected_hit_does_not_consume_budget(self, limiter):
        for _ in range(3):
            limiter.hit("client-a", window_seconds=60, max_hits=3)
        limiter.hit("client-a", window_seconds=60, max_hits=3)  # rejected
        limiter.hit("client-a", window_seconds=60, max_hits=3)  # also rejected
        # still exactly at the limit, not further over it - the rejections
        # themselves weren't recorded as additional hits
        assert limiter.hit("client-a", window_seconds=60, max_hits=3) is False

    def test_window_slides(self, limiter):
        for _ in range(2):
            limiter.hit("client-a", window_seconds=0.1, max_hits=2)
        assert limiter.hit("client-a", window_seconds=0.1, max_hits=2) is False
        time.sleep(0.15)
        assert limiter.hit("client-a", window_seconds=0.1, max_hits=2) is True

    def test_different_keys_are_independent(self, limiter):
        for _ in range(3):
            limiter.hit("client-a", window_seconds=60, max_hits=3)
        assert limiter.hit("client-a", window_seconds=60, max_hits=3) is False
        assert limiter.hit("client-b", window_seconds=60, max_hits=3) is True


class TestCreateStores:
    def test_no_redis_url_falls_back_to_in_memory(self, monkeypatch):
        monkeypatch.setattr(store.config, "REDIS_URL", "")
        kv, limiter = store.create_stores()
        assert isinstance(kv, store.InMemoryKVStore)
        assert isinstance(limiter, store.InMemoryRateLimiter)

    def test_unreachable_redis_falls_back_to_in_memory(self, monkeypatch):
        """A configured-but-down Redis must degrade the service to
        single-instance behavior, not crash it."""
        monkeypatch.setattr(store.config, "REDIS_URL", "redis://localhost:1/0")
        kv, limiter = store.create_stores()
        assert isinstance(kv, store.InMemoryKVStore)
        assert isinstance(limiter, store.InMemoryRateLimiter)
