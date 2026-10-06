# Encore — Chapter 3 demo with Swagger UI

A minimal, runnable Encore service that demonstrates Chapter 3's two core
ideas — **idempotency keys** and a **coded error model** — with an
**interactive Swagger UI** (from the still-current Swagger/OpenAPI ecosystem).

## Run

```bash
pip install flask flasgger
python encore_ch3_swagger.py
```

Then open **http://localhost:3000/apidocs** in a browser.

## What to show students (in the Swagger UI, click "Try it out")

1. `POST /events/ev_101/reservations` with header `Idempotency-Key: kim-1`
   → **201**, a new reservation `res_1`.
2. Send the **same request again** (same `kim-1`)
   → **201 with `"replayed": true`** and the **same** `res_1`.
   *(Chapter 3: a repeated attempt has one outcome — no double booking.)*
3. Use a new key (`ana-1`), then another (`raj-1`) until seats run out
   → **409 `{"error": "sold_out"}`**.
   *(Chapter 3: errors are contract too — a stable, machine-readable code.)*
4. Omit the header entirely → **422 `idempotency_key_required`**.

## Swagger / OpenAPI ecosystem (still current, 2025)

- **OpenAPI** = the spec (the contract format).
- **Swagger** = the tooling around it. Here, `flasgger` serves:
  - **Swagger UI** at `/apidocs` — interactive, always-current docs.
  - the auto-generated **OpenAPI spec** at `/apispec_1.json`.
- Related tools you can mention: **Swagger Editor** (edit/validate specs),
  **Swagger Codegen / OpenAPI Generator** (generate client/server code),
  **Redoc** (polished reference docs).

## A note on where this belongs

The Swagger/OpenAPI *tooling* is a **Chapter 2** topic (the contract). This
demo earns its place in **Chapter 3** by using Swagger UI as an interactive
stage for Chapter 3's semantics: idempotent retries and coded errors.
