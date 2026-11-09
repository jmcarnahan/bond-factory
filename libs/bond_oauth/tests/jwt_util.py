"""Hand-built id_tokens for the identity tests (unsigned: the code under test never checks signatures)."""

import base64
import json

from bond_oauth import GoogleOAuth, MicrosoftOAuth, TokenSet

NOW = 1_800_000_000.0
TID = "11111111-2222-4333-8444-555555555555"
OID = "99999999-aaaa-4bbb-8ccc-dddddddddddd"
CLIENT = "client-1"


def b64(data) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def make_jwt(claims, header=None) -> str:
    return f"{b64(header or {'alg': 'RS256', 'typ': 'JWT'})}.{b64(claims)}.sig"


def token_set(claims=None, *, header=None, raw_token=None, **raw) -> TokenSet:
    token = raw_token if raw_token is not None else make_jwt(claims, header)
    return TokenSet(access_token="acc", raw={"id_token": token, **raw})


def google_claims(**over):
    claims = {"iss": "https://accounts.google.com", "aud": CLIENT, "sub": "g-123", "email": "ANN@example.com ",
              "email_verified": True, "name": "Ann", "exp": NOW + 600, "nonce": "n1", "hd": "example.com"}
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def microsoft_claims(**over):
    claims = {"iss": f"https://login.microsoftonline.com/{TID}/v2.0", "aud": CLIENT, "tid": TID, "oid": OID,
              "sub": "pairwise", "preferred_username": "ann@example.org", "name": "Ann", "exp": NOW + 600,
              "nonce": "n1"}
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def google(http=None):
    import httpx
    return GoogleOAuth("cid", "sec", http or httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))


def microsoft(pinned=TID):
    import httpx
    return MicrosoftOAuth("cid", "sec", tenant=pinned or "common", pinned_tenant=pinned,
                          http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
