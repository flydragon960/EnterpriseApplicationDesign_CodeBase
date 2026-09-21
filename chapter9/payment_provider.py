# Listing 9.2 -- payment_provider.py: a service Encore DOES NOT OWN.
# It runs in its own process, on its own port, with its own database
# (a dict here). Encore cannot lock it, join its transactions, or check
# its versions -- the ownership boundary of Chapter 7, made literal.
# It honors Chapter 3's idempotency contract on ITS side, and it can fail.
# Run: python3 payment_provider.py    (serves :4000)
import random
import sys
import time
from flask import Flask, jsonify, request

app = Flask(__name__)
CHARGES = {}          # idempotency_key -> {"id", "amount", "status"}
_next = {"n": 1}

# Failure knobs the demos set via headers, so we can force each branch.
@app.post("/charges")
def create_charge():
    key = request.headers.get("Idempotency-Key")
    if not key:
        return jsonify({"error": "idempotency_key_required"}), 422

    # THEIR idempotency: a repeated key returns the stored charge.
    if key in CHARGES:
        c = CHARGES[key]
        resp = jsonify(c)
        resp.headers["Idempotency-Replayed"] = "true"
        return resp, 200

    body = request.get_json(silent=True) or {}
    fail = request.headers.get("X-Demo-Fail")            # "decline" | "timeout"
    slow = float(request.headers.get("X-Demo-Slow", 0))

    if fail == "timeout":
        # The charge SUCCEEDS on their side, but the reply is lost: the
        # exact three-state ambiguity of Chapter 1, now across a boundary.
        cid = f"ch_{_next['n']}"; _next["n"] += 1
        CHARGES[key] = {"id": cid, "amount": body.get("amount", 0),
                        "status": "succeeded"}
        time.sleep(30)          # longer than any client timeout
        return jsonify(CHARGES[key]), 201

    if slow:
        time.sleep(slow)

    if fail == "decline":
        return jsonify({"error": "card_declined"}), 402

    cid = f"ch_{_next['n']}"; _next["n"] += 1
    CHARGES[key] = {"id": cid, "amount": body.get("amount", 0),
                    "status": "succeeded"}
    return jsonify(CHARGES[key]), 201

@app.get("/charges/<key>")
def get_charge(key):
    """The recovery path THEY provide: ask what happened to an attempt.
    Without this, a timed-out caller could never learn the truth."""
    c = CHARGES.get(key)
    return (jsonify(c), 200) if c else (jsonify({"error": "not_found"}), 404)

@app.post("/refunds")
def refund():
    """Compensation on THEIR side -- and it too can fail (Section 9.6)."""
    key = request.headers.get("Idempotency-Key")
    charge = (request.get_json(silent=True) or {}).get("charge_id")
    if request.headers.get("X-Demo-Fail") == "refund":
        return jsonify({"error": "refund_failed"}), 503
    return jsonify({"id": f"rf_{key}", "charge_id": charge,
                    "status": "refunded"}), 201

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    app.run(port=port, threaded=True)
