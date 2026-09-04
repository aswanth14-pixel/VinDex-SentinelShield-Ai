"""
Integration tests for dispute lifecycle, win scoring, and contest execution.
"""

import json
from pathlib import Path

import pytest

from packages.agents.contest_executor import ContestExecutor
from packages.agents.orchestrator import Orchestrator
from packages.agents.win_scorer import (
    AUTO_SUBMIT_WIN_THRESHOLD,
    ABANDON_WIN_THRESHOLD,
    AUTO_SUBMIT_MAX_AMOUNT_PAISE,
    compute_win_probability,
    determine_action,
    evaluate,
)
from packages.core.schemas import DisputeEvaluationResult


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "synthetic_ground_truth.json"


@pytest.fixture
def ground_truth():
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


class TestWinProbability:
    def test_retrieval_high_scores(self):
        p = compute_win_probability(
            reason_code="retrieval",
            address_similarity_score=0.95,
            confidence_score=0.90,
            signature_present=True,
        )
        assert p > 0.70

    def test_fraud_low_scores(self):
        p = compute_win_probability(
            reason_code="fraud",
            address_similarity_score=0.30,
            confidence_score=0.40,
            signature_present=False,
        )
        assert p < 0.20

    def test_chargeback_moderate(self):
        p = compute_win_probability(
            reason_code="chargeback",
            address_similarity_score=0.70,
            confidence_score=0.80,
            signature_present=True,
        )
        assert 0.30 < p < 0.60

    def test_bounds(self):
        p_max = compute_win_probability("retrieval", 1.0, 1.0, True)
        p_min = compute_win_probability("fraud", 0.0, 0.0, False)
        assert 0.0 <= p_min <= p_max <= 1.0


class TestDecisionThresholds:
    def test_auto_submit(self):
        action = determine_action(
            win_probability=0.75,
            amount_paise=100000,
            contradictions_count=0,
        )
        assert action == "AUTO_SUBMIT"

    def test_auto_submit_rejects_high_amount(self):
        action = determine_action(
            win_probability=0.80,
            amount_paise=3000000,
            contradictions_count=0,
        )
        assert action == "ESCALATE_HUMAN"

    def test_auto_submit_rejects_contradictions(self):
        action = determine_action(
            win_probability=0.80,
            amount_paise=100000,
            contradictions_count=1,
        )
        assert action == "ESCALATE_HUMAN"

    def test_escalate_moderate_win(self):
        action = determine_action(
            win_probability=0.50,
            amount_paise=100000,
            contradictions_count=0,
        )
        assert action == "ESCALATE_HUMAN"

    def test_abandon_low_win(self):
        action = determine_action(
            win_probability=0.25,
            amount_paise=100000,
            contradictions_count=0,
        )
        assert action == "ABANDON"


class TestEvaluate:
    def test_clean_case_auto_submit(self):
        result = evaluate(
            dispute_id="disp_TEST001",
            reason_code="retrieval",
            amount_paise=200000,
            address_similarity_score=0.95,
            confidence_score=0.90,
            signature_present=True,
            contradictions_count=0,
            detected_contradictions=[],
        )
        assert isinstance(result, DisputeEvaluationResult)
        assert result.recommended_action == "AUTO_SUBMIT"
        assert result.win_probability >= AUTO_SUBMIT_WIN_THRESHOLD

    def test_address_mismatch_escalation(self):
        result = evaluate(
            dispute_id="disp_TEST002",
            reason_code="chargeback",
            amount_paise=200000,
            address_similarity_score=0.50,
            confidence_score=0.85,
            signature_present=True,
            contradictions_count=2,
            detected_contradictions=["Address mismatch", "Pincode mismatch"],
        )
        assert result.recommended_action == "ESCALATE_HUMAN"

    def test_fraud_abandonment(self):
        result = evaluate(
            dispute_id="disp_TEST003",
            reason_code="fraud",
            amount_paise=500000,
            address_similarity_score=0.20,
            confidence_score=0.30,
            signature_present=False,
            contradictions_count=3,
            detected_contradictions=["Address mismatch", "Pincode mismatch", "Recipient mismatch"],
        )
        assert result.recommended_action == "ABANDON"

    def test_projected_recovery(self):
        result_auto = evaluate(
            dispute_id="disp_TEST004",
            reason_code="retrieval",
            amount_paise=100000,
            address_similarity_score=0.95,
            confidence_score=0.90,
            signature_present=True,
            contradictions_count=0,
            detected_contradictions=[],
        )
        assert result_auto.projected_net_recovery == 100000

        result_abandon = evaluate(
            dispute_id="disp_TEST005",
            reason_code="fraud",
            amount_paise=100000,
            address_similarity_score=0.10,
            confidence_score=0.10,
            signature_present=False,
            contradictions_count=0,
            detected_contradictions=[],
        )
        assert result_abandon.projected_net_recovery == 0


