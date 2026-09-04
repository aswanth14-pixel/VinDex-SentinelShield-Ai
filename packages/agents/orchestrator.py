"""
End-to-End Agent Orchestrator for SentinelShield AI.

Coordinates the full dispute processing pipeline:
1. Fetch evidence from store and courier APIs
2. Extract structured data from POD via Vision LLM
3. Verify semantic contradictions
4. Score win probability
5. Execute contest submission or escalation
6. Append audit trail
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

from packages.agents.contradiction_verifier import ContradictionVerifier
from packages.agents.contest_executor import ContestExecutor
from packages.agents.vision_extractor import VisionExtractor
from packages.agents.win_scorer import evaluate, determine_action
from packages.core.config import settings
from packages.core.database import SessionLocal, init_db
from packages.core.models import AuditLog, Dispute, Evaluation, EvidenceBinder, Extraction
from packages.integrations.mock_courier import MockCourier
from packages.integrations.mock_store import MockStore


class Orchestrator:
    """Coordinates the full dispute processing pipeline."""

    def __init__(self, mock_mode: Optional[bool] = None):
        self._mock_mode = mock_mode if mock_mode is not None else settings.MOCK_MODE
        self._store = MockStore()
        self._courier = MockCourier()
        self._extractor = VisionExtractor(mock_mode=self._mock_mode)
        self._verifier = ContradictionVerifier()
        self._executor = ContestExecutor(mock_mode=self._mock_mode)

    async def process_dispute(
        self,
        dispute_id: str,
        payment_id: str,
        amount: int,
        reason_code: str,
    ) -> dict:
        """Process a single dispute through the full pipeline.

        Args:
            dispute_id: Razorpay dispute ID.
            payment_id: Razorpay payment ID.
            amount: Dispute amount in paise.
            reason_code: Chargeback reason code.

        Returns:
            Execution result with status and all intermediate data.
        """
        start_time = time.perf_counter()
        init_db()
        db = SessionLocal()

        try:
            existing = db.query(Dispute).filter(Dispute.id == dispute_id).first()
            if existing:
                db_dispute = existing
                db_dispute.status = "open"
                db_dispute.payment_id = payment_id
                db_dispute.amount = amount
                db_dispute.reason_code = reason_code
            else:
                db_dispute = Dispute(
                    id=dispute_id,
                    payment_id=payment_id,
                    amount=amount,
                    reason_code=reason_code,
                    status="open",
                    respond_by=0,
                    created_at=int(time.time()),
                )
                db.add(db_dispute)
            db.commit()

            self._append_audit(db, dispute_id, "dispute_received", {
                "payment_id": payment_id,
                "amount": amount,
                "reason_code": reason_code,
            })

            # Step 1: Fetch evidence from store and courier
            store_order = self._store.get_order_by_payment_id(payment_id)
            if store_order is None:
                return self._handle_missing_order(db, dispute_id, payment_id)

            pod_path, invoice_path = self._courier.get_documents(store_order.order_id)
            if pod_path is None:
                return self._handle_missing_pod(db, dispute_id, store_order)

            binder = EvidenceBinder(
                dispute_id=dispute_id,
                order_id=store_order.order_id,
                awb_number="",
                courier_name="",
                invoice_path=invoice_path or "",
                pod_path=pod_path or "",
            )
            db.add(binder)
            db.commit()
            db.refresh(binder)

            self._append_audit(db, dispute_id, "evidence_fetched", {
                "order_id": store_order.order_id,
                "has_pod": pod_path is not None,
                "has_invoice": invoice_path is not None,
            })

            # Step 2: Vision extraction
            extraction = await self._extractor.extract(pod_path)

            extraction_rec = Extraction(
                binder_id=binder.id,
                raw_response=extraction.model_dump_json(),
                parsed_evidence=extraction.model_dump_json(),
                confidence_score=extraction.confidence_score,
            )
            db.add(extraction_rec)
            db.commit()

            binder.awb_number = extraction.awb_number
            binder.courier_name = extraction.courier_name
            db.commit()

            self._append_audit(db, dispute_id, "vision_extraction_complete", {
                "awb": extraction.awb_number,
                "confidence": extraction.confidence_score,
            })

            # Step 3: Contradiction verification
            contradiction = await self._verifier.verify(
                extracted=extraction,
                expected_address=store_order.shipping_address,
                expected_pincode=store_order.shipping_pincode,
                expected_recipient=store_order.customer_name,
            )

            # Step 4: Win probability scoring
            eval_result = evaluate(
                dispute_id=dispute_id,
                reason_code=reason_code,
                amount_paise=amount,
                address_similarity_score=contradiction.address_similarity_score,
                confidence_score=extraction.confidence_score,
                signature_present=extraction.signature_present,
                contradictions_count=len(contradiction.detected_contradictions),
                detected_contradictions=contradiction.detected_contradictions,
            )

            eval_rec = Evaluation(
                dispute_id=dispute_id,
                win_probability=eval_result.win_probability,
                address_similarity=contradiction.address_similarity_score,
                contradictions=json.dumps(contradiction.detected_contradictions),
                action=eval_result.recommended_action,
            )
            db.add(eval_rec)
            db.commit()

            self._append_audit(db, dispute_id, "evaluation_complete", {
                "win_probability": eval_result.win_probability,
                "action": eval_result.recommended_action,
            })

            # Step 5: Execute action
            execution_result = await self._executor.execute(
                evaluation=eval_result,
                invoice_path=invoice_path,
                pod_path=pod_path,
            )

            db_dispute.status = execution_result.get("status", "unknown")
            db.commit()

            self._append_audit(db, dispute_id, "action_executed", execution_result)

            elapsed = time.perf_counter() - start_time

            return {
                **execution_result,
                "dispute_id": dispute_id,
                "elapsed_seconds": round(elapsed, 3),
                "extraction": extraction.model_dump(),
                "contradiction": {
                    "address_match": contradiction.address_match,
                    "address_similarity": contradiction.address_similarity_score,
                    "pincode_match": contradiction.pincode_match,
                    "is_adversarial": contradiction.is_adversarial,
                    "contradictions": contradiction.detected_contradictions,
                },
                "evaluation": eval_result.model_dump(),
            }

        finally:
            db.close()

    def _handle_missing_order(self, db, dispute_id: str, payment_id: str) -> dict:
        """Handle case where store order not found."""
        result = {
            "status": "ESCALATED_HUMAN_REVIEW",
            "action": "ESCALATE_HUMAN",
            "dispute_id": dispute_id,
            "error": f"Order not found for payment_id: {payment_id}",
        }
        self._append_audit(db, dispute_id, "order_not_found", result)
        return result

    def _handle_missing_pod(self, db, dispute_id: str, store_order) -> dict:
        """Handle case where POD document not available."""
        result = {
            "status": "ABANDONED_LOW_WIN_RATE",
            "action": "ABANDON",
            "dispute_id": dispute_id,
            "error": "POD document not available",
        }
        self._append_audit(db, dispute_id, "pod_not_found", result)
        return result

    def _append_audit(self, db, dispute_id: str, event_type: str, event_data: dict):
        """Append an immutable audit log record."""
        log = AuditLog(
            dispute_id=dispute_id,
            event_type=event_type,
            event_data=json.dumps(event_data),
            timestamp=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()

    def get_review_queue(self) -> list[dict]:
        """Return disputes pending human review."""
        return self._executor.get_review_queue()
