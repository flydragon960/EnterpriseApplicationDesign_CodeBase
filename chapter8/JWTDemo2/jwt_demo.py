# Listing 8.2 -- jwt_demo.py: a JWT built by hand, then checked by a library.
# A JWT is just header.payload.signature: two pieces of base64url-encoded
# JSON, signed with the private key from Listing 8.1's idea (RS256 = RSA
# signature over SHA-256). Run: python3 jwt_demo.py
import base64
import json
import time
import jwt                                     # PyJWT, used only to compare
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

def b64url(data: bytes) -> str:
    """base64url without '=' padding -- the JWT encoding. NOT encryption."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def to_json(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

# --- Step 1: write the two JSON documents --------------------------------
header = {"alg": "RS256", "typ": "JWT"}
payload = {"iss": "https://id.encore.example",
           "aud": "https://api.encore.example",
           "sub": "student:kim",
           "scope": "events:read",
           "exp": int(time.time()) + 900}          # valid for 15 minutes
print("Step 1 -- header and payload are plain JSON")
print("   header :", header)
print("   payload:", payload)
print()

# --- Step 2: encode them and sign "header.payload" -----------------------
signing_input = b64url(to_json(header)) + "." + b64url(to_json(payload))
signature = private_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
token = signing_input + "." + b64url(signature)
h, p, s = token.split(".")
print("Step 2 -- encode, sign, and join with dots")
print("   header    :", h)
print("   payload   :", p[:40] + "...")
print("   signature :", s[:40] + "...")
print("   token length:", len(token), "characters, 3 parts")
print()

# --- Step 3: anyone can READ it -- no key needed --------------------------
print("Step 3 -- decoding needs no key (signed, not encrypted)")
print("   payload read back:", json.loads(unb64url(p)))
print()

# --- Step 4: CHECK it by hand with the public key -------------------------
def check_by_hand(tok):
    h, p, s = tok.split(".")
    try:
        public_key.verify(unb64url(s), (h + "." + p).encode(),
                          padding.PKCS1v15(), hashes.SHA256())
        return "VALID"
    except InvalidSignature:
        return "INVALID"

edited = dict(payload, scope="events:read events:admin")
tampered = h + "." + b64url(to_json(edited)) + "." + s
print("Step 4 -- check the signature by hand with the PUBLIC key")
print("   our token                 :", check_by_hand(token))
print("   payload edited, old sig   :", check_by_hand(tampered))
print()

# --- Step 5: a real library agrees with our hand-made token ---------------
public_pem = public_key.public_bytes(serialization.Encoding.PEM,
                                     serialization.PublicFormat.SubjectPublicKeyInfo)
private_pem = private_key.private_bytes(serialization.Encoding.PEM,
                                        serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
claims = jwt.decode(token, public_pem, algorithms=["RS256"],
                    issuer="https://id.encore.example",
                    audience="https://api.encore.example")
library_token = jwt.encode(payload, private_pem, algorithm="RS256")
print("Step 5 -- PyJWT accepts our hand-made token")
print("   jwt.decode -> sub         :", claims["sub"])
print("   jwt.encode, same token?   :", library_token == token)
try:
    jwt.decode(tampered, public_pem, algorithms=["RS256"],
               issuer="https://id.encore.example",
               audience="https://api.encore.example")
except jwt.InvalidTokenError as e:
    print("   tampered token            : REJECTED (", type(e).__name__, ")")
