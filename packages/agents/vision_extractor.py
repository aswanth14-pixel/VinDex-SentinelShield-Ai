"""
Multi-Modal Vision Document Extractor for SentinelShield AI.

Uses Gemini Vision-Language Model to extract structured verification data
from scanned courier Proof of Delivery (POD) documents.
"""

import base64
import json
from pathlib import Path
from typing import Optional

import fitz  # pymupdf
from PIL import Image

from packages.core.config import settings
from packages.core.schemas import ExtractedPODEvidence


EXTRACTION_PROMPT = """You are an expert forensic document analyst inspecting logistics shipping receipts and Proof of Delivery (POD) documents for Indian e-commerce shipments.

TASK: Extract the delivery details with extreme precision. Analyze handwriting, courier stamps, delivery agent marks, and scanned text.

OUTPUT FORMAT: Return strictly valid JSON matching this schema:
{
  "awb_number": "string",
  "courier_name": "string",
  "recipient_name": "string or null",
  "delivery_address": "string",
  "delivery_pincode": "string or null",
  "delivery_timestamp": "string or null",
  "signature_present": true/false,
  "signature_type": "handwritten | stamp | otp_verified | missing",
  "confidence_score": 0.0 to 1.0,
  "extraction_notes": "string"
}

Analyze the document carefully:
- AWB numbers are typically 10-15 digits printed near barcodes
- Courier names appear in header logos (Delhivery, Shiprocket, BlueDart, DTDC, Ecom Express)
- Delivery addresses may be handwritten or printed
- Signatures can be handwritten squiggles, rubber stamps, or OTP verification codes
- Confidence score should reflect overall clarity of the scanned document"""


class VisionExtractor:
    """Extracts structured data from POD documents using Gemini Vision."""

    def __init__(self, api_key: Optional[str] = None, mock_mode: Optional[bool] = None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._mock_mode = mock_mode if mock_mode is not None else settings.MOCK_MODE

    def _extract_first_page_as_image(self, pdf_path: str) -> bytes:
        """Render page 1 of PDF to PNG image bytes using PyMuPDF."""
        doc = fitz.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        import io
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def _load_image_bytes(self, file_path: str) -> bytes:
        """Load image bytes from file (PNG/JPEG) or render PDF page 1."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_first_page_as_image(file_path)
        elif suffix in (".png", ".jpg", ".jpeg"):
            return path.read_bytes()
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def _to_base64_data_uri(self, image_bytes: bytes) -> str:
        """Convert image bytes to base64 data URI."""
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{encoded}"

    async def _call_gemini_vision(self, image_data_uri: str) -> str:
        """Call Gemini Vision API for document extraction."""
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        image_part = {
            "mime_type": "image/png",
            "data": image_data_uri.split(",")[1],
        }

        response = model.generate_content(
            [EXTRACTION_PROMPT, image_part],
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        return response.text

    def _parse_response(self, raw_response: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = raw_response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.strip().startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        return json.loads(text)

    async def extract(self, file_path: str) -> ExtractedPODEvidence:
        """Extract structured evidence from a POD document.

        Args:
            file_path: Path to PDF, PNG, or JPEG file.

        Returns:
            ExtractedPODEvidence with parsed fields.
        """
        if self._mock_mode:
            return self._mock_extract(file_path)

        image_bytes = self._load_image_bytes(file_path)
        data_uri = self._to_base64_data_uri(image_bytes)

        raw_response = await self._call_gemini_vision(data_uri)
        parsed = self._parse_response(raw_response)

        return ExtractedPODEvidence(**parsed)

    def _mock_extract(self, file_path: str) -> ExtractedPODEvidence:
        """Mock extraction using ground truth for evaluation without API calls."""
        import json

        ground_truth_path = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_ground_truth.json"
        with open(ground_truth_path) as f:
            ground_truth = json.load(f)

        path = Path(file_path)
        case_id = path.stem.replace("_pod", "")
        for case in ground_truth["cases"]:
            if case["case_id"] == case_id:
                return ExtractedPODEvidence(
                    awb_number=case["awb_number"],
                    courier_name=case["courier_name"],
                    recipient_name=case["customer_name"],
                    delivery_address=case["pod_address"] or "Address not available",
                    delivery_pincode=case["pod_pincode"] or None,
                    delivery_timestamp=case.get("delivery_timestamp") or None,
                    signature_present=case["signature_type"] != "missing",
                    signature_type=case["signature_type"],
                    confidence_score=0.95 if case["signature_type"] != "missing" else 0.3,
                    extraction_notes="Mock extraction from ground truth",
                )

        return ExtractedPODEvidence(
            awb_number="0000000000",
            courier_name="Unknown",
            delivery_address="Address not found",
            signature_present=False,
            signature_type="missing",
            confidence_score=0.1,
            extraction_notes="No matching case found in ground truth",
        )
