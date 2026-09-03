"""
Semantic Contradiction Verifier for SentinelShield AI.

Compares extracted POD evidence against store order data to detect address mismatches,
pincode deviations, and adversarial fraud indicators.
"""

import json
import re
from typing import List, Optional

from packages.core.schemas import ContradictionAnalysis, ExtractedPODEvidence


def _normalize_address(address: str) -> str:
    """Normalize address string for comparison."""
    addr = address.lower().strip()
    addr = re.sub(r"[^\w\s]", " ", addr)
    addr = re.sub(r"\s+", " ", addr)

    replacements = {
        "mahatma gandhi": "mg",
        "gandhi nagar": "gn",
        "road": "rd",
        "street": "st",
        "nagar": "ngr",
        "marg": "mrg",
        "venue": "vn",
        "layout": "lyt",
        "extension": "ext",
        "colony": "col",
        "bangalore": "blr",
        "bengaluru": "blr",
        "mumbai": "mum",
        "bombay": "mum",
        "delhi": "dl",
        "new delhi": "dl",
        "chennai": "chn",
        "madras": "chn",
        "hyderabad": "hyd",
        "pune": "pune",
        "kolkata": "kol",
        "calcutta": "kol",
    }
    for key, val in replacements.items():
        addr = addr.replace(key, val)

    return addr.strip()


def _extract_pincode(address: str) -> Optional[str]:
    """Extract 6-digit Indian pincode from address string."""
    match = re.search(r"\b(\d{6})\b", address)
    return match.group(1) if match else None


def _compute_address_similarity(addr1: str, addr2: str) -> float:
    """Compute similarity score between two normalized addresses using Jaccard index."""
    norm1 = _normalize_address(addr1)
    norm2 = _normalize_address(addr2)

    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())

    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


class ContradictionVerifier:
    """Verifies semantic consistency between extracted POD and store order data."""

    def __init__(self, tolerance_threshold: float = 0.5):
        self._tolerance = tolerance_threshold

    async def verify(
        self,
        extracted: ExtractedPODEvidence,
        expected_address: str,
        expected_pincode: Optional[str] = None,
        expected_recipient: Optional[str] = None,
    ) -> ContradictionAnalysis:
        """Compare extracted evidence against expected order data.

        Args:
            extracted: Vision-extracted POD evidence.
            expected_address: Expected shipping address from store.
            expected_pincode: Expected pincode from store.
            expected_recipient: Expected recipient name from store.

        Returns:
            ContradictionAnalysis with match results and detected contradictions.
        """
        address_similarity = _compute_address_similarity(
            extracted.delivery_address, expected_address
        )

        address_match = address_similarity >= self._tolerance

        extracted_pincode = extracted.delivery_pincode or _extract_pincode(
            extracted.delivery_address
        )
        pincode_match = (
            extracted_pincode == expected_pincode
            if expected_pincode and extracted_pincode
            else True
        )

        recipient_match = True
        if expected_recipient and extracted.recipient_name:
            extracted_lower = extracted.recipient_name.lower().strip()
            expected_lower = expected_recipient.lower().strip()
            recipient_match = (
                extracted_lower == expected_lower
                or extracted_lower in expected_lower
                or expected_lower in extracted_lower
            )

        detected: List[str] = []
        if not address_match:
            detected.append(
                f"Address mismatch: similarity {address_similarity:.2f} below threshold {self._tolerance}"
            )
        if not pincode_match:
            detected.append(
                f"Pincode mismatch: extracted={extracted_pincode}, expected={expected_pincode}"
            )
        if not recipient_match:
            detected.append(
                f"Recipient mismatch: extracted='{extracted.recipient_name}', expected='{expected_recipient}'"
            )

        is_adversarial = (
            not address_match and not pincode_match
        ) or address_similarity < 0.2

        return ContradictionAnalysis(
            address_match=address_match,
            address_similarity_score=address_similarity,
            pincode_match=pincode_match,
            recipient_match=recipient_match,
            detected_contradictions=detected,
            is_adversarial=is_adversarial,
        )
