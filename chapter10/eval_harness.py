# Listing 10.4 -- eval_harness.py: testing the agent-facing surface.
# A conventional test asserts exact outputs. But the newest consumer of
# Encore is a PLANNER (Chapter 4), and the quality that matters is whether
# the tool schema and error messages let a model make the RIGHT DECISION.
# You cannot assert that with ==; you evaluate it against a rubric, over a
# suite of scenarios, and track a SCORE that must not regress.
#
# This harness is model-agnostic: it takes a `judge` function (a call to an
# LLM in production; a deterministic stub here so the demo is reproducible)
# and scores each scenario against explicit criteria. The DISCIPLINE is the
# lesson -- fixed rubric, held-out scenarios, a tracked number -- not the
# particular judge.
import json

SCENARIOS = [
    {
        "name": "sold_out is actionable",
        "tool_response": {"status": 409, "error": "sold_out"},
        "criteria": ["names the reason machine-readably (sold_out)",
                     "tells the agent retry is pointless without new seats"],
    },
    {
        "name": "seatsLeft staleness is disclosed",
        "tool_response": {"seatsLeft": 1,
                          "_description": "point-in-time observation, not a promise"},
        "criteria": ["warns availability may be stale",
                     "does not license a guarantee to the user"],
    },
    {
        "name": "idempotency guidance present",
        "tool_response": {"error": "timeout",
                          "_hint": "retry with the same Idempotency-Key"},
        "criteria": ["instructs same-key retry",
                     "does not suggest a fresh key"],
    },
]

def rubric_judge(tool_response, criteria):
    """Stand-in for an LLM judge. In production this is a prompt to a model:
    'Given this tool response, would an agent satisfy each criterion? Score
    0-1 with a reason.' Here we check deterministically whether the response
    CONTAINS the information each criterion needs -- exactly what a good
    judge rewards -- so the harness shape is real though the judge is stubbed."""
    blob = json.dumps(tool_response).lower()
    scores = []
    for c in criteria:
        present = any(kw in blob for kw in _keywords(c))
        scores.append({"criterion": c, "score": 1.0 if present else 0.0,
                       "reason": "information present" if present
                                 else "information absent"})
    return scores

def _keywords(criterion):
    c = criterion.lower()
    if "sold_out" in c or "pointless" in c: return ["sold_out"]
    if "stale" in c or "guarantee" in c: return ["point-in-time", "not a promise"]
    if "same-key" in c or "fresh key" in c: return ["same idempotency-key"]
    return ["__none__"]

def run(judge=rubric_judge):
    total, earned = 0, 0.0
    print("Agent-surface evaluation:\n")
    for sc in SCENARIOS:
        results = judge(sc["tool_response"], sc["criteria"])
        s = sum(r["score"] for r in results); n = len(results)
        total += n; earned += s
        print(f"  {sc['name']:32} {s:.0f}/{n}")
        for r in results:
            if r["score"] < 1:
                print(f"      MISS: {r['criterion']}")
    print(f"\n  OVERALL: {earned:.0f}/{total} = {earned/total*100:.0f}%")
    print("  (a regression gate: a schema edit that drops this number fails")
    print("   CI exactly as a broken conformance test would)")
    return earned / total

if __name__ == "__main__":
    run()
