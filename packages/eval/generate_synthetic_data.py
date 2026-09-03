"""
Synthetic Data Generator for SentinelShield AI Evaluation Suite.

Generates 200 synthetic dispute profiles with realistic invoice and POD documents
across 5 evaluation test splits.
"""

import hashlib
import json
import math
import os
import random
import string
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

import fitz  # pymupdf
from PIL import Image, ImageEnhance, ImageFilter
from reportlab.graphics.barcode import code128
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated_docs"
INVOICES_DIR = GENERATED_DIR / "invoices"
PODS_DIR = GENERATED_DIR / "pods"
TEST_SPLITS_DIR = DATA_DIR / "test_splits"

SPLIT_CONFIG = {
    "clean_wins": {"count": 80, "action": "AUTO_SUBMIT"},
    "address_mismatches": {"count": 40, "action": "ESCALATE_HUMAN"},
    "messy_scans": {"count": 40, "action": "TEST_EXTRACTION_RESILIENCE"},
    "adversarial_fraud": {"count": 20, "action": "ESCALATE_HUMAN"},
    "missing_evidence": {"count": 20, "action": "ABANDON"},
}

INDIAN_CITIES = [
    ("Mumbai", "400001", "Maharashtra"),
    ("Delhi", "110001", "Delhi"),
    ("Bangalore", "560001", "Karnataka"),
    ("Chennai", "600001", "Tamil Nadu"),
    ("Hyderabad", "500001", "Telangana"),
    ("Pune", "411001", "Maharashtra"),
    ("Kolkata", "700001", "West Bengal"),
    ("Ahmedabad", "380001", "Gujarat"),
    ("Jaipur", "302001", "Rajasthan"),
    ("Lucknow", "226001", "Uttar Pradesh"),
]

ALT_CITIES = [
    ("Nagpur", "440001", "Maharashtra"),
    ("Bhopal", "462001", "Madhya Pradesh"),
    ("Patna", "800001", "Bihar"),
    ("Indore", "452001", "Madhya Pradesh"),
    ("Nagaland", "797001", "Nagaland"),
]

COURIER_NAMES = ["Delhivery", "Shiprocket", "BlueDart", "DTDC", "Ecom Express"]

FIRST_NAMES = [
    "Rahul", "Priya", "Amit", "Sneha", "Vikram", "Pooja", "Arjun", "Meera",
    "Rohit", "Anita", "Sanjay", "Kavita", "Deepak", "Neha", "Arun", "Swati",
]
LAST_NAMES = [
    "Sharma", "Patel", "Kumar", "Singh", "Reddy", "Nair", "Gupta", "Joshi",
    "Mishra", "Verma", "Choudhary", "Mehta", "Iyer", "Desai", "Rao", "Bose",
]

PRODUCTS = [
    ("Samsung Galaxy S24", 74999),
    ("iPhone 15 Pro", 134900),
    ("OnePlus 12", 64999),
    ("Sony WH-1000XM5", 29990),
    ("MacBook Air M3", 114900),
    ("iPad Pro 11\"", 89900),
    ("Dyson V15 Detect", 62900),
    ("LG OLED TV 55\"", 109990),
    ("boAt Rockerz 550", 1799),
    ("JBL Flip 6", 12999),
]

