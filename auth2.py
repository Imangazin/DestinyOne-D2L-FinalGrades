import os
import time
import uuid
import requests
import jwt  # pip install pyjwt cryptography
from dotenv import load_dotenv

# =========================
# CONFIG
# =========================
load_dotenv()
BRIGHTSPACE_BASE_URL = os.getenv("BRIGHTSPACE_BASE_URL")
CLIENT_ID = os.getenv("CLIENT_ID")
KID = os.getenv("KID")
SCOPES = os.getenv("SCOPES")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_FILE = os.path.join(BASE_DIR, "private.key")

with open(PRIVATE_KEY_FILE, "r") as f:
    PRIVATE_KEY_PEM = f.read()

TOKEN_URL = "https://auth.brightspace.com/core/connect/token"


def build_client_assertion() -> str:
    now = int(time.time())

    payload = {
        "iss": CLIENT_ID,
        "sub": CLIENT_ID,
        "aud": TOKEN_URL,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 300,  # 5 minutes
    }

    headers = {
        "kid": KID,
        "typ": "JWT",
        "alg": "RS256",
    }

    token = jwt.encode(
        payload,
        PRIVATE_KEY_PEM,
        algorithm="RS256",
        headers=headers,
    )
    return token


def get_access_token() -> dict:
    client_assertion = build_client_assertion()

    # Debug: decode JWT without verification
    decoded = jwt.decode(
        client_assertion,
        options={"verify_signature": False, "verify_aud": False},
        algorithms=["RS256"],
    )
    print("Decoded JWT payload:", decoded)

    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "scope": SCOPES,
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_assertion,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    response = requests.post(
        TOKEN_URL,
        data=data,
        headers=headers,
        timeout=30,
        allow_redirects=False,
    )
    print("Status:", response.status_code)
    print("Headers:", dict(response.headers))
    print("Response:", response.text)
    response.raise_for_status()
    return response.json()


def api_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }