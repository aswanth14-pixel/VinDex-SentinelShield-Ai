"""
Contest Executor for SentinelShield AI.

Handles the final step of dispute processing: uploading documents, assembling
contest payloads, and submitting to Razorpay. Also manages escalation to
human review queue.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from packages.core.config import settings
from packages.core.schemas import DisputeEvaluationResult, RazorpayContestPayload
from packages.integrations.razorpay_client import RazorpayClient


class ContestExecutor:
    """Executes dispute contest submissions or escalations based on evaluation results."""

    def __init__(self, razorpay_client: Optional[RazorpayClient] = None, mock_mode: Optional[bool] = None):
        self._client = razorpay_client or RazorpayClient()
        self._mock_mode = mock_mode if mock_mode is not None else settings.MOCK_MODE
        self._review_queue: list[dict] = []

    async def execute(
        self,
        evaluation: DisputeEvaluationResult,
        invoice_path: Optional[str] = None,
        pod_path: Optional[str] = None,
    ) -> dict:
        """Execute the recommended action for a dispute.

        Args:
            evaluation: Result from win_scorer.evaluate().
            invoice_path: Path to invoice PDF (for AUTO_SUBMIT).
            pod_path: Path to POD document (for AUTO_SUBMIT).

        Returns:
            Execution result with status and details.
        """
        action = evaluation.recommended_action

        if action == "AUTO_SUBMIT":
            return await self._auto_submit(evaluation, invoice_path, pod_path)
        elif action == "ESCALATE_HUMAN":
            return self._escalate_to_human(evaluation)
        else:
            return self._abandon(evaluation)

    async def _auto_submit(
        self,
        evaluation: DisputeEvaluationResult,
        invoice_path: Optional[str],
        pod_path: Optional[str],
    ) -> dict:
        """Upload documents and submit contest via Razorpay API."""
        doc_ids = {"shipping_proof": [], "billing_proof": [], "proof_of_service": []}

        if not self._mock_mode:
            if invoice_path:
                try:
                    result = await self._client.upload_document(invoice_path)
                    doc_ids["billing_proof"].append(result.get("id", ""))
                except Exception as e:
                    return {
                        "status": "ERROR",
                        "action": "AUTO_SUBMIT",
                        "error": f"Failed to upload invoice: {str(e)}",
                        "dispute_id": evaluation.dispute_id,
                    }

            if pod_path:
                try:
                    result = await self._client.upload_document(pod_path)
                    doc_ids["proof_of_service"].append(result.get("id", ""))
                except Exception as e:
                    return {
                        "status": "ERROR",
                        "action": "AUTO_SUBMIT",
                        "error": f"Failed to upload POD: {str(e)}",
                        "dispute_id": evaluation.dispute_id,
                    }

            payload = RazorpayContestPayload(
                amount=evaluation.projected_net_recovery,
                summary=" | ".join(evaluation.reasoning),
                shipping_proof=doc_ids["shipping_proof"] or None,
                billing_proof=doc_ids["billing_proof"] or None,
                proof_of_service=doc_ids["proof_of_service"] or None,
            )

            try:
                result = await self._client.contest_dispute(
                    evaluation.dispute_id, payload
                )
                return {
                    "status": "AUTO_SUBMITTED",
                    "action": "AUTO_SUBMIT",
                    "dispute_id": evaluation.dispute_id,
                    "win_probability": evaluation.win_probability,
                    "projected_recovery": evaluation.projected_net_recovery,
                    "razorpay_response": result,
                }
            except Exception as e:
                return {
                    "status": "ERROR",
                    "action": "AUTO_SUBMIT",
                    "error": f"Failed to submit contest: {str(e)}",
                    "dispute_id": evaluation.dispute_id,
                }
        else:
            return {
                "status": "AUTO_SUBMITTED",
                "action": "AUTO_SUBMIT",
                "dispute_id": evaluation.dispute_id,
                "win_probability": evaluation.win_probability,
                "projected_recovery": evaluation.projected_net_recovery,
                "invoice_path": invoice_path,
                "pod_path": pod_path,
                "mock": True,
            }

    def _escalate_to_human(self, evaluation: DisputeEvaluationResult) -> dict:
        """Add dispute to human review queue with complete rationale."""
        review_entry = {
            "dispute_id": evaluation.dispute_id,
            "win_probability": evaluation.win_probability,
            "reasoning": evaluation.reasoning,
            "evidence_completeness": evaluation.evidence_completeness_score,
            "projected_recovery": evaluation.projected_net_recovery,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        self._review_queue.append(review_entry)

        return {
            "status": "ESCALATED_HUMAN_REVIEW",
            "action": "ESCALATE_HUMAN",
            "dispute_id": evaluation.dispute_id,
            "win_probability": evaluation.win_probability,
            "review_queue_position": len(self._review_queue),
        }

    def _abandon(self, evaluation: DisputeEvaluationResult) -> dict:
        """Mark dispute as abandoned due to low win probability."""
        return {
            "status": "ABANDONED_LOW_WIN_RATE",
            "action": "ABANDON",
            "dispute_id": evaluation.dispute_id,
            "win_probability": evaluation.win_probability,
            "reason": "Win probability below threshold, avoiding administrative penalty fees",
        }

    def get_review_queue(self) -> list[dict]:
        """Return all disputes pending human review."""
        return list(self._review_queue)

    def get_audit_record(self, result: dict) -> dict:
        """Create an audit log entry from an execution result."""
        return {
            "event_type": f"dispute_{result.get('action', 'unknown').lower()}",
            "event_data": json.dumps(result),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
