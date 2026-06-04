from __future__ import annotations

import argparse
import os
from collections.abc import Callable

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request


def create_app(
    *,
    target_url: str,
    ingest_token: str,
    client_factory: Callable[[], httpx.AsyncClient] | None = None,
) -> FastAPI:
    if not target_url:
        raise ValueError("target_url is required")
    if not ingest_token:
        raise ValueError("ingest_token is required")
    app = FastAPI(title="Talking Boats AIS forwarder")

    def client() -> httpx.AsyncClient:
        if client_factory is not None:
            return client_factory()
        return httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=30.0))

    client_dependency = Depends(client)

    @app.post("/")
    async def forward_ais(
        request: Request,
        http_client: httpx.AsyncClient = client_dependency,
    ) -> dict[str, str]:
        body = await request.body()
        async with http_client:
            response = await http_client.post(
                target_url,
                headers={
                    "Content-Type": request.headers.get("content-type", "application/json"),
                    "X-TalkingBoats-AIS-Ingest-Token": ingest_token,
                },
                content=body,
            )
            response.raise_for_status()
        return {"status": "forwarded"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward local AIS-catcher HTTP JSON to AWS.")
    parser.add_argument("--host", default=os.getenv("TALKINGBOATS_AIS_FORWARDER_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("TALKINGBOATS_AIS_FORWARDER_PORT", "8110")),
    )
    parser.add_argument("--target-url", default=os.getenv("TALKINGBOATS_AIS_HTTP_INGEST_URL"))
    parser.add_argument("--ingest-token", default=os.getenv("TALKINGBOATS_AIS_INGEST_TOKEN"))
    args = parser.parse_args()
    if not args.target_url:
        parser.error("--target-url or TALKINGBOATS_AIS_HTTP_INGEST_URL is required")
    if not args.ingest_token:
        parser.error("--ingest-token or TALKINGBOATS_AIS_INGEST_TOKEN is required")
    uvicorn.run(
        create_app(target_url=args.target_url, ingest_token=args.ingest_token),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
