# Listing 8.1 -- keys_demo.py: the private-key / public-key idea, on its own.
# No web, no tokens yet. One key pair, one message, and four questions:
# can the owner sign? can anyone check? does tampering show? can a
# public-key holder forge? Run: python3 keys_demo.py
import base64
import hashlib
import hmac
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

def short(b):                                   # print long bytes compactly
    s = base64.b64encode(b).decode()
    return f"{s[:24]}...({len(b)} bytes)"

def check(public_key, message, signature):
    """Anyone holding the PUBLIC key can run this check."""
    try:
        public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
        return "VALID"
    except InvalidSignature:
        return "INVALID"

# --- Step 1: the issuer makes a key pair --------------------------------
issuer_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
issuer_public = issuer_private.public_key()
pem = issuer_public.public_bytes(serialization.Encoding.PEM,
                                 serialization.PublicFormat.SubjectPublicKeyInfo)
print("Step 1 -- the issuer creates a key pair")
print("   private key : kept secret by the issuer, never shared")
print("   public key  : safe to publish, starts with", pem.decode().splitlines()[0])
print()

# --- Step 2: sign with the PRIVATE key ----------------------------------
message = b"student:kim may read events"
signature = issuer_private.sign(message, padding.PKCS1v15(), hashes.SHA256())
print("Step 2 -- the issuer signs a message with its PRIVATE key")
print("   message   :", message.decode())
print("   signature :", short(signature))
print()

# --- Step 3: anyone checks with the PUBLIC key --------------------------
print("Step 3 -- anyone checks the signature with the PUBLIC key")
print("   original message           :", check(issuer_public, message, signature))
print()

# --- Step 4: any change breaks the signature ----------------------------
changed = b"student:kim may ADMIN events"
bad_sig = bytes([signature[0] ^ 1]) + signature[1:]      # flip one bit
print("Step 4 -- change anything and the check fails")
print("   message edited             :", check(issuer_public, changed, signature))
print("   signature edited (1 bit)   :", check(issuer_public, message, bad_sig))
print()

# --- Step 5: only the private key can produce a valid signature ---------
attacker_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
fake_sig = attacker_private.sign(changed, padding.PKCS1v15(), hashes.SHA256())
print("Step 5 -- without the issuer's private key, you cannot forge")
print("   attacker signs with own key:", check(issuer_public, changed, fake_sig))
print("   public key can sign?       :", hasattr(issuer_public, "sign"))
print()

# --- Contrast: a SHARED secret (HMAC, used by HS256) --------------------
secret = b"one-secret-both-sides-know"
tag = hmac.new(secret, message, hashlib.sha256).digest()
verifier_tag = hmac.new(secret, message, hashlib.sha256).digest()
minted = hmac.new(secret, changed, hashlib.sha256).digest()
print("Contrast -- a shared secret (HMAC): the same key signs AND checks")
print("   verifier checks the tag    :", "VALID" if hmac.compare_digest(tag, verifier_tag) else "INVALID")
print("   ...but the verifier can also create a tag for ANY message:")
print("   tag for the edited message :", short(minted))
print("   => whoever can check can also forge. A key pair separates the two.")
