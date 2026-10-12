"""Feedback is private; public clients only receive sanitized corrected text."""

import asyncio

import httpx

from talkingboats.live_radio_proxy import ProxySettings, create_app


def test_public_proxy_has_no_correction_or_experiment_routes_even_with_spoofed_headers():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(ProxySettings())),
            base_url="https://seattleboatradio.com",
        ) as client:
            for path in [
                "/api/clips/corrections",
                "/api/asr-feedback/status",
                "/api/asr-feedback/runs",
            ]:
                response = await client.get(path, headers={"X-TalkingBoats-Tailnet-Dev": "1"})
                assert response.status_code == 404

    asyncio.run(run())
