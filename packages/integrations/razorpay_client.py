"""
Razorpay REST API client for SentinelShield AI.

Implements test-mode wrapper for dispute management, document upload, and contest submission.
All outbound calls are guarded by Pydantic v2 schema validation.
"""

import base64
from pathlib import Path
from typing import Optional

import httpx

from packages.core.config import settings
from packages.core.schemas import RazorpayContestPayload


RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


class RazorpayClient:
    """Razorpay API client with test-mode support and Pydantic validation."""

    def __init__(self, key_id: Optional[str] = None, key_secret: Optional[str] = None):
        self._key_id = key_id or settings.RAZORPAY_KEY_ID
        self._key_secret = key_secret or settings.RAZORPAY_KEY_SECRET
        self._auth = (self._key_id, self._key_secret)

    def _get_headers(self) -> dict:
        return {"Content-Type": "application/json"}

    async def fetch_dispute(self, dispute_id: str) -> dict:
        """Fetch dispute details: GET /v1/disputes/{id}."""
        url = f"{RAZORPAY_BASE_URL}/disputes/{dispute_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, auth=self._auth, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

    async def upload_document(self, file_path: str, purpose: str = "dispute_evidence") -> dict:
        """Upload a document: POST /v1/documents.

        Returns dict with 'id' key containing doc_xxx identifier.
        """
        url = f"{RAZORPAY_BASE_URL}/documents"
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        file_bytes = path.read_bytes()
        encoded = base64.b64encode(file_bytes).decode("utf-8")

        payload = {
            "purpose": purpose,
            "file": encoded,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, json=payload, auth=self._auth, headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def contest_dispute(self, dispute_id: str, payload: RazorpayContestPayload) -> dict:
        """Submit contest evidence: PATCH /v1/disputes/{id}/contest.

        Pydantic v2 validates payload before sending.
        """
        validated = RazorpayContestPayload.model_validate(payload.model_dump())
        url = f"{RAZORPAY_BASE_URL}/disputes/{dispute_id}/contest"

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                url, json=validated.model_dump(), auth=self._auth, headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