GSTIN_PREFIXES = ["27", "06", "29", "33", "36", "09", "19", "24", "08", "07"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CaseProfile:
    case_id: str
    split_name: str
    dispute_id: str
    payment_id: str
    order_id: str
    customer_name: str
    shipping_address: str
    shipping_city: str
    shipping_pincode: str
    shipping_state: str
    pod_address: str
    pod_pincode: str
    awb_number: str
    courier_name: str
    product_name: str
    product_amount: int
    total_amount: int
    gstin: str
    invoice_path: str
    pod_path: str
    signature_type: str
    delivery_timestamp: str
    reason_code: str
    expected_action: str
    ground_truth_notes: str
    _created_ts: int = 0
    _delivery_ts: int = 0
    is_adversarial: bool = False
    has_missing_evidence: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rand_digits(n: int) -> str:
    return "".join(random.choices(string.digits, k=n))


def _rand_alpha(n: int) -> str:
    return "".join(random.choices(string.ascii_uppercase, k=n))


def _make_gstin() -> str:
    prefix = random.choice(GSTIN_PREFIXES)
    pan = _rand_alpha(5) + _rand_digits(4) + _rand_alpha(1)
    return prefix + pan + "1Z"


def _make_awb() -> str:
    return _rand_digits(14)


def _make_dispute_id() -> str:
    return "disp_J" + _rand_digits(12)


def _make_payment_id() -> str:
    return "pay_J" + _rand_digits(12)


def _make_order_id() -> str:
    return "ORD" + _rand_digits(10)


def _make_otp() -> str:
    return _rand_digits(6)


def _random_timestamp(year: int = 2024, month_range: tuple = (1, 6)) -> int:
    import calendar
    m = random.randint(*month_range)
    d = random.randint(1, calendar.monthrange(year, m)[1])
    h = random.randint(8, 20)
    mi = random.randint(0, 59)
    from datetime import datetime
    dt = datetime(year, m, d, h, mi)
    return int(dt.timestamp())


def _format_timestamp(ts: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _pick_address(city: str, pincode: str, state: str) -> str:
    house = random.randint(1, 999)
    street = random.choice([
        "MG Road", "Gandhi Nagar", "Station Road", "Temple Street",
        "Park Avenue", "Lake View Road", "Civil Lines", "Nehru Nagar",
        "Rajiv Chowk", "MG Road", "Brigade Road", "Anna Salai",
    ])
    return f"{house}, {street}, {city} {pincode}"


def _pick_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _generate_signature_drawing(drawing: Drawing, x: float, y: float, width: float):
    """Draw a vector squiggle simulating a handwritten signature."""
    num_points = random.randint(6, 12)
    points = []
    cx = x
    for i in range(num_points):
        dx = random.uniform(width * 0.05, width * 0.15)
        dy = random.uniform(-6, 6)
        cx += dx
        points.append((cx, y + dy))

    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        drawing.add(Line(x1, y1, x2, y2, strokeColor=colors.black, strokeWidth=1.2))

    drawing.add(Line(points[-1][0], points[-1][1], points[-1][0] + 8, y + 3,
                     strokeColor=colors.black, strokeWidth=1.2))


# ---------------------------------------------------------------------------
# Invoice PDF Generator
# ---------------------------------------------------------------------------

def _generate_invoice_pdf(case: CaseProfile, output_path: Path):
    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=16, spaceAfter=6)
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=normal, fontSize=9)

    elements.append(Paragraph("TAX INVOICE", title_style))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph(f"<b>Invoice No:</b> INV-{case.case_id.upper()}", normal))
    elements.append(Paragraph(f"<b>Date:</b> {_format_timestamp(case._created_ts).split('T')[0]}", normal))
    elements.append(Paragraph(f"<b>GSTIN:</b> {case.gstin}", normal))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("<b>Bill To:</b>", normal))
    elements.append(Paragraph(case.customer_name, normal))
    elements.append(Paragraph(case.shipping_address, small))
    elements.append(Spacer(1, 6 * mm))

    item_data = [
        ["#", "Item", "Qty", "Unit Price", "Total"],
        ["1", case.product_name, "1",
         f"Rs. {case.product_amount:,.0f}",
         f"Rs. {case.product_amount:,.0f}"],
        ["", "", "", "Subtotal", f"Rs. {case.product_amount:,.0f}"],
        ["", "", "", "CGST (9%)", f"Rs. {int(case.product_amount * 0.09):,.0f}"],
        ["", "", "", "SGST (9%)", f"Rs. {int(case.product_amount * 0.09):,.0f}"],
        ["", "", "", "Grand Total", f"Rs. {case.total_amount:,.0f}"],
    ]

    item_table = Table(item_data, colWidths=[30, 180, 50, 100, 100])
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, 0), 0.5, colors.grey),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
        ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph("<b>Authorized Signatory</b>", normal))

    doc.build(elements)


