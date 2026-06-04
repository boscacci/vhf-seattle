from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from talkingboats.ais_forwarder import create_app


def test_ais_forwarder_posts_to_aws_with_private_header() -> None:
    forwarded = []

    async def handler(request: httpx.Request) -> httpx.Response:
        forwarded.append(request)
        assert request.headers["X-TalkingBoats-AIS-Ingest-Token"] == "secret-token"
        assert request.content == b'{"ships":[]}'
        return httpx.Response(202, json={"status": "accepted"})

    app = create_app(
        target_url="https://aws.example.test/v1/ais",
        ingest_token="secret-token",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    response = TestClient(app).post(
        "/",
        content=b'{"ships":[]}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "forwarded"}
    assert len(forwarded) == 1
