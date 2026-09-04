"""
Razorpay Webhook Listener with HMAC-SHA256 Signature Validation.

All webhook signatures (X-Razorpay-Signature) must be cryptographically
validated before processing.
"""

import asyncio
import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from packages.core.config import settings


router = APIRouter()


def verify_razorpay_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from Razorpay webhook.

    Args:
        body: Raw request body bytes.
        signature: X-Razorpay-Signature header value.
        secret: Webhook secret for HMAC computation.

    Returns:
        True if signature is valid, False otherwise.
    """
    if not signature or not secret:
        return False

    computed = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


async def process_dispute_event(payload: dict):
    """Background task to process verified dispute events."""
    from packages.agents.orchestrator import Orchestrator

    event = payload.get("event", "")
    if event != "payment.dispute.created":
        return

    contains = payload.get("contains", [])
    if "dispute" not in contains:
        return

    payload_data = payload.get("payload", {})
    dispute_entity = payload_data.get("dispute", {}).get("entity", {})

    if not dispute_entity:
        return

    dispute_id = dispute_entity.get("id", "")
    payment_id = dispute_entity.get("payment_id", "")
    amount = dispute_entity.get("amount", 0)
    reason_code = dispute_entity.get("reason_code", "")

    if not dispute_id or not payment_id:
        return

    orch = Orchestrator()
    await orch.process_dispute(
        dispute_id=dispute_id,
        payment_id=payment_id,
        amount=amount,
        reason_code=reason_code,
    )


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: Optional[str] = Header(None),
):
    """Razorpay webhook endpoint with HMAC-SHA256 verification.

    - Returns HTTP 400 if signature verification fails.
    - Returns HTTP 200 immediately upon verification.
    - Dispatches background task for dispute processing.
    """
    body = await request.body()

    if not verify_razorpay_signature(
        body=body,
        signature=x_razorpay_signature or "",
        secret=settings.RAZORPAY_WEBHOOK_SECRET,
    ):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    background_tasks.add_task(process_dispute_event, payload)

    return {"status": "ok"}
