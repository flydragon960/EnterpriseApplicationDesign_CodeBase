# Listing 1.2 (Python) -- A program as the consumer.
# No browser, no HTML: the contract is the product surface.
# Standard library only. Run (with a listing_1_1 server up): python3 listing_1_2.py
import json
import urllib.request
import urllib.error

def find_available():
    try:
        with urllib.request.urlopen("http://localhost:3000/events", timeout=5) as res:
            if res.status != 200:
                raise RuntimeError(f"service returned {res.status}")
            events = json.load(res)
    except (urllib.error.URLError, OSError) as err:
        raise RuntimeError(f"could not reach the service: {err.reason if hasattr(err, 'reason') else err}") from None
    return [e for e in events if e["seatsLeft"] > 0]

if __name__ == "__main__":
    try:
        available = find_available()
        print("bookable events:", [e["title"] for e in available])
    except RuntimeError as err:
        print(err)
