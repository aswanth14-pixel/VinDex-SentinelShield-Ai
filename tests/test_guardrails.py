import json

import pytest
from pydantic import ValidationError

from packages.core.schemas import (
    ContradictionAnalysis,
    DisputeEvaluationResult,
    ExtractedPODEvidence,
    RazorpayContestPayload,
    RazorpayDisputeEntity,
    RazorpayWebhookPayload,
)


class TestRazorpayDisputeEntity:
    def test_serialize(self):
        entity = RazorpayDisputeEntity(
            id="disp_J1234567890",
            payment_id="pay_J1234567890",
            amount=250000,
            status="open",
            reason_code="chargeback",
            respond_by=1719820800,
            created_at=1719734400,
        )
        data = entity.model_dump()
        assert data["id"] == "disp_J1234567890"
        assert data["currency"] == "INR"

    def test_deserialize(self):
        json_str = '{"id":"disp_J1","payment_id":"pay_J1","amount":100000,"currency":"INR","status":"open","reason_code":"fraud","respond_by":1719820800,"created_at":1719734400}'
        entity = RazorpayDisputeEntity.model_validate_json(json_str)
        assert entity.id == "disp_J1"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            RazorpayDisputeEntity(id="disp_J1")


class TestRazorpayWebhookPayload:
    def test_serialize(self):
        payload = RazorpayWebhookPayload(
            entity="event",
            account_id="acc_123",
            event="payment.dispute.created",
            contains=["dispute"],
            payload={
                "dispute": {
                    "entity": RazorpayDisputeEntity(
                        id="disp_J1",
                        payment_id="pay_J1",
                        amount=50000,
                        status="open",
                        reason_code="chargeback",
                        respond_by=1719820800,
                        created_at=1719734400,
                    )
                }
            },
        )
        data = payload.model_dump()
        assert data["event"] == "payment.dispute.created"

    def test_roundtrip(self):
        payload = RazorpayWebhookPayload(
            entity="event",
            account_id="acc_123",
            event="payment.dispute.created",
            contains=["dispute"],
            payload={
                "dispute": {
                    "entity": RazorpayDisputeEntity(
                        id="disp_J1",
                        payment_id="pay_J1",
                        amount=50000,
                        status="open",
                        reason_code="chargeback",
                        respond_by=1719820800,
                        created_at=1719734400,
                    )
                }
            },
        )
        json_str = payload.model_dump_json()
        restored = RazorpayWebhookPayload.model_validate_json(json_str)
        assert restored.event == payload.event


class TestExtractedPODEvidence:
    def test_serialize(self):
        evidence = ExtractedPODEvidence(
            awb_number="AWB123456789",
            courier_name="Delhivery",
            recipient_name="Rahul Sharma",
            delivery_address="42 MG Road, Bangalore 560001",
            delivery_pincode="560001",
            delivery_timestamp="2024-06-30T14:30:00Z",
            signature_present=True,
            signature_type="handwritten",
            confidence_score=0.95,
            extraction_notes="Clear scan",
        )
        data = evidence.model_dump()
        assert data["confidence_score"] == 0.95

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ExtractedPODEvidence(
                awb_number="AWB1",
                courier_name="Delhivery",
                delivery_address="42 MG Road",
                signature_present=True,
                signature_type="stamp",
                confidence_score=1.5,
            )

    def test_optional_fields(self):
        evidence = ExtractedPODEvidence(
            awb_number="AWB1",
            courier_name="Delhivery",
            delivery_address="42 MG Road",
            signature_present=False,
            signature_type="missing",
            confidence_score=0.3,
        )
        assert evidence.recipient_name is None
        assert evidence.delivery_pincode is None


class TestContradictionAnalysis:
    def test_serialize(self):
        analysis = ContradictionAnalysis(
            address_match=True,
            address_similarity_score=0.92,
            pincode_match=True,
            recipient_match=True,
            detected_contradictions=[],
            is_adversarial=False,
        )
        data = analysis.model_dump()
        assert data["is_adversarial"] is False

    def test_adversarial_detected(self):
        analysis = ContradictionAnalysis(
            address_match=False,
            address_similarity_score=0.35,
            pincode_match=False,
            recipient_match=False,
            detected_contradictions=["Address mismatch", "Pincode mismatch"],
            is_adversarial=True,
        )
        assert len(analysis.detected_contradictions) == 2


class TestDisputeEvaluationResult:
    def test_serialize(self):
        result = DisputeEvaluationResult(
            dispute_id="disp_J1",
            win_probability=0.78,
            recommended_action="AUTO_SUBMIT",
            reasoning=["Strong evidence", "No contradictions"],
            evidence_completeness_score=0.95,
            projected_net_recovery=237500,
        )
        data = result.model_dump()
        assert data["recommended_action"] == "AUTO_SUBMIT"

    def test_win_probability_bounds(self):
        with pytest.raises(ValidationError):
            DisputeEvaluationResult(
                dispute_id="disp_J1",
                win_probability=1.5,
                recommended_action="AUTO_SUBMIT",
                reasoning=[],
                evidence_completeness_score=0.9,
                projected_net_recovery=100000,
            )


class TestRazorpayContestPayload:
    def test_serialize(self):
        payload = RazorpayContestPayload(
            amount=250000,
            summary="Dispute contested with valid POD evidence",
            shipping_proof=["doc_abc123"],
            billing_proof=["doc_def456"],
        )
        data = payload.model_dump()
        assert data["action"] == "submit"
        assert len(data["shipping_proof"]) == 1

    def test_summary_max_length(self):
        with pytest.raises(ValidationError):
            RazorpayContestPayload(
                amount=100000,
                summary="x" * 1001,
            )

    def test_optional_fields_default(self):
        payload = RazorpayContestPayload(amount=100000, summary="Test")
        assert payload.shipping_proof is None
        assert payload.billing_proof is None
        assert payload.customer_communication is None
        assert payload.proof_of_service is None
        assert payload.others is None

    def test_full_roundtrip(self):
        payload = RazorpayContestPayload(
            amount=250000,
            summary="Complete evidence package",
            shipping_proof=["doc_1"],
            billing_proof=["doc_2"],
            customer_communication=["doc_3"],
            proof_of_service=["doc_4"],
            others=["doc_5"],
        )
        json_str = payload.model_dump_json()
        restored = RazorpayContestPayload.model_validate_json(json_str)
        assert restored.amount == 250000
        assert len(restored.others) == 1
