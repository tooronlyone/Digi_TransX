import time
import threading

# Thread-safe in-memory cache for durable sessions and user identities.
# Short TTL (20 seconds) ensures snappy multi-click navigation without compromising security.
_SESSION_CACHE = {}
_CACHE_LOCK = threading.Lock()
SESSION_CACHE_TTL_SECONDS = 20.0


def get_cached_auth(cache_key):
    now = time.time()
    with _CACHE_LOCK:
        entry = _SESSION_CACHE.get(cache_key)
        if entry:
            expires_at, durable, user = entry
            if now < expires_at:
                return durable, user
            else:
                _SESSION_CACHE.pop(cache_key, None)
    return None, None


def set_cached_auth(cache_key, durable, user, ttl=SESSION_CACHE_TTL_SECONDS):
    expires_at = time.time() + ttl
    with _CACHE_LOCK:
        _SESSION_CACHE[cache_key] = (expires_at, durable, user)


def invalidate_cached_auth(cache_key=None, user_id=None):
    with _CACHE_LOCK:
        if cache_key:
            _SESSION_CACHE.pop(cache_key, None)
        if user_id:
            keys_to_remove = [k for k, v in _SESSION_CACHE.items() if v[2].get("id") == user_id]
            for k in keys_to_remove:
                _SESSION_CACHE.pop(k, None)


def clear_all_cached_auth():
    with _CACHE_LOCK:
        _SESSION_CACHE.clear()
