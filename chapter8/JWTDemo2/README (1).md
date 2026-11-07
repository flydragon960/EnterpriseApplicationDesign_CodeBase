# Chapter 8 Demo — Authentication, Authorization, and Delegation

This demo has seven Python files. Together they show everything in Chapter 8, starting from the basics: how a private and public key work, what a JWT is made of, then issuing and checking tokens, three attacks on careless verifiers, scopes at the door, and an agent booking a seat on someone's behalf.

| File | Listing | What it does |
|---|---|---|
| `keys_demo.py` | 8.1 | The key-pair idea on its own: sign with the private key, check with the public key, tampering fails, forging fails. Contrasts a shared secret (HMAC). |
| `jwt_demo.py` | 8.2 | Builds a JWT by hand (header.payload.signature), reads it without a key, checks it by hand, and shows PyJWT accepts it. |
| `auth.py` | 8.3 | Issues tokens (`issue`) and verifies them correctly (`verify`). Also keeps two **wrong** verifiers so the attacks can be shown. |
| `app.py` | 8.4 | A small Encore API (Flask) guarded by two decorators: `authenticated()` (who are you?) and `requires_scope()` (what may you do?). |
| `attacks.py` | 8.5 | Runs three forged tokens against a naive verifier and against the honest `verify()`. |
| `client.py` | 8.6 | Calls the API **the right way**: renews tokens before they expire, retries once on 401, stops on 403, sets a timeout, never prints a whole token. |
| `delegation_client.py` | 8.7 | The delegation demo in depth: the two wrong ways to let an agent act for kim, the right way (narrower, shorter-lived, attributed), what a delegated token cannot do, and the resulting audit trail. |

The demo has three parts. **Part 0** (the basics) and **Part 1** (the attacks) each run in a single terminal and need no server. **Part 2** uses two terminals: one runs the server, and the other sends requests with `curl`.

---

## 1. Setup (once)

Requires Python 3.9 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask pyjwt cryptography requests
```

The first time `auth.py` is imported, it creates an RSA key pair and saves it as `/tmp/encore_priv.pem` and `/tmp/encore_pub.pem`. Every process (the server, the attack script, and the token-minting commands) reads the same key files. That is how they all trust the same issuer. In production, this shared file would be a published JWKS endpoint.

> **Windows users:** `/tmp` becomes `C:\tmp` on the current drive. Create that folder first (`mkdir C:\tmp`), or change the two paths at the top of `auth.py`.

---

## 2. Part 0 — The basics: keys and JWTs

These two scripts are self-contained. They make their own keys in memory and do not use `auth.py` or the `/tmp` key files.

### 2.1 Private key and public key

```bash
python3 keys_demo.py
```

Expected output (the base64 values differ on every run):

```
Step 2 -- the issuer signs a message with its PRIVATE key
   message   : student:kim may read events
   signature : jIR+Ah6E0D0ueQvOaOfnhW8y...(256 bytes)

Step 3 -- anyone checks the signature with the PUBLIC key
   original message           : VALID

Step 4 -- change anything and the check fails
   message edited             : INVALID
   signature edited (1 bit)   : INVALID

Step 5 -- without the issuer's private key, you cannot forge
   attacker signs with own key: INVALID
   public key can sign?       : False

Contrast -- a shared secret (HMAC): the same key signs AND checks
   verifier checks the tag    : VALID
   ...but the verifier can also create a tag for ANY message:
   tag for the edited message : 71jCl4nLZKzPlOShFksDebx3...(32 bytes)
   => whoever can check can also forge. A key pair separates the two.
```

**What to point out**

- **Step 3:** the message is readable. A signature proves who wrote it and that it was not changed; it does not hide it.
- **Step 4:** changing one word, or one bit of the signature, makes the check fail.
- **Step 5:** an attacker's own key pair is useless, and the public key has no `sign` method at all. Holding the public key gives the power to check, never to sign.
- **Contrast:** with a shared secret, any service that can check can also forge. Keep this in mind for Attack B later.

**Optional question for the class:** before running Step 5, ask "Encore has the public key. Can Encore make a token for kim?"

### 2.2 A JWT built by hand

```bash
python3 jwt_demo.py
```

Expected output (abridged):

```
Step 2 -- encode, sign, and join with dots
   header    : eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9
   payload   : eyJpc3MiOiJodHRwczovL2lkLmVuY29yZS5leGFt...
   signature : ZWBo4sLT8yhJNlwgTjIvd7hH6M7xEz07F8vBBrGA...
   token length: 552 characters, 3 parts

