# Solution 1.8 client (Python) -- one call vs N+1 calls, timed.
import json, time, urllib.request

def get_json(path):
    with urllib.request.urlopen("http://localhost:3000" + path, timeout=5) as res:
        if res.status != 200:
            raise RuntimeError(f"service returned {res.status}")
        return json.load(res)

def main():
    get_json("/events")                                   # warm-up: pay connection setup outside the timers

    t0 = time.perf_counter()
    get_json("/events")
    t1 = time.perf_counter()
    print(f"one call (list only): {(t1 - t0) * 1000:.1f} ms")

    t0 = time.perf_counter()
    events = get_json("/events")
    bookable = [e for e in events if e["seatsLeft"] > 0]
    for e in bookable:                                    # sequential, as a naive client would
        get_json(f"/events/{e['id']}")
    t1 = time.perf_counter()
    print(f"N+1 calls (list, then each bookable event): {(t1 - t0) * 1000:.1f} ms")
    print(f"(N = {len(bookable)} bookable events, so {2 + len(bookable)} requests in the second block)")

main()
