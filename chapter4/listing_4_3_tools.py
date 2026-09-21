# Listing 4.3 -- Projecting the OpenAPI contract into tool schemas.
# The newest consumer of a boundary is a planner. It reads a "tool": a name,
# a natural-language description, and a JSON Schema for the inputs. This
# script derives Encore's tools MECHANICALLY from the Chapter 3 contract --
# then adds the one layer OpenAPI never forced us to state.
# Run: python3 listing_4_3_tools.py
import json
import yaml

# The layer a planner needs that a human-facing contract left implicit:
# may this tool be called without asking? repeated without harm?
ANNOTATIONS = {
    "listEvents":        {"readOnly": True,  "idempotent": True},
    "getEvent":          {"readOnly": True,  "idempotent": True},
    "getReservation":    {"readOnly": True,  "idempotent": True},
    "createReservation": {"readOnly": False, "idempotent": "per Idempotency-Key",
                          "consequence": "takes a scarce seat; visible to a human at a door"},
}

def tools_from_openapi(path):
    spec = yaml.safe_load(open(path))
    tools = []
    for route, methods in spec["paths"].items():
        for method, op in methods.items():
            inputs, required = {}, []
            for p in op.get("parameters", []):
                inputs[p["name"]] = {**p["schema"],
                                     "description": p.get("description", "").strip()}
                if p.get("required"):
                    required.append(p["name"])
            tools.append({
                "name": op["operationId"],
                "description": op.get("description", op.get("summary", "")).strip(),
                "inputSchema": {"type": "object",
                                "properties": inputs, "required": required},
                "annotations": ANNOTATIONS.get(op["operationId"], {}),
            })
    return tools

if __name__ == "__main__":
    tools = tools_from_openapi("../ch03/encore-openapi-v1.1.yaml")
    out = json.dumps(tools, indent=2)
    open("encore-tools.json", "w").write(out)
    reserve = next(t for t in tools if t["name"] == "createReservation")
    print(json.dumps(reserve, indent=2))
