import asyncio
import os
import uuid

import httpx
import pytest


@pytest.mark.skipif(
    not os.getenv("N8N_INTEGRATION_WEBHOOK_URL") or not os.getenv("N8N_WEBHOOK_SECRET"),
    reason="Set N8N_INTEGRATION_WEBHOOK_URL and N8N_WEBHOOK_SECRET for local n8n testing",
)
def test_optional_real_n8n_webhook():
    async def send() -> None:
        event_id = f"n8n-local-{uuid.uuid4().hex}"
        headers = {"Idempotency-Key": event_id}
        headers["X-Webhook-Secret"] = os.environ["N8N_WEBHOOK_SECRET"]
        payload = {
            "schema_version": "1.0",
            "event_id": event_id,
            "source": "simulation",
            "type": "fall_collapse",
            "timestamp": "2026-10-16T06:50:00Z",
        }
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                os.environ["N8N_INTEGRATION_WEBHOOK_URL"],
                json=payload,
                headers=headers,
            )
        assert 200 <= response.status_code < 300, f"n8n returned HTTP {response.status_code}"

    asyncio.run(send())
