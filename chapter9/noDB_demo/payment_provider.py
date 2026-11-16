# Listing 9.2 (classroom version) -- payment_provider.py: a service Encore
# DOES NOT OWN. It runs in its own process, on its own port, with its own
# "database" (a dict here). Encore cannot lock it, join its transactions, or
# check its versions -- the ownership boundary of Chapter 7, made literal.
# It honors Chapter 3's idempotency contract on ITS side, and it can fail.
#
# Standard library only (no Flask), so there is nothing to install.
# Run: python3 payment_provider.py    (serves :4000)
# demo.py starts it for you if it is not already running.
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHARGES = {}          # idempotency_key -> {"id", "amount", "status"}
_next = {"n": 1}
_lock = threading.Lock()


def _new_charge(key, amount):
    with _lock:
        cid = f"ch_{_next['n']}"
        _next["n"] += 1
        CHARGES[key] = {"id": cid, "amount": amount, "status": "succeeded"}
        return CHARGES[key]


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):          # keep the classroom terminal quiet
        pass

    def _send(self, code, body, headers=None):
        data = json.dumps(body).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass                            # the caller gave up waiting

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    # ---- POST /charges and POST /refunds -------------------------------
    def do_POST(self):
        if self.path == "/charges":
            return self._create_charge()
        if self.path == "/refunds":
            return self._refund()
        self._send(404, {"error": "not_found"})

    def _create_charge(self):
        key = self.headers.get("Idempotency-Key")
        if not key:
            return self._send(422, {"error": "idempotency_key_required"})

        # THEIR idempotency: a repeated key returns the stored charge.
        if key in CHARGES:
            return self._send(200, CHARGES[key], {"Idempotency-Replayed": "true"})

        body = self._body()
        fail = self.headers.get("X-Demo-Fail")          # "decline" | "timeout"
        slow = float(self.headers.get("X-Demo-Slow", 0))

        if fail == "timeout":
            # The charge SUCCEEDS on their side, but the reply is lost: the
            # exact three-state ambiguity of Chapter 1, now across a boundary.
            charge = _new_charge(key, body.get("amount", 0))
            time.sleep(30)                  # longer than any client timeout
            return self._send(201, charge)

        if slow:
            time.sleep(slow)

        if fail == "decline":
            return self._send(402, {"error": "card_declined"})

        self._send(201, _new_charge(key, body.get("amount", 0)))

    def _refund(self):
        """Compensation on THEIR side -- and it too can fail (Section 9.6)."""
        key = self.headers.get("Idempotency-Key")
        charge = self._body().get("charge_id")
        if self.headers.get("X-Demo-Fail") == "refund":
            return self._send(503, {"error": "refund_failed"})
        self._send(201, {"id": f"rf_{key}", "charge_id": charge,
                         "status": "refunded"})

    # ---- GET /charges/<key> ---------------------------------------------
    def do_GET(self):
        """The recovery path THEY provide: ask what happened to an attempt.
        Without this, a timed-out caller could never learn the truth."""
        if self.path.startswith("/charges/"):
            c = CHARGES.get(self.path[len("/charges/"):])
            return self._send(200, c) if c else self._send(404, {"error": "not_found"})
        self._send(404, {"error": "not_found"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    server = ThreadingHTTPServer(("localhost", port), Provider)
    server.daemon_threads = True
    print(f"payment provider listening on :{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
