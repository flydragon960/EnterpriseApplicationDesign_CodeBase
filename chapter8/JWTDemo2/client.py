# Listing 8.6 -- client.py: calling the protected API the RIGHT way.
# curl shows the raw protocol; a real client must also: hold its token and
# refresh it BEFORE it expires, send it only in the Authorization header,
# react to each status code differently (401: get a new token and retry
# once; 403: stop, retrying cannot help), set a timeout, and never print
# or log the token. Start app.py first, then run: python3 client.py
import time
import jwt
import requests
import auth          # here auth.issue() plays the identity provider

API = "http://localhost:3000"     # in production: always https://


class TokenSource:
    """Holds one caller's token and renews it shortly before it expires.

    In production, get_new() would call the identity provider's token
    endpoint (OAuth 2.0). Here auth.issue() plays that role."""

    def __init__(self, subject, scopes, ttl_seconds=900, actor=None,
                 refresh_margin=30):
        self.subject, self.scopes = subject, scopes
        self.ttl, self.actor, self.margin = ttl_seconds, actor, refresh_margin
        self._token, self._exp = None, 0

    def get_new(self):
        self._token = auth.issue(self.subject, self.scopes,
                                 ttl_seconds=self.ttl, actor=self.actor)
        # The CLIENT may read exp without checking the signature: it only
        # uses it to decide WHEN to renew, and trusts nothing else in it.
        # The SERVER is the one that verifies.
        claims = jwt.decode(self._token, options={"verify_signature": False})
        self._exp = claims["exp"]
        return self._token

    def get(self):
        if self._token is None or time.time() > self._exp - self.margin:
            return self.get_new()          # renew BEFORE it expires
        return self._token


class EncoreClient:
    def __init__(self, tokens):
        self.tokens = tokens
        self.http = requests.Session()     # reuses the connection

    def call(self, method, path):
        resp = self._send(method, path)
        if resp.status_code == 401:
            # Token rejected (expired, rotated key...). Get a new one and
            # retry ONCE. A second 401 is a real problem: do not loop.
            reason = resp.json().get("reason", resp.json()["error"])
            print(f"   (401 {reason} -> getting a new token, retrying once)")
            self.tokens.get_new()
            resp = self._send(method, path)
        return resp

    def _send(self, method, path):
        return self.http.request(
            method, API + path,
            headers={"Authorization": f"Bearer {self.tokens.get()}"},
            timeout=5)                     # never wait forever


def report(label, resp):
    """React to each status code differently, as Chapter 3's rules intend."""
    body = resp.json()
    code = resp.status_code
    if code in (200, 201):
        if "events" in body:
            names = ", ".join(e["title"] for e in body["events"])
            outcome = f"OK  events: {names}"
        else:
            outcome = (f"OK  reservedBy {body['reservedBy']}, "
                       f"onBehalfOf {body['onBehalfOf']}")
    elif code == 401:
        outcome = f"NOT AUTHENTICATED ({body.get('reason', body['error'])}) -- even after one retry"
    elif code == 403:
        outcome = f"FORBIDDEN -- need '{body['need']}'; ask for more permission, do not retry"
    elif code == 404:
        outcome = "NOT FOUND -- check the event id"
    elif code == 409:
        outcome = "SOLD OUT -- a domain rule, not an auth problem"
    else:
        outcome = f"UNEXPECTED {code}: {body}"
    print(f"{label:<42} {code}  {outcome}")


def masked(token):
    """Show only the last few characters (the start is the same for every
    token: eyJhbGciOi...). Never print or log a whole token."""
    return "..." + token[-8:]


def main():
    reader = EncoreClient(TokenSource("student:kim", ["events:read"]))
    booker = EncoreClient(TokenSource("student:kim",
                                      ["events:read", "reservations:write"]))
    agent = EncoreClient(TokenSource("agent:calendar-bot",
                                     ["reservations:write"],
                                     ttl_seconds=300, actor="student:kim"))

    print("1. Normal calls")
    report("reader  GET  /events", reader.call("GET", "/events"))
    report("booker  POST reservation ev_101",
           booker.call("POST", "/events/ev_101/reservations"))
    print()

    print("2. Errors handled, not retried blindly")
    report("reader  POST reservation ev_101",
           reader.call("POST", "/events/ev_101/reservations"))
    report("booker  POST reservation ev_102",
           booker.call("POST", "/events/ev_102/reservations"))
    report("booker  POST reservation ev_999",
           booker.call("POST", "/events/ev_999/reservations"))
    print()

    print("3. Delegation: the agent books for kim")
    report("agent   POST reservation ev_101",
           agent.call("POST", "/events/ev_101/reservations"))
    report("agent   GET  /events", agent.call("GET", "/events"))
    print()

    print("4. Token expires while held -> 401 -> renew -> retry once")
    reader.tokens._token = auth.issue("student:kim", ["events:read"],
                                      ttl_seconds=-10)   # simulate expiry
    reader.tokens._exp = time.time() + 999   # client believes it is fresh
    old = reader.tokens._token
    report("reader  GET  /events (stale token)", reader.call("GET", "/events"))
    print("   token used first :", masked(old))
    print("   token used after :", masked(reader.tokens._token), "(renewed)")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("Cannot reach", API, "-- start the server first: python3 app.py")
