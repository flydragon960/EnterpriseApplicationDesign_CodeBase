# Listing 3.2 -- Two clients meet the lost reply.
# The naive client retries with a FRESH key and double-books.
# The correct client retries with the SAME key and is safe.
# Run (with listing_3_1_server.py up): python3 listing_3_2_client.py
import json
import urllib.request
import urllib.error
import socket
import uuid

BASE = "http://localhost:3000"

def post_reservation(event_id, key, lose_reply=False, timeout=1):
    req = urllib.request.Request(
        f"{BASE}/events/{event_id}/reservations", method="POST", data=b"{}",
        headers={"Content-Type": "application/json", "Idempotency-Key": key,
                 **({"X-Demo-Lose-Reply": "true"} if lose_reply else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.load(res), res.headers.get("Idempotency-Replayed")
    except urllib.error.HTTPError as err:
        return err.code, json.load(err), err.headers.get("Idempotency-Replayed")

def seats(event_id):
    with urllib.request.urlopen(f"{BASE}/events/{event_id}") as res:
        return json.load(res)["seatsLeft"]

def naive_client(event_id):
    """Retries the way local code retries: just call it again."""
    print(f"\n--- NAIVE client on {event_id} (seats before: {seats(event_id)}) ---")
    try:
        post_reservation(event_id, key=str(uuid.uuid4()), lose_reply=True)
    except (TimeoutError, socket.timeout, urllib.error.URLError):
        print("timed out ... retrying with a FRESH key (the bug)")
        status, body, _ = post_reservation(event_id, key=str(uuid.uuid4()))
        print(f"retry answered {status}: {body}")
    print(f"seats after: {seats(event_id)}   <- one student, two seats gone")

def correct_client(event_id):
    """Retries with the same idempotency key, as the contract instructs."""
    print(f"\n--- CORRECT client on {event_id} (seats before: {seats(event_id)}) ---")
    key = str(uuid.uuid4())
    try:
        post_reservation(event_id, key=key, lose_reply=True)
    except (TimeoutError, socket.timeout, urllib.error.URLError):
        print("timed out ... retrying with the SAME key")
        status, body, replayed = post_reservation(event_id, key=key)
        print(f"retry answered {status} (replayed={replayed}): {body}")
    print(f"seats after: {seats(event_id)}   <- applied exactly once")

def race_for_last_seats(event_id):
    """ev_103 has 2 seats; three students want them."""
    print(f"\n--- THREE students, {seats(event_id)} seats on {event_id} ---")
    for student in ("kim", "ana", "raj"):
        status, body, _ = post_reservation(event_id, key=f"{student}-attempt-1")
        print(f"{student}: {status} {body}")

if __name__ == "__main__":
    naive_client("ev_101")
    correct_client("ev_101")
    race_for_last_seats("ev_103")
