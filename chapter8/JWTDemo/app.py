import datetime
import jwt

# A secret key used for signing (keep this secure in production!)
SECRET_KEY = "my_super_secret_key_change_in_production"
ALGORITHM = "HS256"


def create_token(user_id: int, username: str) -> str:
  """Generates a JWT containing user information and an expiration time."""
  payload = {
      "sub": user_id,  # Subject (User ID)
      "username": username,
      "iat": datetime.datetime.now(
          datetime.timezone.utc
      ),  # Issued at timestamp
      "exp": datetime.datetime.now(datetime.timezone.utc)
      + datetime.timedelta(minutes=15),  # Expires in 15 minutes
  }

  # Encode the payload into a JWT string using the secret key
  token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
  return token


def verify_token(token: str):
  """Verifies the JWT signature and checks if it has expired."""
  try:
    # Decode automatically checks the signature and expiration ('exp')
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload
  except jwt.ExpiredSignatureError:
    print("❌ Verification Failed: The token has expired.")
    return None
  except jwt.InvalidTokenError:
    print("❌ Verification Failed: The token is invalid or has been tampered with.")
    return None


# --- Demonstration ---
if __name__ == "__main__":
  print("--- 1. Generating JWT ---")
  sample_token = create_token(user_id=101, username="Yuhong")
  print(f"Generated Token:\n{sample_token}\n")

  print("--- 2. Verifying a Valid Token ---")
  decoded_data = verify_token(sample_token)
  if decoded_data:
    print("✅ Token successfully verified!")
    print(f"User ID: {decoded_data['sub']}")
    print(f"Username: {decoded_data['username']}")
    print(
        "Issued At:",
        datetime.datetime.fromtimestamp(
            decoded_data["iat"], tz=datetime.timezone.utc
        ),
    )
    print(
        "Expires At:",
        datetime.datetime.fromtimestamp(
            decoded_data["exp"], tz=datetime.timezone.utc
        ),
    )
    print()

  print("--- 3. Simulating a Tampered Token ---")
  # Modify the last character of the token string to break the signature
  tampered_token = sample_token[:-5] + "ABCDE"
  verify_token(tampered_token)