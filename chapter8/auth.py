# Listing 8.1 -- auth.py: issuing and verifying tokens, and the two ways
# verification is done wrong. A token is a signed claim; the security is
# entirely in HOW you check the signature, not in having one.
import datetime
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# An identity provider owns a PRIVATE key and signs tokens with it.
# Everyone else holds the PUBLIC key and only VERIFIES. Encore never
# sees the private key -- it cannot mint tokens, only check them.
# The keys are generated once and cached on disk, because the issuer
# and every verifier must share the SAME public key -- distributing it
# (here, a shared file; in production, a published JWKS endpoint) is a
# real part of the design, not an afterthought.
import os
_priv_path, _pub_path = "/tmp/encore_priv.pem", "/tmp/encore_pub.pem"
if os.path.exists(_priv_path):
    PRIVATE_PEM = open(_priv_path, "rb").read()
    PUBLIC_PEM = open(_pub_path, "rb").read()
else:
    _key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    PRIVATE_PEM = _key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    PUBLIC_PEM = _key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)
    open(_priv_path, "wb").write(PRIVATE_PEM)
    open(_pub_path, "wb").write(PUBLIC_PEM)

ISSUER = "https://id.encore.example"
AUDIENCE = "https://api.encore.example"

def issue(subject, scopes, ttl_seconds=900, actor=None):
    """The identity provider mints a token. Note what is IN it: who
    (sub), what they may do (scope), who it's for (aud), who said so
    (iss), and when it dies (exp). All signed."""
    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": subject,
        "scope": " ".join(scopes),
        "iat": now, "exp": now + datetime.timedelta(seconds=ttl_seconds),
    }
    if actor:                       # delegation: "X acting for Y" (Section 8.5)
        claims["act"] = {"sub": actor}
    return jwt.encode(claims, PRIVATE_PEM, algorithm="RS256")

# ---- the RIGHT way ----
def verify(token):
    """Verify signature AND issuer AND audience AND expiry, and pin the
    algorithm. Every clause here is a vulnerability if omitted."""
    return jwt.decode(
        token, PUBLIC_PEM,
        algorithms=["RS256"],          # PIN it -- see verify_wrong_alg
        issuer=ISSUER,
        audience=AUDIENCE,             # CHECK it -- see the confused-deputy demo
        options={"require": ["exp", "iss", "aud", "sub"]})

# ---- the WRONG ways, kept so the attacks can be demonstrated ----
def verify_no_verify(token):
    """The one-liner that ships in a hundred tutorials."""
    return jwt.decode(token, options={"verify_signature": False})

def verify_trusting_header(token, key=""):
    """Trusts the algorithm the TOKEN declares in its own header -- the
    root of the 'alg=none' and RS256->HS256 confusion attacks. A token
    should never be allowed to choose how it is verified."""
    header = jwt.get_unverified_header(token)
    opts = {}
    if header["alg"] == "none":
        opts = {"verify_signature": False}      # what "none" means, fatally
    return jwt.decode(token, key, algorithms=[header["alg"]],
                      audience=AUDIENCE, issuer=ISSUER, options=opts)

def has_scope(claims, required):
    return required in claims.get("scope", "").split()
