# Listing 8.3 -- attacks.py: three forgeries, and the verify() that stops them.
# Each attack succeeds against a verifier that skips one clause, and fails
# against the honest verify() of Listing 8.1. Run: python3 attacks.py
import base64
import datetime
import json
import jwt
import auth

def show(name, attacker_result, honest_fn, token, key=None):
    print(name)
    print("   naive  :", attacker_result)
    try:
        honest_fn(token) if key is None else honest_fn(token, key)
        print("   honest : ACCEPTED  (this would be a bug)")
    except Exception as e:
        print("   honest : REJECTED  (", type(e).__name__, ")")
    print()

# --- Attack A: tamper with the payload, keep the old signature ---
honest = auth.issue("student:kim", ["events:read"])
h, p, s = honest.split(".")
body = json.loads(base64.urlsafe_b64decode(p + "=="))
body["scope"] = "events:read events:admin"
forged = base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=").decode()
tampered = f"{h}.{forged}.{s}"
naive_A = auth.verify_no_verify(tampered)["scope"]   # tutorials' verify_signature=False
show("Attack A -- tampered scope (payload edited, signature stale)",
     f"scope now '{naive_A}'  <- attacker granted self admin",
     auth.verify, tampered)

# --- Attack B: alg=none, a token that declares itself unsigned ---
now = datetime.datetime.now(datetime.timezone.utc)
none_tok = jwt.encode(
    {"sub": "student:kim", "scope": "events:admin", "iss": auth.ISSUER,
     "aud": auth.AUDIENCE, "exp": now + datetime.timedelta(hours=1)},
    key=None, algorithm="none")
naive_B = auth.verify_trusting_header(none_tok)["scope"]  # trusts header alg
show("Attack B -- alg=none (unsigned token, header says 'trust me')",
     f"scope '{naive_B}'  <- forged with NO key at all",
     auth.verify, none_tok)

# --- Attack C: a token for another service (confused deputy) ---
library_tok = jwt.encode(
    {"iss": auth.ISSUER, "aud": "https://api.library.example",
     "sub": "student:kim", "scope": "books:borrow admin",
     "exp": now + datetime.timedelta(hours=1)},
    auth.PRIVATE_PEM, algorithm="RS256")
naive_C = jwt.decode(library_tok, auth.PUBLIC_PEM, algorithms=["RS256"],
                     issuer=auth.ISSUER,
                     options={"verify_aud": False})["aud"]   # aud unchecked
show("Attack C -- wrong audience (token minted for the library)",
     f"accepted a token whose aud is '{naive_C}'  <- confused deputy",
     auth.verify, library_tok)

print("Every attack defeated the verifier that skipped ONE clause,")
print("and none defeated verify(): signature + alg + iss + aud + exp.")
