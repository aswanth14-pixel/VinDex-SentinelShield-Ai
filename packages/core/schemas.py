from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RazorpayDisputeEntity(BaseModel):
    id: str = Field(..., description="Unique dispute ID, e.g., disp_J1234567890")
    payment_id: str = Field(..., description="Unique payment ID, e.g., pay_J1234567890")
    amount: int = Field(..., description="Dispute amount in currency subunits (paise)")
    currency: str = Field(default="INR")
    status: str = Field(..., description="open, under_review, won, lost, closed")
    reason_code: str = Field(..., description="chargeback, fraud, retrieval")
    respond_by: int = Field(..., description="Unix timestamp deadline for evidence submission")
    created_at: int = Field(..., description="Unix timestamp of dispute creation")


class RazorpayWebhookPayload(BaseModel):
    entity: str
    account_id: str
    event: str = Field(..., description="e.g., payment.dispute.created")
    contains: List[str]
    payload: Dict[str, Dict[str, RazorpayDisputeEntity]]


class ExtractedPODEvidence(BaseModel):
    awb_number: str
    courier_name: str
    recipient_name: Optional[str] = None
    delivery_address: str
    delivery_pincode: Optional[str] = None
    delivery_timestamp: Optional[str] = None
    signature_present: bool
    signature_type: str = Field(
        ..., description="handwritten, stamp, otp_verified, missing"
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    extraction_notes: Optional[str] = None


class ContradictionAnalysis(BaseModel):
    address_match: bool
    address_similarity_score: float = Field(..., ge=0.0, le=1.0)
    pincode_match: bool
    recipient_match: bool
    detected_contradictions: List[str]
    is_adversarial: bool


class DisputeEvaluationResult(BaseModel):
    dispute_id: str
    win_probability: float = Field(..., ge=0.0, le=1.0)
    recommended_action: str = Field(
        ..., description="AUTO_SUBMIT, ESCALATE_HUMAN, ABANDON"
    )
    reasoning: List[str]
    evidence_completeness_score: float = Field(..., ge=0.0, le=1.0)
    projected_net_recovery: float


class RazorpayContestPayload(BaseModel):
    amount: int
    summary: str = Field(..., max_length=1000)
    shipping_proof: Optional[List[str]] = Field(
        default=None, description="Array of doc_xxx IDs"
    )
    billing_proof: Optional[List[str]] = Field(
        default=None, description="Array of doc_xxx IDs"
    )
    customer_communication: Optional[List[str]] = Field(
        default=None, description="Array of doc_xxx IDs"
    )
    proof_of_service: Optional[List[str]] = Field(
        default=None, description="Array of doc_xxx IDs"
    )
    others: Optional[List[str]] = Field(
        default=None, description="Array of doc_xxx IDs"
    )
    action: str = Field(default="submit")
