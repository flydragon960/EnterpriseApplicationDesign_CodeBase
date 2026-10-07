"""
demo_client.py  --  one client for all four pattern servers
====================================================================
Start ANY one of the four servers (they all listen on :3000), then run:
    python demo_client.py

It runs the same scenario against whatever is running, and prints the pattern
name the server reports -- so you can start each server in turn and watch the
SAME behavior from four different internal designs.

(No dependencies beyond the standard library.)

Equivalent curl commands are printed at the end for reference.
"""
import json
import urllib.request

BASE = "http://localhost:3000"


def call(method, path, headers=None):
    req = urllib.request.Request(BASE + path, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def show(label, result):
    status, body = result
    print(f"{label:<46} -> {status}  {json.dumps(body, separators=(',', ':'))}")


def main():
    # which pattern are we talking to?
    _, info = call("GET", "/events")
    print("=" * 74)
    print(f"Talking to pattern:  {info.get('pattern', '?')}")
    print("=" * 74)

    show("1) GET /events (ev_101 cap 3, ev_102 cap 1)", call("GET", "/events"))
    print()
    show("2) reserve ev_101  (#1)", call("POST", "/events/ev_101/reservations"))
    show("   reserve ev_101  (#2)", call("POST", "/events/ev_101/reservations"))
    show("   reserve ev_101  (#3)", call("POST", "/events/ev_101/reservations"))
    print()
    show("3) reserve ev_101  (#4 -> sold_out 409)", call("POST", "/events/ev_101/reservations"))
    print()
    show("4) GET /events (ev_101 now 0)", call("GET", "/events"))
    print()
    show("5) cancel res_1 (frees a seat)", call("DELETE", "/reservations/res_1"))
    show("6) GET /events (ev_101 back to 1)", call("GET", "/events"))
    print()
    show("7) reserve unknown event (-> 404)", call("POST", "/events/ev_999/reservations"))

    # idempotency demo (only the service-layer server honors the key; the others
    # just make a new reservation -- which itself is an instructive contrast)
    print()
    print("-- idempotency (Idempotency-Key header) --")
    h = {"Idempotency-Key": "k1"}
    show("8) reserve ev_102 with key k1", call("POST", "/events/ev_102/reservations", h))
    show("   reserve ev_102 with key k1 again", call("POST", "/events/ev_102/reservations", h))
    print("   (service-layer server: same reservation, 'replayed':true.")
    print("    other servers: a 2nd attempt -> sold_out, since ev_102 cap is 1.)")

    print()
    print("Equivalent curl commands:")
    print('  curl -s http://localhost:3000/events')
    print('  curl -s -X POST http://localhost:3000/events/ev_101/reservations')
    print('  curl -s -X DELETE http://localhost:3000/reservations/res_1')
    print('  curl -s -X POST http://localhost:3000/events/ev_102/reservations \\')
    print('       -H "Idempotency-Key: k1"')


if __name__ == "__main__":
    main()