# ---------------------------------------------------------------------------
# POD PDF Generator
# ---------------------------------------------------------------------------

def _generate_pod_pdf(case: CaseProfile, output_path: Path, messy: bool = False):
    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    elements = []

    normal = styles["Normal"]
    small = ParagraphStyle("PODSmall", parent=normal, fontSize=9)

    header_style = ParagraphStyle("Header", parent=normal, fontSize=12,
                                  textColor=colors.HexColor("#003366"), spaceAfter=2)

    elements.append(Paragraph(f"{case.courier_name} - PROOF OF DELIVERY", header_style))
    elements.append(Spacer(1, 2 * mm))

    barcode_drawing = Drawing(200, 30)
    barcode_text = String(10, 10, f"||| {case.awb_number} |||",
                          fontName="Courier-Bold", fontSize=12)
    barcode_drawing.add(barcode_text)
    elements.append(barcode_drawing)
    elements.append(Spacer(1, 3 * mm))

    info_data = [
        ["AWB Number:", case.awb_number],
        ["Courier:", case.courier_name],
        ["Order ID:", case.order_id],
        ["Delivery Date:", _format_timestamp(case._delivery_ts).split("T")[0]],
        ["Status:", "Delivered"],
    ]
    info_table = Table(info_data, colWidths=[120, 300])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5 * mm))

    elements.append(Paragraph("<b>Recipient Details</b>", normal))
    elements.append(Paragraph(f"Name: {case.customer_name}", normal))
    elements.append(Paragraph(f"Delivery Address: {case.pod_address}", small))
    elements.append(Spacer(1, 5 * mm))

    sig_drawing = Drawing(300, 40)
    if case.signature_type == "otp_verified":
        elements.append(Paragraph(f"<b>OTP Verified:</b> {_make_otp()}", normal))
    elif case.signature_type == "missing":
        elements.append(Paragraph("<b>Signature:</b> Not Available", normal))
    else:
        _generate_signature_drawing(sig_drawing, 10, 25, 200)
        elements.append(sig_drawing)

    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph("This is a system-generated proof of delivery.", small))

    doc.build(elements)


# ---------------------------------------------------------------------------
# Messy scan transformations
# ---------------------------------------------------------------------------

def _apply_messy_transformations(pdf_path: Path, output_path: Path):
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    doc.close()

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    angle = random.uniform(-7, 7)
    img = img.rotate(angle, fillcolor=(255, 255, 255), expand=True)

    if random.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.5)))

    if random.random() < 0.5:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(random.uniform(0.4, 0.7))

    if random.random() < 0.3:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(random.uniform(0.7, 0.9))

    img.save(str(output_path), "PNG")


# ---------------------------------------------------------------------------
# Case generators per split
# ---------------------------------------------------------------------------

def _generate_clean_win_case(index: int) -> CaseProfile:
    city, pincode, state = random.choice(INDIAN_CITIES)
    name = _pick_name()
    address = _pick_address(city, pincode, state)
    product, amount = random.choice(PRODUCTS)
    total = int(amount * 1.18)
    created_ts = _random_timestamp()
    delivery_ts = _random_timestamp(month_range=(1, 6))

    return CaseProfile(
        case_id=f"clean_{index:04d}",
        split_name="clean_wins",
        dispute_id=_make_dispute_id(),
        payment_id=_make_payment_id(),
        order_id=_make_order_id(),
        customer_name=name,
        shipping_address=address,
        shipping_city=city,
        shipping_pincode=pincode,
        shipping_state=state,
        pod_address=address,
        pod_pincode=pincode,
        awb_number=_make_awb(),
        courier_name=random.choice(COURIER_NAMES),
        product_name=product,
        product_amount=amount,
        total_amount=total,
        gstin=_make_gstin(),
        invoice_path="",
        pod_path="",
        signature_type=random.choice(["handwritten", "stamp"]),
        delivery_timestamp=_format_timestamp(delivery_ts),
        reason_code=random.choice(["retrieval", "chargeback"]),
        expected_action="AUTO_SUBMIT",
        ground_truth_notes="Valid invoice, matching POD address, clear signature, prompt delivery",
        _created_ts=created_ts,
        _delivery_ts=delivery_ts,
    )


