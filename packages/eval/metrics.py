"""
Evaluation Metrics for SentinelShield AI Benchmark.

Computes extraction precision/recall, address contradiction accuracy,
representment metrics, and cost-sensitive financial yield.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CaseResult:
    case_id: str
    split_name: str
    expected_action: str
    predicted_action: str
    win_probability: float
    extraction_accuracy: Dict[str, bool]
    address_contradiction_detected: bool
    address_contradiction_expected: bool
    elapsed_seconds: float
    amount_paise: int
    is_correct: bool = False
    is_submitted: bool = False
    is_winnable: bool = False


@dataclass
class BenchmarkMetrics:
    total_cases: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0

    extraction_awb_precision: float = 0.0
    extraction_awb_recall: float = 0.0
    extraction_address_precision: float = 0.0
    extraction_address_recall: float = 0.0
    extraction_signature_precision: float = 0.0
    extraction_signature_recall: float = 0.0

    address_contradiction_tpr: float = 0.0
    address_contradiction_fpr: float = 0.0

    representment_precision: float = 0.0
    representment_recall: float = 0.0

    net_financial_yield_paise: int = 0
    total_disputed_paise: int = 0
    financial_yield_rate: float = 0.0

    mean_latency_seconds: float = 0.0
    max_latency_seconds: float = 0.0

    split_breakdown: Dict[str, dict] = field(default_factory=dict)


def _extract_accuracy(extraction: dict, ground_truth: dict) -> Dict[str, bool]:
    """Compare extracted fields against ground truth."""
    awb_match = extraction.get("awb_number") == ground_truth.get("awb_number")
    address_match = (
        ground_truth.get("pod_address", "").lower() in
        extraction.get("delivery_address", "").lower()
    ) or (
        extraction.get("delivery_address", "").lower() in
        ground_truth.get("pod_address", "").lower()
    )
    sig_present = extraction.get("signature_present", False)
    sig_expected = ground_truth.get("signature_type", "missing") != "missing"
    signature_match = sig_present == sig_expected

    return {
        "awb": awb_match,
        "address": address_match,
        "signature": signature_match,
    }


def compute_metrics(results: List[dict]) -> BenchmarkMetrics:
    """Compute all benchmark metrics from a list of case results.

    Args:
        results: List of dicts with keys:
            case_id, split_name, expected_action, predicted_action,
            win_probability, extraction (dict), contradiction (dict),
            elapsed_seconds, ground_truth (dict)

    Returns:
        BenchmarkMetrics with all computed metrics.
    """
    metrics = BenchmarkMetrics()
    metrics.total_cases = len(results)

    if metrics.total_cases == 0:
        return metrics

    correct = 0
    submitted = 0
    winnable = 0
    correct_submitted = 0
    tp_contradiction = 0
    fp_contradiction = 0
    fn_contradiction = 0
    tn_contradiction = 0

    awb_tp = 0
    awb_fn = 0
    addr_tp = 0
    addr_fn = 0
    sig_tp = 0
    sig_fn = 0

    total_latency = 0.0
    max_latency = 0.0
    total_yield = 0
    total_disputed = 0

    split_counts: Dict[str, int] = {}
    split_correct: Dict[str, int] = {}

    for r in results:
        case_id = r.get("case_id", "")
        split = r.get("split_name", "unknown")
        expected = r.get("expected_action", "")
        predicted = r.get("predicted_action", "")
        win_prob = r.get("win_probability", 0.0)
        elapsed = r.get("elapsed_seconds", 0.0)
        amount = r.get("amount_paise", 0)
        gt = r.get("ground_truth", {})
        extraction = r.get("extraction", {})
        contradiction = r.get("contradiction", {})

        is_correct = (expected == predicted) if expected != "TEST_EXTRACTION_RESILIENCE" else True
        is_submitted = predicted == "AUTO_SUBMIT"
        is_winnable = expected == "AUTO_SUBMIT"

        if is_correct:
            correct += 1
        if is_submitted:
            submitted += 1
        if is_winnable:
            winnable += 1
        if is_submitted and is_winnable:
            correct_submitted += 1

        addr_expected = gt.get("is_adversarial", False)
        addr_detected = contradiction.get("is_adversarial", False)

        if addr_expected and addr_detected:
            tp_contradiction += 1
        elif addr_expected and not addr_detected:
            fn_contradiction += 1
        elif not addr_expected and addr_detected:
            fp_contradiction += 1
        else:
            tn_contradiction += 1

        acc = _extract_accuracy(extraction, gt) if gt else {"awb": False, "address": False, "signature": False}
        if gt:
            if acc["awb"]:
                awb_tp += 1
            awb_fn += 1

            if acc["address"]:
                addr_tp += 1
            addr_fn += 1

            if acc["signature"]:
                sig_tp += 1
            sig_fn += 1

        total_latency += elapsed
        max_latency = max(max_latency, elapsed)
        total_disputed += amount

        if is_submitted and is_winnable:
            total_yield += amount
        elif is_submitted and not is_winnable:
            total_yield -= int(amount * 0.05)

        split_counts[split] = split_counts.get(split, 0) + 1
        if is_correct:
            split_correct[split] = split_correct.get(split, 0) + 1

    metrics.correct_predictions = correct
    metrics.accuracy = correct / metrics.total_cases

    metrics.extraction_awb_precision = awb_tp / max(awb_tp + 0, 1)
    metrics.extraction_awb_recall = awb_tp / max(awb_fn, 1)
    metrics.extraction_address_precision = addr_tp / max(addr_tp + 0, 1)
    metrics.extraction_address_recall = addr_tp / max(addr_fn, 1)
    metrics.extraction_signature_precision = sig_tp / max(sig_tp + 0, 1)
    metrics.extraction_signature_recall = sig_tp / max(sig_fn, 1)

    metrics.address_contradiction_tpr = tp_contradiction / max(tp_contradiction + fn_contradiction, 1)
    metrics.address_contradiction_fpr = fp_contradiction / max(fp_contradiction + tn_contradiction, 1)

    metrics.representment_precision = correct_submitted / max(submitted, 1)
    metrics.representment_recall = correct_submitted / max(winnable, 1)

    metrics.net_financial_yield_paise = total_yield
    metrics.total_disputed_paise = total_disputed
    metrics.financial_yield_rate = total_yield / max(total_disputed, 1)

    metrics.mean_latency_seconds = total_latency / metrics.total_cases
    metrics.max_latency_seconds = max_latency

    for split in split_counts:
        sc = split_correct.get(split, 0)
        metrics.split_breakdown[split] = {
            "total": split_counts[split],
            "correct": sc,
            "accuracy": sc / split_counts[split],
        }

    return metrics


def metrics_to_dict(m: BenchmarkMetrics) -> dict:
    """Convert BenchmarkMetrics to a JSON-serializable dict."""
    return {
        "total_cases": m.total_cases,
        "accuracy": round(m.accuracy, 4),
        "extraction": {
            "awb_precision": round(m.extraction_awb_precision, 4),
            "awb_recall": round(m.extraction_awb_recall, 4),
            "address_precision": round(m.extraction_address_precision, 4),
            "address_recall": round(m.extraction_address_recall, 4),
            "signature_precision": round(m.extraction_signature_precision, 4),
            "signature_recall": round(m.extraction_signature_recall, 4),
        },
        "address_contradiction": {
            "true_positive_rate": round(m.address_contradiction_tpr, 4),
            "false_positive_rate": round(m.address_contradiction_fpr, 4),
        },
        "representment": {
            "precision": round(m.representment_precision, 4),
            "recall": round(m.representment_recall, 4),
        },
        "financial": {
            "net_yield_paise": m.net_financial_yield_paise,
            "net_yield_inr": round(m.net_financial_yield_paise / 100, 2),
            "total_disputed_paise": m.total_disputed_paise,
            "total_disputed_inr": round(m.total_disputed_paise / 100, 2),
            "yield_rate": round(m.financial_yield_rate, 4),
        },
        "latency": {
            "mean_seconds": round(m.mean_latency_seconds, 4),
            "max_seconds": round(m.max_latency_seconds, 4),
        },
        "split_breakdown": m.split_breakdown,
    }
