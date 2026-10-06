# Contract-first, done properly (YAML spec + REAL endpoints)

## The correction

An earlier demo (`swagger_from_yaml.py`) served Swagger UI from the YAML but
implemented **no endpoints** -- no `@app.get("/events")`. That is fine ONLY if
your goal is a static documentation site. But it is misleading as a "server":
clicking **Try it out** in that UI would hit `/events` and get a **404**,
because the endpoint doesn't exist. Documentation you can see but not call.

`swagger_contract_first.py` fixes this: the YAML is still the source of truth
**and** the server actually implements the endpoints the contract promises, so
Swagger UI's "Try it out" really works.

## Two different jobs a YAML contract can do

| Job | Needs real endpoints? | Tool |
|-----|----------------------|------|
| Render documentation | **No** | Swagger UI / Redoc / Swagger Editor |
| Implement the service | **Yes** — you hand-write `@app.get(...)` etc. | Flask / FastAPI / Express ... |

A YAML contract does **not** auto-become a running server. Contract-first means:
1. author the contract (YAML) — the truth,
2. **hand-write endpoints that conform to it** — the step the docs-only demo omitted,
3. run a conformance suite to check (2) against (1).

## Run

```bash
pip install flask flask-swagger-ui pyyaml
python swagger_contract_first.py
```

Open **http://localhost:3000/docs**, expand an operation, click **Try it out**,
**Execute** — you get a real 200/201/409, not a 404.

Verified endpoints (all real):
```
GET  /events?bookable=true                 -> {"events":[{"id":"ev_101",...}]}
GET  /events/ev_101                        -> the event
POST /events/ev_101/reservations           -> 201 {"id":"res_1",...}   (needs Idempotency-Key header)
     same key again                        -> 201 {...,"replayed":true} (same reservation)
     (once full)                           -> 409 {"error":"sold_out"}
     (no key)                              -> 422 {"error":"idempotency_key_required"}
```

## When each demo is the right one

- **Just documentation** (contract IS the truth, no live calls needed):
  `swagger_from_yaml.py`, or paste the YAML into editor.swagger.io. No endpoints.
- **Documentation + working endpoints** (Try it out actually runs):
  `swagger_contract_first.py`  <-- use this one for a realistic class demo.
- **Code-first (spec generated FROM code)**: the flasgger demo
  (`encore_ch3_swagger.py`). Convenient, but the generated spec has no authority.
