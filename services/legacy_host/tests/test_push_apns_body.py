"""The host builds a PushMessage with badge and interruption level and it reaches the APNs body.

The legacy host has no push sender of its own, so this proves the module from the host's environment and install."""

import json

import httpx
from bond_push_py import ApnsSender, PushMessage, PushResult
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def test_badge_and_interruption_level_reach_the_apns_body():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    seen: list[httpx.Request] = []

    def apple(request):
        seen.append(request)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(apple))
    sender = ApnsSender(pem, "KEYID12345", "TEAMID6789", client=client)
    message = PushMessage(token="ab" * 32, environment="sandbox", topic="com.example.legacy", title="Due", body="Now",
                          badge=2, interruption_level="time-sensitive", data={"task_id": "t1"})
    assert sender.send([message]) == [PushResult(ok=True)]
    (request,) = seen
    body = json.loads(request.content)
    assert body["aps"]["badge"] == 2
    assert body["aps"]["interruption-level"] == "time-sensitive"
    assert body["task_id"] == "t1"