def _generate_address_mismatch_case(index: int) -> CaseProfile:
    city, pincode, state = random.choice(INDIAN_CITIES)
    alt_city, alt_pincode, alt_state = random.choice(ALT_CITIES)
    name = _pick_name()
    shipping_address = _pick_address(city, pincode, state)
    pod_address = _pick_address(alt_city, alt_pincode, alt_state)
    product, amount = random.choice(PRODUCTS)
    total = int(amount * 1.18)
    created_ts = _random_timestamp()
    delivery_ts = _random_timestamp(month_range=(1, 6))

    return CaseProfile(
        case_id=f"addrmismatch_{index:04d}",
        split_name="address_mismatches",
        dispute_id=_make_dispute_id(),
        payment_id=_make_payment_id(),
        order_id=_make_order_id(),
        customer_name=name,
        shipping_address=shipping_address,
        shipping_city=city,
        shipping_pincode=pincode,
        shipping_state=state,
        pod_address=pod_address,
        pod_pincode=alt_pincode,
        awb_number=_make_awb(),
        courier_name=random.choice(COURIER_NAMES),
        product_name=product,
        product_amount=amount,
        total_amount=total,
        gstin=_make_gstin(),
        invoice_path="",
        pod_path="",
        signature_type=random.choice(["handwritten", "stamp", "otp_verified"]),
        delivery_timestamp=_format_timestamp(delivery_ts),
        reason_code="chargeback",
        expected_action="ESCALATE_HUMAN",
        ground_truth_notes="Buyer claims non-receipt. POD address points to different city/pincode.",
        _created_ts=created_ts,
        _delivery_ts=delivery_ts,
        is_adversarial=True,
    )


def _generate_messy_scan_case(index: int) -> CaseProfile:
    city, pincode, state = random.choice(INDIAN_CITIES)
    name = _pick_name()
    address = _pick_address(city, pincode, state)
    product, amount = random.choice(PRODUCTS)
    total = int(amount * 1.18)
    created_ts = _random_timestamp()
    delivery_ts = _random_timestamp(month_range=(1, 6))

    return CaseProfile(
        case_id=f"messy_{index:04d}",
        split_name="messy_scans",
        dispute_id=_make_dispute_id(),
        payment_id=_make_payment_id(),
        order_id=_make_order_id(),
        customer_name=name,
        shipping_address=address,
        shipping_city=city,
        shipping_pincode=pincode,
        shipping_state=state,
        pod_address=address,
        pod_pincode=pincode,
        awb_number=_make_awb(),
        courier_name=random.choice(COURIER_NAMES),
        product_name=product,
        product_amount=amount,
        total_amount=total,
        gstin=_make_gstin(),
        invoice_path="",
        pod_path="",
        signature_type=random.choice(["handwritten", "stamp", "otp_verified"]),
        delivery_timestamp=_format_timestamp(delivery_ts),
        reason_code=random.choice(["retrieval", "chargeback"]),
        expected_action="TEST_EXTRACTION_RESILIENCE",
        ground_truth_notes="Skewed, rotated scan with low contrast and messy signature",
        _created_ts=created_ts,
        _delivery_ts=delivery_ts,
    )


