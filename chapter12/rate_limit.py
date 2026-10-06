# Listing 12.1 -- rate_limit.py: a token bucket, and why a service must
# protect itself. No service has infinite capacity; past its limit, MORE
# load makes it slower for EVERYONE, so a request it cannot serve well it
# should refuse FAST -- a 429 in a millisecond beats a timeout in thirty
# seconds. The token bucket is the standard mechanism: a bucket refills at
# a steady rate; each request spends a token; an empty bucket means refuse.
import time

class TokenBucket:
    def __init__(self, rate_per_sec, burst):
        self.rate = rate_per_sec        # steady-state requests/second allowed
        self.capacity = burst           # how many can arrive at once
        self.tokens = burst
        self.last = time.monotonic()

    def allow(self):
        now = time.monotonic()
        # refill proportional to elapsed time, capped at capacity
        self.tokens = min(self.capacity,
                          self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False                    # bucket empty -> 429, immediately

# Per-caller buckets: one noisy client cannot starve the others. The KEY is
# the authenticated principal (Chapter 8), never something the caller can
# forge -- rate limits are an authority-scoped resource, like everything else.
class PerCallerLimiter:
    def __init__(self, rate_per_sec, burst):
        self.rate, self.burst = rate_per_sec, burst
        self.buckets = {}

    def allow(self, caller):
        b = self.buckets.get(caller)
        if b is None:
            b = self.buckets[caller] = TokenBucket(self.rate, self.burst)
        return b.allow()

if __name__ == "__main__":
    # A caller allowed 5/sec with burst 5, hit with 12 rapid requests.
    limiter = PerCallerLimiter(rate_per_sec=5, burst=5)
    allowed = refused = 0
    print("12 rapid requests from one caller (limit 5/s, burst 5):")
    for i in range(12):
        ok = limiter.allow("student:kim")
        print(f"  req {i+1:2}: {'200 allowed' if ok else '429 refused'}")
        if ok: allowed += 1
        else: refused += 1
    print(f"burst absorbed {allowed}, refused {refused} instantly")

    print("\nafter waiting 1 second (bucket refills ~5 tokens):")
    time.sleep(1)
    refilled = sum(1 for _ in range(6) if limiter.allow("student:kim"))
    print(f"  {refilled} more allowed, then refused again -- steady rate holds")

    print("\na second caller is unaffected by the first's exhaustion:")
    print("  student:ana req 1:",
          "200 allowed" if limiter.allow("student:ana") else "429 refused")
