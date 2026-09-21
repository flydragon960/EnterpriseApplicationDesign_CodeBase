# Listing 11.2 -- app.py: an instance the platform can operate.
# A deployable service must answer two questions the orchestrator asks
# constantly, and they are DIFFERENT questions:
#   liveness  -- "are you alive, or should I kill and restart you?"
#   readiness -- "are you ready for traffic, or should I route around you?"
# Conflating them is a classic outage: a liveness check that also pings the
# database will report the WHOLE FLEET dead when the database blips, and the
# orchestrator will restart every instance -- turning a database hiccup into
# a total outage.
import os
import signal
import threading
import time
from flask import Flask, jsonify
from sqlalchemy import text
from config import Config

cfg = Config(os.environ if os.environ.get("ENCORE_DATABASE_URL")
             else {"ENCORE_DATABASE_URL":
                   "postgresql+psycopg2://encore:encore@localhost/encore"})

from storage import make_session_factory
sf, engine = make_session_factory(cfg.database_url)

app = Flask(__name__)
_state = {"ready": False, "draining": False, "in_flight": 0}
_lock = threading.Lock()

# ---- liveness: cheap, local, no dependencies ----
@app.get("/healthz")
def liveness():
    """Am I a functioning process? Deliberately checks NOTHING external.
    If this fails, the process is wedged and SHOULD be restarted."""
    return jsonify({"status": "alive"}), 200

# ---- readiness: may I take traffic right now? ----
@app.get("/readyz")
def readiness():
    """Can I actually serve a request? Checks dependencies AND drain state.
    Failing this removes me from the load balancer WITHOUT killing me."""
    if _state["draining"]:
        return jsonify({"status": "draining"}), 503
    try:
        with sf() as s:
            s.execute(text("SELECT 1"))          # can I reach the database?
    except Exception:
        return jsonify({"status": "db_unreachable"}), 503
    if not _state["ready"]:
        return jsonify({"status": "starting"}), 503
    return jsonify({"status": "ready"}), 200

@app.get("/events/<event_id>")
def get_event(event_id):
    with _lock:
        _state["in_flight"] += 1
    try:
        time.sleep(0.05)                          # simulate real work
        return jsonify({"id": event_id, "title": "Demo"}), 200
    finally:
        with _lock:
            _state["in_flight"] -= 1

# ---- graceful drain: the shutdown sequence ----
def graceful_shutdown(signum, frame):
    """On SIGTERM (how orchestrators ask you to stop), do NOT die at once.
    1. Fail readiness so the load balancer stops sending NEW requests.
    2. Wait for in-flight requests to finish.
    3. Then exit. No request is severed mid-flight."""
    print("SIGTERM received: draining", flush=True)
    _state["draining"] = True                     # step 1: readiness now 503
    deadline = time.time() + 30
    while _state["in_flight"] > 0 and time.time() < deadline:  # step 2
        time.sleep(0.1)
    print(f"drained (in_flight={_state['in_flight']}); exiting", flush=True)
    os._exit(0)                                   # step 3

signal.signal(signal.SIGTERM, graceful_shutdown)

def mark_ready():
    # startup work (warm caches, verify migrations) would go here
    _state["ready"] = True
    print("readiness: ready", flush=True)

if __name__ == "__main__":
    threading.Timer(0.5, mark_ready).start()
    app.run(port=cfg.port, threaded=True)