def _generate_adversarial_fraud_case(index: int) -> CaseProfile:
    city, pincode, state = random.choice(INDIAN_CITIES)
    name = _pick_name()
    address = _pick_address(city, pincode, state)
    product, amount = random.choice(PRODUCTS)
    total = int(amount * 1.18)
    created_ts = _random_timestamp()
    delivery_ts = _random_timestamp(month_range=(1, 6))
    fraud_type = random.choice(["altered_amount", "fake_stamp", "forged_receipt"])

    return CaseProfile(
        case_id=f"fraud_{index:04d}",
        split_name="adversarial_fraud",
        dispute_id=_make_dispute_id(),
        payment_id=_make_payment_id(),
        order_id=_make_order_id(),
        customer_name=name,
        shipping_address=address,
        shipping_city=city,
        shipping_pincode=pincode,
        shipping_state=state,
        pod_address=address,
        pod_pincode=pincode,
        awb_number=_make_awb(),
        courier_name=random.choice(COURIER_NAMES),
        product_name=product,
        product_amount=amount,
        total_amount=total,
        gstin=_make_gstin(),
        invoice_path="",
        pod_path="",
        signature_type="stamp",
        delivery_timestamp=_format_timestamp(delivery_ts),
        reason_code="fraud",
        expected_action=random.choice(["ESCALATE_HUMAN", "ABANDON"]),
        ground_truth_notes=f"Adversarial case: {fraud_type}. Forged or altered evidence.",
        _created_ts=created_ts,
        _delivery_ts=delivery_ts,
        is_adversarial=True,
    )


def _generate_missing_evidence_case(index: int) -> CaseProfile:
    city, pincode, state = random.choice(INDIAN_CITIES)
    name = _pick_name()
    address = _pick_address(city, pincode, state)
    product, amount = random.choice(PRODUCTS)
    total = int(amount * 1.18)
    created_ts = _random_timestamp()

    return CaseProfile(
        case_id=f"missing_{index:04d}",
        split_name="missing_evidence",
        dispute_id=_make_dispute_id(),
        payment_id=_make_payment_id(),
        order_id=_make_order_id(),
        customer_name=name,
        shipping_address=address,
        shipping_city=city,
        shipping_pincode=pincode,
        shipping_state=state,
        pod_address="",
        pod_pincode="",
        awb_number=_make_awb(),
        courier_name=random.choice(COURIER_NAMES),
        product_name=product,
        product_amount=amount,
        total_amount=total,
        gstin=_make_gstin(),
        invoice_path="",
        pod_path="",
        signature_type="missing",
        delivery_timestamp="",
        reason_code=random.choice(["chargeback", "fraud"]),
        expected_action="ABANDON",
        ground_truth_notes="Logistics provider returned 404 or courier lost the parcel.",
        _created_ts=created_ts,
        _delivery_ts=0,
        has_missing_evidence=True,
    )


