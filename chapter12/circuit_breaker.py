# Listing 12.2 -- circuit_breaker.py: stop calling what is already broken.
# When a downstream dependency (Chapter 9's payment provider) is failing,
# continuing to call it is doubly harmful: each call ties up a worker for a
# full timeout, and the flood of retries keeps the struggling dependency
# down (the thundering herd, from the CALLER's side). A circuit breaker
# watches the failure rate and, past a threshold, "opens" -- failing fast
# WITHOUT calling -- giving the dependency room to recover and freeing the
# caller's resources. It periodically tests the water ("half-open") and
# closes again when the dependency is healthy.
import time

class CircuitOpen(Exception):
    """Raised instead of calling a dependency we believe is down."""

class CircuitBreaker:
    def __init__(self, fail_threshold=5, recovery_timeout=3.0):
        self.fail_threshold = fail_threshold      # consecutive fails -> open
        self.recovery_timeout = recovery_timeout  # how long to stay open
        self.state = "closed"                     # closed | open | half_open
        self.failures = 0
        self.opened_at = None

    def call(self, fn, *args, **kwargs):
        if self.state == "open":
            if time.monotonic() - self.opened_at >= self.recovery_timeout:
                self.state = "half_open"          # time to test the water
            else:
                raise CircuitOpen()               # fail fast, do NOT call

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def _on_failure(self):
        self.failures += 1
        if self.state == "half_open" or self.failures >= self.fail_threshold:
            self.state = "open"                   # trip (or re-trip)
            self.opened_at = time.monotonic()

    def _on_success(self):
        self.failures = 0
        self.state = "closed"                     # recovered

if __name__ == "__main__":
    # A dependency that is down for a while, then recovers.
    clock = {"t": 0.0}
    def flaky_provider():
        # "down" for the first stretch of wall time, healthy after
        if time.monotonic() - START < 2.0:
            raise ConnectionError("provider down")
        return "charged"

    START = time.monotonic()
    breaker = CircuitBreaker(fail_threshold=5, recovery_timeout=1.0)

    outcomes = {"called_and_failed": 0, "fast_failed": 0, "succeeded": 0}
    for i in range(40):
        try:
            breaker.call(flaky_provider)
            outcomes["succeeded"] += 1
            tag = "OK"
        except CircuitOpen:
            outcomes["fast_failed"] += 1          # did NOT touch the provider
            tag = "circuit open (fast fail, provider spared)"
        except ConnectionError:
            outcomes["called_and_failed"] += 1
            tag = "called provider, it failed"
        if i % 5 == 0 or breaker.state != "closed":
            print(f"  req {i:2} [{breaker.state:9}] {tag}")
        time.sleep(0.1)

    print(f"\ncalled-and-failed: {outcomes['called_and_failed']}  "
          f"(each a wasted timeout on a known-down service)")
    print(f"fast-failed:       {outcomes['fast_failed']}  "
          f"(refused instantly, provider left alone to recover)")
    print(f"succeeded:         {outcomes['succeeded']}  "
          f"(after the breaker probed and closed)")
