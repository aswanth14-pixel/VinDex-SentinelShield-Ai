"""
Tests for vision document extraction and contradiction verification.
"""

import json
from pathlib import Path

import pytest

from packages.agents.contradiction_verifier import (
    ContradictionVerifier,
    _compute_address_similarity,
    _extract_pincode,
    _normalize_address,
)
from packages.agents.vision_extractor import VisionExtractor
from packages.core.schemas import ExtractedPODEvidence


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "synthetic_ground_truth.json"


@pytest.fixture
def ground_truth():
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


@pytest.fixture
def sample_pod_path():
    return str(DATA_DIR / "generated_docs" / "pods" / "clean_0000_pod.pdf")


@pytest.fixture
def messy_pod_path():
    return str(DATA_DIR / "generated_docs" / "pods" / "messy_0000_pod.png")


class TestAddressNormalization:
    def test_basic_normalization(self):
        addr = "42, MG Road, Bangalore 560001"
        normalized = _normalize_address(addr)
        assert "mg" in normalized
        assert "blr" in normalized

    def test_city_aliases(self):
        assert "blr" in _normalize_address("Bengaluru 560001")
        assert "mum" in _normalize_address("Bombay 400001")
        assert "chn" in _normalize_address("Madras 600001")

    def test_punctuation_removal(self):
        addr = "Flat-4B, Sector-7, HSR Layout"
        normalized = _normalize_address(addr)
        assert "-" not in normalized
        assert "," not in normalized


class TestPincodeExtraction:
    def test_valid_pincode(self):
        assert _extract_pincode("42 MG Road, Bangalore 560001") == "560001"

    def test_no_pincode(self):
        assert _extract_pincode("42 MG Road, Bangalore") is None

    def test_multiple_pincodes_returns_first(self):
        assert _extract_pincode("From 110001 to 400001") == "110001"


class TestAddressSimilarity:
    def test_identical_addresses(self):
        addr = "42 MG Road, Bangalore 560001"
        score = _compute_address_similarity(addr, addr)
        assert score == 1.0

    def test_similar_addresses(self):
        addr1 = "42 MG Road, Bangalore 560001"
        addr2 = "42 MG Road, Bengaluru 560001"
        score = _compute_address_similarity(addr1, addr2)
        assert score > 0.7

    def test_different_addresses(self):
        addr1 = "42 MG Road, Bangalore 560001"
        addr2 = "99 Station Road, Mumbai 400001"
        score = _compute_address_similarity(addr1, addr2)
        assert score < 0.3

    def test_empty_addresses(self):
        assert _compute_address_similarity("", "") == 1.0

    def test_one_empty(self):
        assert _compute_address_similarity("42 MG Road", "") == 0.0


class TestVisionExtractorMockMode:
    def test_mock_extraction_clean_case(self, ground_truth, sample_pod_path):
        extractor = VisionExtractor(mock_mode=True)
        evidence = extractor._mock_extract(sample_pod_path)

        assert isinstance(evidence, ExtractedPODEvidence)
        assert evidence.awb_number is not None
        assert evidence.courier_name is not None
        assert evidence.delivery_address is not None
        assert 0.0 <= evidence.confidence_score <= 1.0
        assert evidence.signature_type in ["handwritten", "stamp", "otp_verified", "missing"]

    def test_mock_extraction_messy_case(self, ground_truth, messy_pod_path):
        extractor = VisionExtractor(mock_mode=True)
        evidence = extractor._mock_extract(messy_pod_path)

        assert isinstance(evidence, ExtractedPODEvidence)
        assert evidence.confidence_score >= 0.0

    def test_mock_extraction_missing_evidence(self):
        extractor = VisionExtractor(mock_mode=True)
        evidence = extractor._mock_extract("data/generated_docs/pods/nonexistent_pod.pdf")

        assert evidence.signature_type == "missing"
        assert evidence.confidence_score < 0.5


class TestContradictionVerifier:
    @pytest.mark.asyncio
    async def test_matching_addresses(self):
        verifier = ContradictionVerifier()
        extracted = ExtractedPODEvidence(
            awb_number="1234567890",
            courier_name="Delhivery",
            delivery_address="42 MG Road, Bangalore 560001",
            delivery_pincode="560001",
            signature_present=True,
            signature_type="handwritten",
            confidence_score=0.95,
        )

        result = await verifier.verify(
            extracted=extracted,
            expected_address="42 MG Road, Bangalore 560001",
            expected_pincode="560001",
        )

        assert result.address_match is True
        assert result.pincode_match is True
        assert result.is_adversarial is False
        assert len(result.detected_contradictions) == 0

    @pytest.mark.asyncio
    async def test_mismatched_addresses(self):
        verifier = ContradictionVerifier()
        extracted = ExtractedPODEvidence(
            awb_number="1234567890",
            courier_name="Delhivery",
            delivery_address="99 Station Road, Mumbai 400001",
            delivery_pincode="400001",
            signature_present=True,
            signature_type="stamp",
            confidence_score=0.85,
        )

        result = await verifier.verify(
            extracted=extracted,
            expected_address="42 MG Road, Bangalore 560001",
            expected_pincode="560001",
        )

        assert result.address_match is False
        assert result.pincode_match is False
        assert result.is_adversarial is True
        assert len(result.detected_contradictions) >= 1

    @pytest.mark.asyncio
    async def test_pincode_only_mismatch(self):
        verifier = ContradictionVerifier()
        extracted = ExtractedPODEvidence(
            awb_number="1234567890",
            courier_name="Shiprocket",
            delivery_address="42 MG Road, Mumbai 400001",
            delivery_pincode="400001",
            signature_present=True,
            signature_type="otp_verified",
            confidence_score=0.90,
        )

        result = await verifier.verify(
            extracted=extracted,
            expected_address="42 MG Road, Bangalore 560001",
            expected_pincode="560001",
        )

        assert result.pincode_match is False
        assert len(result.detected_contradictions) >= 1

    @pytest.mark.asyncio
    async def test_recipient_mismatch(self):
        verifier = ContradictionVerifier()
        extracted = ExtractedPODEvidence(
            awb_number="1234567890",
            courier_name="Delhivery",
            recipient_name="John Doe",
            delivery_address="42 MG Road, Bangalore 560001",
            signature_present=True,
            signature_type="handwritten",
            confidence_score=0.90,
        )

        result = await verifier.verify(
            extracted=extracted,
            expected_address="42 MG Road, Bangalore 560001",
            expected_recipient="Rahul Sharma",
        )

        assert result.recipient_match is False
        assert any("Recipient" in c for c in result.detected_contradictions)

    @pytest.mark.asyncio
    async def test_with_ground_truth_cases(self, ground_truth):
        verifier = ContradictionVerifier()
        clean_cases = [c for c in ground_truth["cases"] if c["split_name"] == "clean_wins"]

        case = clean_cases[0]
        extracted = ExtractedPODEvidence(
            awb_number=case["awb_number"],
            courier_name=case["courier_name"],
            recipient_name=case["customer_name"],
            delivery_address=case["pod_address"],
            delivery_pincode=case["pod_pincode"],
            signature_present=case["signature_type"] != "missing",
            signature_type=case["signature_type"],
            confidence_score=0.95,
        )

        result = await verifier.verify(
            extracted=extracted,
            expected_address=case["shipping_address"],
            expected_pincode=case["shipping_pincode"],
            expected_recipient=case["customer_name"],
        )

        assert result.address_match is True
        assert result.pincode_match is True
        assert result.is_adversarial is False