Step 3 -- decoding needs no key (signed, not encrypted)
   payload read back: {'iss': ..., 'sub': 'student:kim', 'scope': 'events:read', ...}

Step 4 -- check the signature by hand with the PUBLIC key
   our token                 : VALID
   payload edited, old sig   : INVALID

Step 5 -- PyJWT accepts our hand-made token
   jwt.decode -> sub         : student:kim
   jwt.encode, same token?   : True
   tampered token            : REJECTED ( InvalidSignatureError )
```

**What to point out**

- **Step 2:** a JWT is just three base64url strings joined by dots. The header always starts with `eyJ`, which is how base64url writes `{"`.
- **Step 3:** anyone can read the payload without a key. This is the "postcard" rule.
- **Step 4:** the signature check is the same RSA check as in `keys_demo.py`, now applied to the text `header.payload`.
- **Step 5:** a JWT library does nothing magical. PyJWT accepts the hand-made token, and `jwt.encode` produces the same bytes. (The `True` depends on PyJWT writing the JSON exactly as we did; it does in PyJWT 2.x. If a future version prints `False`, the decode line still proves the point.)

**Optional live demo:** add `print(token)` at the end of `jwt_demo.py` and paste the output into [jwt.io](https://jwt.io) to show the three coloured parts. Use only demo tokens on public websites, never real ones.

---

## 3. Part 1 — The three attacks

```bash
python3 attacks.py
```

Expected output:

```
Attack A -- tampered scope (payload edited, signature stale)
   naive  : scope now 'events:read events:admin'  <- attacker granted self admin
   honest : REJECTED  ( InvalidSignatureError )

Attack B -- alg=none (unsigned token, header says 'trust me')
   naive  : scope 'events:admin'  <- forged with NO key at all
   honest : REJECTED  ( InvalidAlgorithmError )

Attack C -- wrong audience (token minted for the library)
   naive  : accepted a token whose aud is 'https://api.library.example'  <- confused deputy
   honest : REJECTED  ( InvalidAudienceError )
```

**What to point out**

- **Attack A:** `verify_no_verify()` in `auth.py` is the one-liner from tutorials (`verify_signature: False`). It *reads* the claims but never *checks* them.
- **Attack B:** `verify_trusting_header()` lets the token's own header choose the algorithm. The fix is one argument in `verify()`: `algorithms=["RS256"]`.
- **Attack C:** every cryptographic check passes. Only `audience=AUDIENCE` in `verify()` stops it.
- Then open `verify()` and go through it line by line. Every argument blocks one attack: `algorithms`, `issuer`, `audience`, and `options={"require": [...]}`.

**Optional live edit:** delete `audience=AUDIENCE,` from `verify()` and run `attacks.py` again. Attack C's honest line now says `ACCEPTED (this would be a bug)`. Put the line back afterwards.

---

## 4. Part 2 — The live API

### 4.1 Start the server (Terminal 1)

```bash
python3 app.py
```

The server listens on `http://localhost:3000` and starts with two events:

| Event id | Title | Seats left |
|---|---|---|
| `ev_101` | Jazz Ensemble | 42 |
| `ev_102` | Improv Night | 0 |

### 4.2 Mint three tokens (Terminal 2)

Here, the identity provider is just `auth.issue()`. These commands create three tokens with different permissions:

```bash
B=http://localhost:3000

# kim, read-only
READER=$(python3 -c 'import auth; print(auth.issue("student:kim", ["events:read"]))')

# kim, read + book
BOOKER=$(python3 -c 'import auth; print(auth.issue("student:kim", ["events:read","reservations:write"]))')

# calendar agent acting for kim: booking only, 5-minute lifetime
AGENT=$(python3 -c 'import auth; print(auth.issue("agent:calendar-bot", ["reservations:write"], ttl_seconds=300, actor="student:kim"))')
```

Run these commands in the same folder as `auth.py`. Tokens expire after 15 minutes (the agent's after 5). If you see `ExpiredSignatureError`, just mint them again.

**Postcard moment:** a token is signed, not encrypted. You can decode one without any key:

```bash
python3 -c 'import jwt,sys; print(jwt.decode(sys.argv[1], options={"verify_signature": False}))' "$AGENT"
```

```
{'iss': 'https://id.encore.example', 'aud': 'https://api.encore.example',
 'sub': 'agent:calendar-bot', 'scope': 'reservations:write',
 'iat': ..., 'exp': ..., 'act': {'sub': 'student:kim'}}
```

### 4.3 Demo 4 — Scopes at the door

`-w " %{http_code}\n"` prints the status code after each response.

```bash
# 1. no token -> 401
curl -s -w " %{http_code}\n" $B/events

# 2. reader reads -> 200
curl -s -w " %{http_code}\n" -H "Authorization: Bearer $READER" $B/events

# 3. reader tries to book -> 403
curl -s -w " %{http_code}\n" -X POST -H "Authorization: Bearer $READER" $B/events/ev_101/reservations

# 4. booker books -> 201
curl -s -w " %{http_code}\n" -X POST -H "Authorization: Bearer $BOOKER" $B/events/ev_101/reservations
```

Expected results:

| # | Caller | Request | Status | Body |
|---|---|---|---|---|
| 1 | no token | `GET /events` | **401** | `{"error":"missing_token"}` |
| 2 | reader | `GET /events` | **200** | event list, `"as":"student:kim"` |
| 3 | reader | `POST reservation` | **403** | `{"error":"insufficient_scope","need":"reservations:write"}` |
| 4 | booker | `POST reservation` | **201** | `"reservedBy":"student:kim","onBehalfOf":"student:kim"` |

**What to point out:** compare #1 and #3. A 401 means "we don't know who you are, so get a valid token." A 403 means "we know you, but you may not do this, so retrying won't help." Show the comment in `requires_scope()` in `app.py`.

### 4.4 Demo 5 — Delegation

```bash
# 5. agent books for kim -> 201, receipt names both
curl -s -w " %{http_code}\n" -X POST -H "Authorization: Bearer $AGENT" $B/events/ev_101/reservations

# 6. agent tries to read the catalogue -> 403
curl -s -w " %{http_code}\n" -H "Authorization: Bearer $AGENT" $B/events
```

| # | Request | Status | Body |
|---|---|---|---|
| 5 | `POST reservation` | **201** | `"reservedBy":"agent:calendar-bot","onBehalfOf":"student:kim"` |
| 6 | `GET /events` | **403** | `{"error":"insufficient_scope","need":"events:read"}` |

**What to point out**

- **Attributed:** the receipt in #5 names both the agent and kim. See the last lines of `reserve()` in `app.py`.
- **Narrower than kim:** in #6 the agent cannot read the catalogue, even though kim can (#2). It was given only `reservations:write`.
- **Time-limited:** the agent's token lives 5 minutes, while kim's lives 15.

### 4.5 Extra failures (optional)

These four show that the same `verify()` protects the live server, not just the attack script.

```bash
# 7. sold-out event -> 409 (a domain rule, not an auth rule)
curl -s -w " %{http_code}\n" -X POST -H "Authorization: Bearer $BOOKER" $B/events/ev_102/reservations

# 8. tampered token (reader edits own scope to add reservations:write) -> 401 InvalidSignatureError
TAMP=$(python3 -c '
import auth, base64, json
h, p, s = auth.issue("student:kim", ["events:read"]).split(".")
b = json.loads(base64.urlsafe_b64decode(p + "=="))
b["scope"] = "events:read reservations:write"
print(h + "." + base64.urlsafe_b64encode(json.dumps(b).encode()).rstrip(b"=").decode() + "." + s)')
curl -s -w " %{http_code}\n" -X POST -H "Authorization: Bearer $TAMP" $B/events/ev_101/reservations

# 9. expired token -> 401 ExpiredSignatureError
EXP=$(python3 -c 'import auth; print(auth.issue("student:kim", ["events:read"], ttl_seconds=-10))')
curl -s -w " %{http_code}\n" -H "Authorization: Bearer $EXP" $B/events
```

**What to point out about #7:** a 409 comes from the domain ("is there a seat left?"), not from the auth layer. This is the layer separation from Section 8.1.

A fourth extra, for Exercise 8.3: stop the server, delete `/tmp/encore_*.pem`, then restart the server and run `curl` with an old token. The token is rejected with `InvalidSignatureError` because the key has rotated. Mint new tokens to continue.

### 4.6 The right way to call the API: `client.py`

`curl` shows the raw protocol. `client.py` shows what a real client must add. Keep the server running in Terminal 1, then in Terminal 2:

```bash
python3 client.py
```

Expected output:

```
1. Normal calls
reader  GET  /events                       200  OK  events: Jazz Ensemble, Improv Night
booker  POST reservation ev_101            201  OK  reservedBy student:kim, onBehalfOf student:kim

2. Errors handled, not retried blindly
reader  POST reservation ev_101            403  FORBIDDEN -- need 'reservations:write'; ask for more permission, do not retry
booker  POST reservation ev_102            409  SOLD OUT -- a domain rule, not an auth problem
booker  POST reservation ev_999            404  NOT FOUND -- check the event id

3. Delegation: the agent books for kim
agent   POST reservation ev_101            201  OK  reservedBy agent:calendar-bot, onBehalfOf student:kim
agent   GET  /events                       403  FORBIDDEN -- need 'events:read'; ask for more permission, do not retry

4. Token expires while held -> 401 -> renew -> retry once
   (401 ExpiredSignatureError -> getting a new token, retrying once)
reader  GET  /events (stale token)         200  OK  events: Jazz Ensemble, Improv Night
   token used first : ...MVBGFFCA
   token used after : ...4auA_c8w (renewed)
```

**What to point out**

- **`TokenSource`** holds a token and renews it 30 seconds *before* `exp`. The client reads `exp` without checking the signature, which is fine: it uses `exp` only to decide when to renew. The *server* is the one that verifies.
- **`EncoreClient.call()`** sends the token only in the `Authorization` header, with a 5-second timeout, and reuses one connection (`requests.Session`).
- **401 → renew and retry once.** The token may have expired or the key may have rotated. A second 401 means a real problem, so it stops instead of looping.
- **403 → stop.** Retrying with the same token cannot help; the caller needs more permission. Compare the two lines in part 2 and part 4: the codes from section 4.3 now drive different behaviour.
- **409 and 404** are domain answers, not auth problems.
- **`masked()`** prints only the last 8 characters. Tokens are bearer credentials: anyone who copies one from a log can use it until it expires.
- In production, `API` must be `https://`. Over plain HTTP, anyone on the network can read the token.

If the server isn't running, the script prints `Cannot reach http://localhost:3000 -- start the server first`.

### 4.7 Delegation in depth: `delegation_client.py`

This script expands Demo 5 and the delegation slides. With the server running in Terminal 1:

```bash
python3 delegation_client.py
```

Expected output:

```
Request: kim tells her calendar agent 'Book me into the Jazz Ensemble.'

WRONG 1 -- give the agent kim's own token
   agent POST reservation ev_101         201  reservedBy student:kim, onBehalfOf student:kim
   agent GET  /events                    200  read 2 events
   -> receipt says kim did it; the agent left no trace,
      and it holds ALL of kim's power for the token's full 15 minutes

WRONG 2 -- give the agent its own identity
   agent POST reservation ev_101         201  reservedBy agent:calendar-bot, onBehalfOf agent:calendar-bot
   -> the seat is booked by the agent for... itself; the link to kim is lost

RIGHT -- kim delegates a narrow, short-lived permission
   kim's token   : sub=student:kim          act=-            scope='events:read reservations:write'  lifetime=15 min
   agent's token : sub=agent:calendar-bot   act=student:kim  scope='reservations:write'  lifetime=5 min
   agent POST reservation ev_101         201  reservedBy agent:calendar-bot, onBehalfOf student:kim
   agent GET  /events                    403  insufficient_scope (need events:read)
   kim   GET  /events                    200  read 2 events
   -> attributed: the receipt names both;
      narrower: the agent cannot read events, though kim can

LIMIT -- kim cannot delegate what she does not hold
   refused: student:kim cannot delegate ['events:admin']: she does not hold it

WHAT A TOKEN CANNOT DO
   a) it cannot say 'one booking only' -- the agent books again:
   agent POST reservation ev_101 (2nd)   201  reservedBy agent:calendar-bot, onBehalfOf student:kim
   b) it expires, and the agent cannot renew it on its own:
   agent POST with expired grant         401  ExpiredSignatureError
      -> a new grant needs kim (via the identity provider), not the agent
   c) it cannot be revoked early: until exp, it simply works

AUDIT TRAIL -- what the receipts let kim (or an auditor) see
   reservedBy             onBehalfOf           traceable to kim?
   student:kim            student:kim          yes, but the agent is hidden
   agent:calendar-bot     agent:calendar-bot   NO
   agent:calendar-bot     student:kim          yes, and to the agent
   agent:calendar-bot     student:kim          yes, and to the agent
```

**What to point out**

- **WRONG 1** (give the agent kim's token): the booking works, but the receipt says *kim* did it, and the agent can read everything kim can, for 15 minutes.
- **WRONG 2** (agent's own identity): the receipt says the agent booked *for itself*. Nothing links the seat to kim.
- **RIGHT**: compare the two decoded tokens. The agent's token has `act` naming kim, only `reservations:write`, and a 5-minute lifetime instead of 15. The receipt names both parties, and the agent gets 403 on reading events even though kim gets 200.
- **LIMIT**: `delegate()` refuses to give the agent `events:admin`, because kim doesn't hold it. A delegate can never receive more than the principal holds. In production the identity provider enforces this, after kim consents.
- **WHAT A TOKEN CANNOT DO**: (a) it can't say "one booking only", so the second booking also succeeds; (b) when it expires, the agent can't renew it by itself, unlike `client.py`, because a new grant needs kim's consent; (c) it can't be revoked before `exp`. These are the open problems on the "A token is a fixed grant" slide.
- **AUDIT TRAIL**: only the delegated bookings are traceable to both kim *and* the agent.

Note: the seat count for `ev_101` drops by four each run. Restart `app.py` to reset it.

---

## 5. Resetting and troubleshooting

| Problem | Fix |
|---|---|
| Seat counts drifted | Restart `app.py`. Data is in memory only. |
| `ExpiredSignatureError` | Mint the tokens again (section 4.2). |
| `InvalidSignatureError` on a fresh token | The server was started with older key files. Restart it so both sides use the same `/tmp/encore_*.pem`. |
| `Address already in use` | Another process is on port 3000. Stop it, or change `app.run(port=3000)`. |
| `$READER` is empty | You are not in the folder with `auth.py`, or the virtual environment is not active. |
| PowerShell instead of bash | Use `$READER = python -c "..."` to set variables, and `curl.exe` instead of `curl`. Alternatively, run the demo in Git Bash or WSL. |

Every reservation receipt returns the id `res_1`. That is a simplification in the demo, not a bug in the auth code.

---

## 6. Suggested running order (about 35 minutes)

1. `python3 keys_demo.py`: private and public keys (5 min)
2. `python3 jwt_demo.py`: a JWT by hand (5 min)
3. `python3 attacks.py`, then walk through `verify()` (5 min)
4. Start the server, mint tokens, and decode one ("postcard") (2 min)
5. Demo 4, requests #1–#4 (4 min)
6. Demo 5, requests #5–#6 (3 min)
7. Optional extras #7–#9 if time allows (1 min)
8. `python3 client.py`: the right way to call the API (4 min)
9. `python3 delegation_client.py`: delegation in depth (5 min)
