"""
Security tests for webhook signature validation.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes.webhooks import verify_razorpay_signature


TEST_SECRET = "test_webhook_secret_12345"


class TestHMACVerification:
    def test_valid_signature(self):
        body = b'{"event":"payment.dispute.created"}'
        signature = hmac.new(
            TEST_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        assert verify_razorpay_signature(body, signature, TEST_SECRET) is True

    def test_invalid_signature(self):
        body = b'{"event":"payment.dispute.created"}'
        assert verify_razorpay_signature(body, "invalid_signature", TEST_SECRET) is False

    def test_tampered_body(self):
        body = b'{"event":"payment.dispute.created"}'
        signature = hmac.new(
            TEST_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        tampered_body = b'{"event":"payment.dispute.refunded"}'
        assert verify_razorpay_signature(tampered_body, signature, TEST_SECRET) is False

    def test_empty_signature(self):
        body = b'{"event":"payment.dispute.created"}'
        assert verify_razorpay_signature(body, "", TEST_SECRET) is False

    def test_empty_secret(self):
        body = b'{"event":"payment.dispute.created"}'
        assert verify_razorpay_signature(body, "some_signature", "") is False

    def test_both_empty(self):
        body = b'{}'
        assert verify_razorpay_signature(body, "", "") is False

    def test_empty_body(self):
        signature = hmac.new(
            TEST_SECRET.encode("utf-8"),
            b"",
            hashlib.sha256,
        ).hexdigest()
        assert verify_razorpay_signature(b"", signature, TEST_SECRET) is True


class TestWebhookEndpoint:
    def setup_method(self):
        self.client = TestClient(app)
        self.original_secret = None

    def _set_secret(self, secret: str):
        from packages.core.config import settings
        self.original_secret = settings.RAZORPAY_WEBHOOK_SECRET
        settings.RAZORPAY_WEBHOOK_SECRET = secret

    def _restore_secret(self):
        if self.original_secret is not None:
            from packages.core.config import settings
            settings.RAZORPAY_WEBHOOK_SECRET = self.original_secret

    def test_invalid_signature_returns_400(self):
        self._set_secret(TEST_SECRET)
        try:
            response = self.client.post(
                "/api/v1/webhooks/razorpay",
                content=b'{"event":"payment.dispute.created"}',
                headers={"X-Razorpay-Signature": "invalid_sig"},
            )
            assert response.status_code == 400
            assert "Invalid webhook signature" in response.json()["detail"]
        finally:
            self._restore_secret()

    def test_valid_signature_returns_200(self):
        self._set_secret(TEST_SECRET)
        try:
            body = json.dumps({
                "entity": "event",
                "account_id": "acc_123",
                "event": "payment.dispute.created",
                "contains": ["dispute"],
                "payload": {},
            }).encode("utf-8")

            signature = hmac.new(
                TEST_SECRET.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()

            response = self.client.post(
                "/api/v1/webhooks/razorpay",
                content=body,
                headers={
                    "X-Razorpay-Signature": signature,
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
        finally:
            self._restore_secret()

    def test_missing_signature_returns_400(self):
        self._set_secret(TEST_SECRET)
        try:
            response = self.client.post(
                "/api/v1/webhooks/razorpay",
                content=b'{"event":"payment.dispute.created"}',
            )
            assert response.status_code == 400
        finally:
            self._restore_secret()

    def test_invalid_json_returns_400(self):
        self._set_secret(TEST_SECRET)
        try:
            body = b'not json'
            signature = hmac.new(
                TEST_SECRET.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()

            response = self.client.post(
                "/api/v1/webhooks/razorpay",
                content=body,
                headers={"X-Razorpay-Signature": signature},
            )
            assert response.status_code == 400
        finally:
            self._restore_secret()


class TestAPIEndpoints:
    def setup_method(self):
        self.client = TestClient(app)

    def test_root(self):
        response = self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "SentinelShield AI"

    def test_health(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_list_disputes(self):
        response = self.client.get("/api/v1/disputes")
        assert response.status_code == 200
        assert "disputes" in response.json()

    def test_dispute_stats(self):
        response = self.client.get("/api/v1/disputes/stats/summary")
        assert response.status_code == 200
        assert "total_disputes" in response.json()

    def test_get_nonexistent_dispute(self):
        response = self.client.get("/api/v1/disputes/disp_NONEXISTENT")
        assert response.status_code == 404
