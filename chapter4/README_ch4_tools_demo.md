# Chapter 4 demo — Tool schemas (the boundary meets a planner), listing_4_3

The newest consumer of a boundary is an **AI planner/agent**. It reads a
"tool": a **name**, a natural-language **description**, and a **JSON Schema**
for the inputs. This script derives Encore's tools **mechanically from the
Chapter 3 OpenAPI contract**, then adds the one layer OpenAPI never forced us
to state: **annotations**.

Unlike the GraphQL and gRPC demos, this one does NOT start a server. It is a
**projection script**: contract in (YAML) → tool catalog out (JSON).

## 1. Install

```bash
pip install -r requirements.txt      # just PyYAML; json is stdlib
```

## 2. Fix the contract path (a gotcha)

The listing hard-codes `../ch03/encore-openapi-v1.1.yaml`, but the contract in
this course lives at `chapter3/encore-openapi-v1.1.yaml`. Point the script at
the real file — either edit the last block, or copy the YAML next to the script
and use its name. If the path is wrong you get `FileNotFoundError`.

## 3. Run

```bash
python listing_4_3_tools.py
```

It writes **encore-tools.json** (all four tools) and prints the
`createReservation` tool. You should see 4 tools:
`listEvents, getEvent, createReservation, getReservation`.

## What it shows (the Chapter 4 points)

1. **Tools are projected, not hand-written.** The name comes from
   `operationId`, the `inputSchema` IS the Chapter 2 JSON Schema, and the
   `description` is the Chapter 3 prose — copied **verbatim**. Nothing about the
   domain is re-authored. Same capability, a new projection.

2. **The description IS the interface.** Read the `createReservation`
   description in the output — the idempotency-key warning, the "retry with the
   SAME key" instruction. A planner conditions its behaviour on exactly those
   words. This is why Chapters 2–3 insisted the description be written with care.

3. **`annotations` is the one layer that had to be ADDED.** OpenAPI never made
   us state: is this read-only? idempotent under what discipline? what is the
   real-world consequence? A human integrator carries that judgment; a planner
   carries only what the schema says. So `createReservation` is annotated
   `readOnly: false`, `idempotent: "per Idempotency-Key"`, `consequence: "takes
   a scarce seat; visible to a human at a door"`. This is what an agent's
   harness uses to decide which calls proceed silently and which need a human's
   yes — the safety architecture of the sequel course, resting on Chapter 3's
   semantics.

## Try this in class: good contract vs. bad contract

The projection is only as good as the contract. Replace the rich
`createReservation` description with a bare `"Creates a reservation."` and
re-run: you get a tool a planner can *invoke* but cannot be *trusted* with — it
no longer knows the retry rule or the consequence. The lesson: **a careful
contract is not documentation politeness; it is the agent's operating manual.**

## Connection to MCP (forward look)

This JSON tool shape is exactly what the Model Context Protocol (MCP) carries.
To make Encore callable by a real agent, you'd wrap these tools in a small MCP
server whose `call_tool` handler translates a tool call into an HTTP request to
your real Encore endpoints (Chapter 2's contract-first service). The schema work
is already done here; MCP adds the discover/invoke protocol on top. (Sequel
course territory.)
