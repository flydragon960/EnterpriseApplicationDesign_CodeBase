# Listing 10.3 -- consumer_contract.py: catching the break the provider's
# own tests cannot see. Run: python3 consumer_contract.py
#
# Chapter 2's conformance suite checked the provider against ITS OWN
# contract. But a provider can change its contract in a way that is
# internally consistent and still breaks a specific consumer that depended
# on part of it. Consumer-driven contracts invert the direction: each
# CONSUMER records what it actually relies on, and the provider is verified
# against the UNION of its consumers' real expectations.
import json
import urllib.request
import urllib.error
from jsonschema import Draft202012Validator

# --- what the DOORS-STAFF SCANNER app actually depends on ---
# It reads only id and title. It does NOT care about seatsLeft. Recording
# this is the point: the provider learns it may change seatsLeft freely for
# THIS consumer, but must never touch id or title.
SCANNER_EXPECTS = {
    "interaction": "GET /events/ev_101",
    "response_status": 200,
    "response_shape": {
        "type": "object",
        "required": ["id", "title"],          # scanner's real dependency
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string", "minLength": 1},
        },
    },
}

# --- what the BOOKING WIDGET actually depends on ---
# It reads seatsLeft and needs it non-negative to render availability.
WIDGET_EXPECTS = {
    "interaction": "GET /events/ev_101",
    "response_status": 200,
    "response_shape": {
        "type": "object",
        "required": ["seatsLeft"],
        "properties": {"seatsLeft": {"type": "integer", "minimum": 0}},
    },
}

def verify(provider_base, pact):
    """Replay one consumer's recorded expectation against the live provider."""
    method, path = pact["interaction"].split(" ", 1)
    try:
        with urllib.request.urlopen(provider_base + path, timeout=5) as r:
            status, body = r.status, json.load(r)
    except urllib.error.HTTPError as e:
        status, body = e.code, json.load(e)
    if status != pact["response_status"]:
        return False, f"status {status} != expected {pact['response_status']}"
    errs = list(Draft202012Validator(pact["response_shape"]).iter_errors(body))
    if errs:
        return False, errs[0].message
    return True, "satisfied"

if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
    print(f"Verifying provider at {base} against its consumers' contracts:\n")
    for name, pact in [("scanner", SCANNER_EXPECTS), ("booking-widget", WIDGET_EXPECTS)]:
        ok, msg = verify(base, pact)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:16} {msg}")
