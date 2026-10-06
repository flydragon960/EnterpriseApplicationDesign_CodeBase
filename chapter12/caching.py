# Listing 12.3 -- caching.py: a cache, the stampede it invites, and two
# distinct cures for two distinct herds.
# Reads dominate most services (Chapter 4's over-fetch, Chapter 6's read
# models), and the cheapest read is one you don't perform. But a cache
# introduces the STAMPEDE (thundering herd): a cached entry expires and the
# requests that wanted it all miss AT ONCE, hitting the database in a spike.
# There are TWO herds and TWO cures, and conflating them is a common error:
#   - ONE hot key expiring -> many simultaneous misses  -> SINGLE-FLIGHT
#   - MANY keys expiring together (same TTL)             -> TTL JITTER
# Jitter (Chapter 3's retry medicine) decorrelates DIFFERENT keys; it does
# nothing for a single key, because one key has one expiry. Know which herd
# you have.
import random
import threading
import time

class DB:
    def __init__(self):
        self.queries = 0
        self.concurrent = 0
        self.peak = 0
        self.lock = threading.Lock()
    def load(self, key):
        with self.lock:
            self.queries += 1
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
        time.sleep(0.05)
        with self.lock:
            self.concurrent -= 1
        return {"key": key, "seatsLeft": 12}

# ---- the naive cache: one hot key, synchronized misses ----
class NaiveCache:
    def __init__(self, db, ttl=1.0):
        self.db, self.ttl, self.store = db, ttl, {}
    def get(self, key):
        e = self.store.get(key)
        if e and time.monotonic() < e[1]:
            return e[0]
        v = self.db.load(key)                       # every misser hits the DB
        self.store[key] = (v, time.monotonic() + self.ttl)
        return v

# ---- single-flight: one misser refills, the rest wait for it ----
class SingleFlightCache:
    def __init__(self, db, ttl=1.0):
        self.db, self.ttl, self.store = db, ttl, {}
        self.locks = {}
        self.guard = threading.Lock()
    def get(self, key):
        e = self.store.get(key)
        if e and time.monotonic() < e[1]:
            return e[0]
        # coordinate: only ONE thread loads this key; others block on its lock
        with self.guard:
            keylock = self.locks.setdefault(key, threading.Lock())
        with keylock:
            e = self.store.get(key)                 # re-check: someone may have filled it
            if e and time.monotonic() < e[1]:
                return e[0]
            v = self.db.load(key)                   # exactly one DB hit per expiry
            self.store[key] = (v, time.monotonic() + self.ttl)
            return v

# ---- jitter: the RIGHT tool for MANY keys expiring together ----
def hammer(cache, n_clients, duration, key="ev_hot"):
    stop = time.monotonic() + duration
    def client():
        while time.monotonic() < stop:
            cache.get(key)
            time.sleep(0.01)
    ts = [threading.Thread(target=client) for _ in range(n_clients)]
    for t in ts: t.start()
    for t in ts: t.join()

def expiry_spike(n_keys, jitter, window=0.02):
    """Seed n_keys at the same instant with base TTL 1.0 (+ optional jitter),
    and report the worst burst: how many expire within any `window` slice.
    That burst is the spike of simultaneous DB misses jitter must prevent."""
    base = 1.0
    expiries = sorted(base * (1 + random.uniform(0, jitter)) for _ in range(n_keys))
    peak, j = 0, 0
    for i in range(len(expiries)):
        while expiries[i] - expiries[j] > window:
            j += 1
        peak = max(peak, i - j + 1)
    return peak

if __name__ == "__main__":
    print("HERD 1 -- one hot key, 50 clients, 3s, TTL 1.0s:\n")
    d1 = DB(); hammer(NaiveCache(d1), 50, 3.0)
    print(f"  naive        : {d1.queries} queries, peak {d1.peak} concurrent"
          f"  <- 50 miss the same instant")
    d2 = DB(); hammer(SingleFlightCache(d2), 50, 3.0)
    print(f"  single-flight: {d2.queries} queries, peak {d2.peak} concurrent"
          f"  <- one refills, 49 wait")

    print("\nHERD 2 -- 1000 keys seeded together, worst burst in any 20ms:\n")
    print(f"  fixed TTL    : {expiry_spike(1000, jitter=0)} expire at once"
          f"  <- one giant synchronized spike")
    print(f"  jittered TTL : {expiry_spike(1000, jitter=0.4)} expire at once"
          f"  <- smeared across time")

    print("\nTwo herds, two cures: single-flight for a hot key, jitter for")
    print("correlated expiries -- and jitter is Chapter 3's retry medicine.")
