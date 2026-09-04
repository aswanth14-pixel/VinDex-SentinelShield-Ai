"""
Dispute Management REST Endpoints.

Provides query endpoints to fetch dispute queues, retrieve individual disputes,
and human-in-the-loop review override capabilities.
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.core.database import SessionLocal
from packages.core.models import AuditLog, Dispute, Evaluation, EvidenceBinder


router = APIRouter()


class DisputeResponse(BaseModel):
    id: str
    payment_id: str
    amount: int
    currency: str
    status: str
    reason_code: str
    respond_by: int
    created_at: int


class DisputeDetailResponse(DisputeResponse):
    evaluation: Optional[dict] = None
    evidence: Optional[dict] = None
    audit_logs: Optional[list] = None


class ReviewActionRequest(BaseModel):
    action: str  # "approve" or "dismiss"
    notes: Optional[str] = None


@router.get("/disputes")
async def list_disputes(
    status: Optional[str] = None,
    reason_code: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List disputes with optional filtering by status and reason code."""
    db = SessionLocal()
    try:
        query = db.query(Dispute)
        if status:
            query = query.filter(Dispute.status == status)
        if reason_code:
            query = query.filter(Dispute.reason_code == reason_code)

        total = query.count()
        disputes = query.offset(offset).limit(limit).all()

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "disputes": [
                {
                    "id": d.id,
                    "payment_id": d.payment_id,
                    "amount": d.amount,
                    "currency": d.currency,
                    "status": d.status,
                    "reason_code": d.reason_code,
                    "respond_by": d.respond_by,
                    "created_at": d.created_at,
                }
                for d in disputes
            ],
        }
    finally:
        db.close()


@router.get("/disputes/{dispute_id}")
async def get_dispute(dispute_id: str):
    """Retrieve a single dispute with evaluation and evidence details."""
    db = SessionLocal()
    try:
        dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")

        evaluation = db.query(Evaluation).filter(
            Evaluation.dispute_id == dispute_id
        ).first()

        evidence = db.query(EvidenceBinder).filter(
            EvidenceBinder.dispute_id == dispute_id
        ).first()

        audit_logs = db.query(AuditLog).filter(
            AuditLog.dispute_id == dispute_id
        ).order_by(AuditLog.timestamp).all()

        return {
            "id": dispute.id,
            "payment_id": dispute.payment_id,
            "amount": dispute.amount,
            "currency": dispute.currency,
            "status": dispute.status,
            "reason_code": dispute.reason_code,
            "respond_by": dispute.respond_by,
            "created_at": dispute.created_at,
            "evaluation": {
                "win_probability": evaluation.win_probability,
                "address_similarity": evaluation.address_similarity,
                "contradictions": json.loads(evaluation.contradictions) if evaluation.contradictions else [],
                "action": evaluation.action,
            } if evaluation else None,
            "evidence": {
                "order_id": evidence.order_id,
                "awb_number": evidence.awb_number,
                "courier_name": evidence.courier_name,
                "invoice_path": evidence.invoice_path,
                "pod_path": evidence.pod_path,
            } if evidence else None,
            "audit_logs": [
                {
                    "event_type": log.event_type,
                    "event_data": json.loads(log.event_data) if log.event_data else {},
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                }
                for log in audit_logs
            ],
        }
    finally:
        db.close()


@router.post("/disputes/{dispute_id}/review")
async def review_dispute(dispute_id: str, request: ReviewActionRequest):
    """Human-in-the-loop review override endpoint.

    Allows manual approval or dismissal of escalated disputes.
    """
    db = SessionLocal()
    try:
        dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")

        if request.action == "approve":
            dispute.status = "AUTO_SUBMITTED"
        elif request.action == "dismiss":
            dispute.status = "DISMISSED_HUMAN"
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'dismiss'")

        log = AuditLog(
            dispute_id=dispute_id,
            event_type="human_review",
            event_data=json.dumps({
                "action": request.action,
                "notes": request.notes,
            }),
        )
        db.add(log)
        db.commit()

        return {
            "dispute_id": dispute_id,
            "status": dispute.status,
            "action": request.action,
        }
    finally:
        db.close()


@router.get("/disputes/stats/summary")
async def dispute_stats():
    """Get aggregate dispute statistics."""
    db = SessionLocal()
    try:
        from sqlalchemy import func

        stats = db.query(
            Dispute.status,
            func.count(Dispute.id),
            func.sum(Dispute.amount),
        ).group_by(Dispute.status).all()

        return {
            "by_status": [
                {
                    "status": status,
                    "count": count,
                    "total_amount": total or 0,
                }
                for status, count, total in stats
            ],
            "total_disputes": sum(count for _, count, _ in stats),
        }
    finally:
        db.close()
