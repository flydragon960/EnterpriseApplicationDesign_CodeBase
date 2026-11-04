# Listing 8.7 -- delegation_client.py: a calendar agent books a seat for kim.
# Shows the delegation section of Chapter 8 against the live API:
#   1. the two WRONG ways to let an agent act for kim
#   2. the RIGHT way: a delegated token -- narrower, shorter-lived, attributed
#   3. what a delegated token CANNOT do (expiry, no per-action limits)
# Start app.py first, then run: python3 delegation_client.py
import time
import jwt
import requests
import auth          # auth.issue() plays the identity provider

API = "http://localhost:3000"
KIM = "student:kim"
AGENT = "agent:calendar-bot"
KIM_SCOPES = ["events:read", "reservations:write"]


# ---------------------------------------------------------------- helpers
def call(token, method, path):
    """One API call with a bearer token (see client.py for the full pattern)."""
    resp = requests.request(method, API + path,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=5)
    return resp.status_code, resp.json()

def show(label, status, body):
    if "reservedBy" in body:
        detail = f"reservedBy {body['reservedBy']}, onBehalfOf {body['onBehalfOf']}"
    elif "events" in body:
        detail = f"read {len(body['events'])} events"
    elif "need" in body:
        detail = f"{body['error']} (need {body['need']})"
    else:
        detail = body.get("reason", body.get("error"))
    print(f"   {label:<37} {status}  {detail}")
    return body

def claims_of(token):
    """Read a token's claims (no check: we only display them)."""
    c = jwt.decode(token, options={"verify_signature": False})
    minutes = round((c["exp"] - c["iat"]) / 60)
    act = c.get("act", {}).get("sub", "-")
    return f"sub={c['sub']:<20} act={act:<12} scope='{c['scope']}'  lifetime={minutes} min"


def delegate(principal, principal_scopes, agent, scopes, minutes):
    """kim grants the agent a SUBSET of her own permissions, for a short time.

    In production the identity provider runs this check, after kim consents.
    The rule: a delegate can never receive more than the principal holds."""
    extra = set(scopes) - set(principal_scopes)
    if extra:
        raise PermissionError(f"{principal} cannot delegate {sorted(extra)}: "
                              f"she does not hold it")
    return auth.issue(agent, scopes, ttl_seconds=minutes * 60, actor=principal)


# ------------------------------------------------------------------ demo
def main():
    receipts = []
    kim_token = auth.issue(KIM, KIM_SCOPES)          # kim's own token, 15 min

    print("Request: kim tells her calendar agent 'Book me into the Jazz Ensemble.'\n")

    # ---- WRONG 1: hand the agent kim's own token -----------------------
    print("WRONG 1 -- give the agent kim's own token")
    receipts.append(show("agent POST reservation ev_101",
                         *call(kim_token, "POST", "/events/ev_101/reservations")))
    show("agent GET  /events", *call(kim_token, "GET", "/events"))
    print("   -> receipt says kim did it; the agent left no trace,")
    print("      and it holds ALL of kim's power for the token's full 15 minutes\n")

    # ---- WRONG 2: give the agent its own identity, no link to kim ------
    print("WRONG 2 -- give the agent its own identity")
    agent_alone = auth.issue(AGENT, ["reservations:write"])
    receipts.append(show("agent POST reservation ev_101",
                         *call(agent_alone, "POST", "/events/ev_101/reservations")))
    print("   -> the seat is booked by the agent for... itself; the link to kim is lost\n")

    # ---- RIGHT: a delegated token -------------------------------------
    print("RIGHT -- kim delegates a narrow, short-lived permission")
    agent_token = delegate(KIM, KIM_SCOPES, AGENT, ["reservations:write"], minutes=5)
    print("   kim's token   :", claims_of(kim_token))
    print("   agent's token :", claims_of(agent_token))
    receipts.append(show("agent POST reservation ev_101",
                         *call(agent_token, "POST", "/events/ev_101/reservations")))
    show("agent GET  /events", *call(agent_token, "GET", "/events"))
    show("kim   GET  /events", *call(kim_token, "GET", "/events"))
    print("   -> attributed: the receipt names both;")
    print("      narrower: the agent cannot read events, though kim can\n")

    # ---- the grant itself is limited ----------------------------------
    print("LIMIT -- kim cannot delegate what she does not hold")
    try:
        delegate(KIM, KIM_SCOPES, AGENT, ["reservations:write", "events:admin"], 5)
    except PermissionError as e:
        print("   refused:", e)
        print()

    # ---- what a token CANNOT do ---------------------------------------
    print("WHAT A TOKEN CANNOT DO")
    print("   a) it cannot say 'one booking only' -- the agent books again:")
    receipts.append(show("agent POST reservation ev_101 (2nd)",
                         *call(agent_token, "POST", "/events/ev_101/reservations")))
    print("   b) it expires, and the agent cannot renew it on its own:")
    short = delegate(KIM, KIM_SCOPES, AGENT, ["reservations:write"], minutes=0)
    time.sleep(1)                                    # a 0-minute grant: already expired
    show("agent POST with expired grant", *call(short, "POST", "/events/ev_101/reservations"))
    print("      -> a new grant needs kim (via the identity provider), not the agent")
    print("   c) it cannot be revoked early: until exp, it simply works\n")

    # ---- the audit trail ----------------------------------------------
    print("AUDIT TRAIL -- what the receipts let kim (or an auditor) see")
    print(f"   {'reservedBy':<22} {'onBehalfOf':<20} traceable to kim?")
    for r in receipts:
        if "reservedBy" not in r:
            continue
        traced = "yes, and to the agent" if r["reservedBy"] == AGENT and r["onBehalfOf"] == KIM \
            else "yes, but the agent is hidden" if r["reservedBy"] == KIM \
            else "NO"
        print(f"   {r['reservedBy']:<22} {r['onBehalfOf']:<20} {traced}")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("Cannot reach", API, "-- start the server first: python3 app.py")