class TestContestExecutor:
    @pytest.mark.asyncio
    async def test_auto_submit_mock(self):
        executor = ContestExecutor(mock_mode=True)
        eval_result = DisputeEvaluationResult(
            dispute_id="disp_TEST001",
            win_probability=0.80,
            recommended_action="AUTO_SUBMIT",
            reasoning=["Strong evidence"],
            evidence_completeness_score=0.90,
            projected_net_recovery=100000,
        )
        result = await executor.execute(
            evaluation=eval_result,
            invoice_path="data/generated_docs/invoices/clean_0000_invoice.pdf",
            pod_path="data/generated_docs/pods/clean_0000_pod.pdf",
        )
        assert result["status"] == "AUTO_SUBMITTED"
        assert result["mock"] is True

    @pytest.mark.asyncio
    async def test_escalation(self):
        executor = ContestExecutor(mock_mode=True)
        eval_result = DisputeEvaluationResult(
            dispute_id="disp_TEST002",
            win_probability=0.50,
            recommended_action="ESCALATE_HUMAN",
            reasoning=["Moderate probability"],
            evidence_completeness_score=0.60,
            projected_net_recovery=25000,
        )
        result = await executor.execute(evaluation=eval_result)
        assert result["status"] == "ESCALATED_HUMAN_REVIEW"
        assert len(executor.get_review_queue()) == 1

    @pytest.mark.asyncio
    async def test_abandonment(self):
        executor = ContestExecutor(mock_mode=True)
        eval_result = DisputeEvaluationResult(
            dispute_id="disp_TEST003",
            win_probability=0.25,
            recommended_action="ABANDON",
            reasoning=["Low probability"],
            evidence_completeness_score=0.20,
            projected_net_recovery=0,
        )
        result = await executor.execute(evaluation=eval_result)
        assert result["status"] == "ABANDONED_LOW_WIN_RATE"


class TestOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_clean_case_e2e(self, ground_truth):
        clean_case = next(
            c for c in ground_truth["cases"] if c["split_name"] == "clean_wins"
        )

        orch = Orchestrator(mock_mode=True)
        result = await orch.process_dispute(
            dispute_id=clean_case["dispute_id"],
            payment_id=clean_case["payment_id"],
            amount=clean_case["total_amount"] * 100,
            reason_code=clean_case["reason_code"],
        )

        assert result["status"] in ("AUTO_SUBMITTED", "ESCALATED_HUMAN_REVIEW")
        assert "evaluation" in result
        assert "extraction" in result
        assert "contradiction" in result
        assert result["elapsed_seconds"] > 0

    @pytest.mark.asyncio
    async def test_address_mismatch_case(self, ground_truth):
        mismatch_case = next(
            c for c in ground_truth["cases"] if c["split_name"] == "address_mismatches"
        )

        orch = Orchestrator(mock_mode=True)
        result = await orch.process_dispute(
            dispute_id=mismatch_case["dispute_id"],
            payment_id=mismatch_case["payment_id"],
            amount=mismatch_case["total_amount"] * 100,
            reason_code=mismatch_case["reason_code"],
        )

        assert result["status"] in ("AUTO_SUBMITTED", "ESCALATED_HUMAN_REVIEW", "ABANDONED_LOW_WIN_RATE")
        assert "contradiction" in result
        assert result["contradiction"]["address_similarity"] < 0.8

    @pytest.mark.asyncio
    async def test_missing_evidence_case(self, ground_truth):
        missing_case = next(
            c for c in ground_truth["cases"] if c["split_name"] == "missing_evidence"
        )

        orch = Orchestrator(mock_mode=True)
        result = await orch.process_dispute(
            dispute_id=missing_case["dispute_id"],
            payment_id=missing_case["payment_id"],
            amount=missing_case["total_amount"] * 100,
            reason_code=missing_case["reason_code"],
        )

        assert result["status"] == "ABANDONED_LOW_WIN_RATE"

    @pytest.mark.asyncio
    async def test_audit_trail(self, ground_truth):
        clean_case = next(
            c for c in ground_truth["cases"] if c["split_name"] == "clean_wins"
        )

        from packages.core.database import SessionLocal
        from packages.core.models import AuditLog
        orch = Orchestrator(mock_mode=True)
        await orch.process_dispute(
            dispute_id=clean_case["dispute_id"],
            payment_id=clean_case["payment_id"],
            amount=clean_case["total_amount"] * 100,
            reason_code=clean_case["reason_code"],
        )

        db = SessionLocal()
        logs = db.query(AuditLog).filter(
            AuditLog.dispute_id == clean_case["dispute_id"]
        ).all()
        db.close()

        assert len(logs) >= 4
        event_types = [log.event_type for log in logs]
        assert "dispute_received" in event_types
        assert "evidence_fetched" in event_types
        assert "vision_extraction_complete" in event_types
        assert "evaluation_complete" in event_types