GENERATORS = {
    "clean_wins": _generate_clean_win_case,
    "address_mismatches": _generate_address_mismatch_case,
    "messy_scans": _generate_messy_scan_case,
    "adversarial_fraud": _generate_adversarial_fraud_case,
    "missing_evidence": _generate_missing_evidence_case,
}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _ensure_dirs():
    for d in [INVOICES_DIR, PODS_DIR, TEST_SPLITS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _generate_all_cases() -> List[CaseProfile]:
    cases: List[CaseProfile] = []
    for split_name, config in SPLIT_CONFIG.items():
        gen = GENERATORS[split_name]
        for i in range(config["count"]):
            case = gen(i)
            cases.append(case)
    random.shuffle(cases)
    return cases


def _generate_documents(cases: List[CaseProfile]) -> List[CaseProfile]:
    updated = []
    for case in cases:
        invoice_path = INVOICES_DIR / f"{case.case_id}_invoice.pdf"
        _generate_invoice_pdf(case, invoice_path)
        case.invoice_path = str(invoice_path.relative_to(BASE_DIR))

        if case.has_missing_evidence:
            case.pod_path = ""
        else:
            pod_pdf_path = PODS_DIR / f"{case.case_id}_pod.pdf"

            messy = case.split_name == "messy_scans"
            if messy:
                temp_pdf = PODS_DIR / f"{case.case_id}_pod_temp.pdf"
                _generate_pod_pdf(case, temp_pdf)
                pod_img_path = PODS_DIR / f"{case.case_id}_pod.png"
                _apply_messy_transformations(temp_pdf, pod_img_path)
                case.pod_path = str(pod_img_path.relative_to(BASE_DIR))
                temp_pdf.unlink(missing_ok=True)
            else:
                _generate_pod_pdf(case, pod_pdf_path)
                case.pod_path = str(pod_pdf_path.relative_to(BASE_DIR))

        updated.append(case)
    return updated


def _build_ground_truth(cases: List[CaseProfile]) -> dict:
    ground_truth = {
        "metadata": {
            "total_cases": len(cases),
            "splits": {name: cfg["count"] for name, cfg in SPLIT_CONFIG.items()},
        },
        "cases": [],
    }
    for case in cases:
        ground_truth["cases"].append({
            "case_id": case.case_id,
            "split_name": case.split_name,
            "dispute_id": case.dispute_id,
            "payment_id": case.payment_id,
            "order_id": case.order_id,
            "customer_name": case.customer_name,
            "shipping_address": case.shipping_address,
            "shipping_pincode": case.shipping_pincode,
            "pod_address": case.pod_address,
            "pod_pincode": case.pod_pincode,
            "awb_number": case.awb_number,
            "courier_name": case.courier_name,
            "product_name": case.product_name,
            "product_amount": case.product_amount,
            "total_amount": case.total_amount,
            "signature_type": case.signature_type,
            "reason_code": case.reason_code,
            "expected_action": case.expected_action,
            "ground_truth_notes": case.ground_truth_notes,
            "is_adversarial": case.is_adversarial,
            "has_missing_evidence": case.has_missing_evidence,
            "invoice_path": case.invoice_path,
            "pod_path": case.pod_path,
        })
    return ground_truth


def _write_test_splits(cases: List[CaseProfile]):
    for split_name in SPLIT_CONFIG:
        split_cases = [c for c in cases if c.split_name == split_name]
        split_data = []
        for c in split_cases:
            split_data.append({
                "case_id": c.case_id,
                "dispute_id": c.dispute_id,
                "payment_id": c.payment_id,
                "order_id": c.order_id,
                "customer_name": c.customer_name,
                "shipping_address": c.shipping_address,
                "pod_address": c.pod_address,
                "awb_number": c.awb_number,
                "courier_name": c.courier_name,
                "product_name": c.product_name,
                "total_amount": c.total_amount,
                "signature_type": c.signature_type,
                "reason_code": c.reason_code,
                "expected_action": c.expected_action,
                "invoice_path": c.invoice_path,
                "pod_path": c.pod_path,
            })
        output_path = TEST_SPLITS_DIR / f"{split_name}.json"
        with open(output_path, "w") as f:
            json.dump(split_data, f, indent=2)


def generate_dataset():
    """Main entry point: generate 200-case synthetic evaluation dataset."""
    print("Ensuring directories exist...")
    _ensure_dirs()

    print("Generating 200 case profiles...")
    cases = _generate_all_cases()
    print(f"  Created {len(cases)} cases across {len(SPLIT_CONFIG)} splits")

    print("Generating invoice and POD documents...")
    cases = _generate_documents(cases)
    print(f"  Generated {len(cases)} invoice/POD file pairs")

    print("Writing ground truth JSON...")
    gt = _build_ground_truth(cases)
    gt_path = DATA_DIR / "synthetic_ground_truth.json"
    with open(gt_path, "w") as f:
        json.dump(gt, f, indent=2)
    print(f"  Written to {gt_path}")

    print("Writing test split files...")
    _write_test_splits(cases)
    for split_name in SPLIT_CONFIG:
        count = len([c for c in cases if c.split_name == split_name])
        print(f"  {split_name}: {count} cases")

    print("\nDataset generation complete.")
    print(f"  Invoices: {INVOICES_DIR}")
    print(f"  PODs: {PODS_DIR}")
    print(f"  Ground truth: {gt_path}")


if __name__ == "__main__":
    generate_dataset()
