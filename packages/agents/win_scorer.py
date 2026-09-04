"""
Win Probability Scoring Engine for SentinelShield AI.

Implements the cost-sensitive financial yield model and decision threshold rules
as defined in the project specification.
"""

from packages.core.schemas import (
    ContradictionAnalysis,
    DisputeEvaluationResult,
    ExtractedPODEvidence,
)


# Reason code base win rates (Section 5 of spec)
REASON_CODE_WIN_RATES = {
    "retrieval": 0.85,
    "chargeback": 0.60,
    "fraud": 0.35,
}

# Decision thresholds (Section 5 of spec)
AUTO_SUBMIT_WIN_THRESHOLD = 0.65
ABANDON_WIN_THRESHOLD = 0.40
AUTO_SUBMIT_MAX_AMOUNT_PAISE = 2500000  # ₹25,000 in paise


def compute_win_probability(
    reason_code: str,
    address_similarity_score: float,
    confidence_score: float,
    signature_present: bool,
) -> float:
    """Compute P(win) using the formula from Section 5.

    P(win) = W_reason * (0.45 * S_addr + 0.35 * S_doc + 0.20 * I_signature)

    Args:
        reason_code: One of 'retrieval', 'chargeback', 'fraud'.
        address_similarity_score: S_addr in [0, 1].
        confidence_score: S_doc in [0, 1].
        signature_present: Boolean indicator for signature presence.

    Returns:
        Win probability in [0, 1].
    """
    w_reason = REASON_CODE_WIN_RATES.get(reason_code, 0.50)
    s_addr = max(0.0, min(1.0, address_similarity_score))
    s_doc = max(0.0, min(1.0, confidence_score))
    i_sig = 1.0 if signature_present else 0.0

    p_win = w_reason * (0.45 * s_addr + 0.35 * s_doc + 0.20 * i_sig)
    return round(max(0.0, min(1.0, p_win)), 4)


def determine_action(
    win_probability: float,
    amount_paise: int,
    contradictions_count: int,
) -> str:
    """Determine recommended action based on decision threshold rules.

    Rules (Section 5):
    - AUTO_SUBMIT: P(win) >= 0.65 AND Amount <= 2500000 paise AND Contradictions == 0
    - ESCALATE_HUMAN: 0.40 <= P(win) < 0.65 OR Amount > 2500000 paise OR Contradictions > 0
    - ABANDON: P(win) < 0.40

    Args:
        win_probability: Computed win probability.
        amount_paise: Dispute amount in paise.
        contradictions_count: Number of detected contradictions.

    Returns:
        One of 'AUTO_SUBMIT', 'ESCALATE_HUMAN', 'ABANDON'.
    """
    if win_probability < ABANDON_WIN_THRESHOLD:
        return "ABANDON"

    if (
        win_probability >= AUTO_SUBMIT_WIN_THRESHOLD
        and amount_paise <= AUTO_SUBMIT_MAX_AMOUNT_PAISE
        and contradictions_count == 0
    ):
        return "AUTO_SUBMIT"

    return "ESCALATE_HUMAN"


def evaluate(
    dispute_id: str,
    reason_code: str,
    amount_paise: int,
    address_similarity_score: float,
    confidence_score: float,
    signature_present: bool,
    contradictions_count: int,
    detected_contradictions: list[str],
) -> DisputeEvaluationResult:
    """Full evaluation: compute win probability, determine action, build result.

    Args:
        dispute_id: Unique dispute identifier.
        reason_code: Chargeback reason code.
        amount_paise: Dispute amount in currency subunits.
        address_similarity_score: Semantic address match score.
        confidence_score: Document extraction confidence.
        signature_present: Whether signature was detected.
        contradictions_count: Count of detected contradictions.
        detected_contradictions: List of contradiction descriptions.

    Returns:
        DisputeEvaluationResult with full scoring and decision.
    """
    win_prob = compute_win_probability(
        reason_code=reason_code,
        address_similarity_score=address_similarity_score,
        confidence_score=confidence_score,
        signature_present=signature_present,
    )

    action = determine_action(
        win_probability=win_prob,
        amount_paise=amount_paise,
        contradictions_count=contradictions_count,
    )

    evidence_completeness = (
        (0.4 * address_similarity_score)
        + (0.4 * confidence_score)
        + (0.2 * (1.0 if signature_present else 0.0))
    )

    if action == "AUTO_SUBMIT":
        projected_recovery = amount_paise
    elif action == "ABANDON":
        projected_recovery = 0
    else:
        projected_recovery = int(amount_paise * win_prob * 0.5)

    reasoning = []
    if win_prob >= AUTO_SUBMIT_WIN_THRESHOLD:
        reasoning.append(f"Strong win probability ({win_prob:.2%})")
    elif win_prob >= ABANDON_WIN_THRESHOLD:
        reasoning.append(f"Moderate win probability ({win_prob:.2%})")
    else:
        reasoning.append(f"Low win probability ({win_prob:.2%}), recommending abandon")

    if contradictions_count > 0:
        reasoning.append(f"{contradictions_count} contradiction(s) detected")
    else:
        reasoning.append("No contradictions detected")

    if amount_paise > AUTO_SUBMIT_MAX_AMOUNT_PAISE:
        reasoning.append(f"High-value dispute (Rs. {amount_paise // 100:,.0f})")

    reasoning.append(f"Reason code: {reason_code} (base rate: {REASON_CODE_WIN_RATES.get(reason_code, 0):.0%})")

    return DisputeEvaluationResult(
        dispute_id=dispute_id,
        win_probability=win_prob,
        recommended_action=action,
        reasoning=reasoning,
        evidence_completeness_score=round(evidence_completeness, 4),
        projected_net_recovery=projected_recovery,
    )
