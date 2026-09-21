# Listing 10.2 -- observability.py: structured logs and a trace, from scratch.
# Real systems use OpenTelemetry; this is the same ideas in 60 lines so the
# mechanism is visible. Two artifacts:
#   - structured logs: JSON events, not prose, each carrying a correlation id
#   - a trace: a tree of timed spans, one per unit of work, sharing a trace id
# The point of both: when a request misbehaves in production, you can
# reconstruct exactly what happened -- across the async and cross-boundary
# seams of Chapters 7 and 9, where a stack trace cannot reach.
import json
import time
import uuid
import contextvars

# The correlation id follows one logical request everywhere it goes -- into
# the worker, out to the payment provider, and back -- so all its log lines
# and spans can be gathered even though they cross processes.
correlation_id = contextvars.ContextVar("correlation_id", default=None)

def log(event, **fields):
    """A log line is a structured EVENT, not a sentence. Machines read it:
    filter by field, aggregate, alert. Prose logs cannot be queried."""
    record = {"ts": round(time.time(), 3), "event": event,
              "correlation_id": correlation_id.get(), **fields}
    print(json.dumps(record))

# ---- tracing: spans in a tree ----
class Tracer:
    def __init__(self):
        self.spans = []
    def span(self, name, **attrs):
        return _Span(self, name, attrs)

class _Span:
    def __init__(self, tracer, name, attrs):
        self.tracer, self.name, self.attrs = tracer, name, attrs
    def __enter__(self):
        self.start = time.perf_counter(); return self
    def __exit__(self, exc_type, *a):
        dur_ms = round((time.perf_counter() - self.start) * 1000, 1)
        self.tracer.spans.append(
            {"name": self.name, "ms": dur_ms,
             "status": "error" if exc_type else "ok", **self.attrs})
        return False

def new_correlation_id():
    cid = f"req_{uuid.uuid4().hex[:8]}"
    correlation_id.set(cid)
    return cid

if __name__ == "__main__":
    # Simulate one reservation request, instrumented end to end.
    tracer = Tracer()
    cid = new_correlation_id()
    log("request.received", path="/events/ev_103/reservations", method="POST")

    with tracer.span("reserve", event="ev_103"):
        with tracer.span("db.hold", table="reservations"):
            time.sleep(0.004)
            log("hold.created", reservation="res_abc", seats_left=1)
        with tracer.span("outbox.enqueue"):
            time.sleep(0.001)
        # the worker, later, in another process -- SAME correlation id
        with tracer.span("provider.charge", peer="payment", amount=1500):
            time.sleep(0.030)
            log("charge.succeeded", charge="ch_1")
        with tracer.span("db.confirm"):
            time.sleep(0.003)
            log("hold.confirmed", reservation="res_abc")

    log("request.completed", status=201)
    print("\n--- trace", cid, "---")
    total = sum(s["ms"] for s in tracer.spans)
    for s in tracer.spans:
        bar = "#" * int(s["ms"])
        print(f"  {s['name']:18} {s['ms']:6.1f}ms {bar}")
    print(f"  {'TOTAL':18} {total:6.1f}ms   "
          f"(provider.charge was {tracer.spans[2]['ms']/total*100:.0f}% of it)")
