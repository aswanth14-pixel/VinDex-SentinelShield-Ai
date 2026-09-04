"""
Benchmark Evaluation Runner for SentinelShield AI.

Executes the batch evaluation suite against 200 synthetic cases
without requiring a running web server.
"""

import asyncio
import json
import time
from pathlib import Path

from packages.agents.contradiction_verifier import ContradictionVerifier
from packages.agents.vision_extractor import VisionExtractor
from packages.agents.win_scorer import evaluate
from packages.core.config import settings
from packages.eval.metrics import BenchmarkMetrics, compute_metrics, metrics_to_dict
from packages.integrations.mock_courier import MockCourier
from packages.integrations.mock_store import MockStore


BASE_DIR = Path(__file__).resolve().parent.parent.parent
GROUND_TRUTH_PATH = BASE_DIR / "data" / "synthetic_ground_truth.json"
RESULTS_DIR = BASE_DIR / "data"


async def run_benchmark() -> BenchmarkMetrics:
    """Execute the full 200-case benchmark evaluation.

    Returns:
        BenchmarkMetrics with all computed performance metrics.
    """
    print("Loading synthetic dataset...")
    with open(GROUND_TRUTH_PATH) as f:
        dataset = json.load(f)

    cases = dataset["cases"]
    print(f"Loaded {len(cases)} cases across {len(dataset['metadata']['splits'])} splits")

    store = MockStore()
    courier = MockCourier()
    extractor = VisionExtractor(mock_mode=True)
    verifier = ContradictionVerifier()

    results = []
    total_start = time.perf_counter()

    for i, case in enumerate(cases):
        case_start = time.perf_counter()

        if (i + 1) % 50 == 0 or i == 0:
            print(f"  Processing case {i + 1}/{len(cases)}...")

        pod_path, invoice_path = courier.get_documents(case["order_id"])

        if pod_path is None:
            results.append({
                "case_id": case["case_id"],
                "split_name": case["split_name"],
                "expected_action": case["expected_action"],
                "predicted_action": "ABANDON",
                "win_probability": 0.0,
                "extraction": {},
                "contradiction": {},
                "elapsed_seconds": 0.0,
                "amount_paise": case["total_amount"] * 100,
                "ground_truth": case,
            })
            continue

        extraction = await extractor.extract(pod_path)

        contradiction = await verifier.verify(
            extracted=extraction,
            expected_address=case["shipping_address"],
            expected_pincode=case["shipping_pincode"],
            expected_recipient=case["customer_name"],
        )

        evaluation = evaluate(
            dispute_id=case["dispute_id"],
            reason_code=case["reason_code"],
            amount_paise=case["total_amount"] * 100,
            address_similarity_score=contradiction.address_similarity_score,
            confidence_score=extraction.confidence_score,
            signature_present=extraction.signature_present,
            contradictions_count=len(contradiction.detected_contradictions),
            detected_contradictions=contradiction.detected_contradictions,
        )

        elapsed = time.perf_counter() - case_start

        results.append({
            "case_id": case["case_id"],
            "split_name": case["split_name"],
            "expected_action": case["expected_action"],
            "predicted_action": evaluation.recommended_action,
            "win_probability": evaluation.win_probability,
            "extraction": extraction.model_dump(),
            "contradiction": {
                "address_match": contradiction.address_match,
                "address_similarity": contradiction.address_similarity_score,
                "is_adversarial": contradiction.is_adversarial,
            },
            "elapsed_seconds": elapsed,
            "amount_paise": case["total_amount"] * 100,
            "ground_truth": case,
        })

    total_elapsed = time.perf_counter() - total_start
    print(f"\nBenchmark completed in {total_elapsed:.2f}s")
    print(f"Average latency: {total_elapsed / len(cases):.3f}s per case")

    metrics = compute_metrics(results)

    results_path = RESULTS_DIR / "benchmark_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "metrics": metrics_to_dict(metrics),
            "results": results,
        }, f, indent=2)
    print(f"Results saved to {results_path}")

    return metrics


def generate_markdown_report(metrics: BenchmarkMetrics) -> str:
    """Generate a Markdown report from benchmark metrics."""
    m = metrics_to_dict(metrics)

    report = """# SentinelShield AI Benchmark Results

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Cases Evaluated | {total} |
| Overall Accuracy | {accuracy:.1%} |
| Mean Processing Latency | {latency:.3f}s |
| Max Processing Latency | {max_latency:.3f}s |

## Extraction Performance

| Field | Precision | Recall |
|-------|-----------|--------|
| AWB Number | {awb_p:.1%} | {awb_r:.1%} |
| Address | {addr_p:.1%} | {addr_r:.1%} |
| Signature Presence | {sig_p:.1%} | {sig_r:.1%} |

## Address Contradiction Detection

| Metric | Value |
|--------|-------|
| True Positive Rate | {tpr:.1%} |
| False Positive Rate | {fpr:.1%} |

## Representment Performance

| Metric | Value |
|--------|-------|
| Precision (Correct Submissions / All Submissions) | {rep_p:.1%} |
| Recall (Correct Submissions / Winnable Cases) | {rep_r:.1%} |

## Financial Yield

| Metric | Value |
|--------|-------|
| Net Yield Recovered | Rs. {yield_inr:,.2f} |
| Total Disputed Amount | Rs. {disputed_inr:,.2f} |
| Yield Recovery Rate | {yield_rate:.1%} |

## Split Breakdown

| Split | Total Cases | Correct | Accuracy |
|-------|-------------|---------|----------|
""".format(
        total=m["total_cases"],
        accuracy=m["accuracy"],
        latency=m["latency"]["mean_seconds"],
        max_latency=m["latency"]["max_seconds"],
        awb_p=m["extraction"]["awb_precision"],
        awb_r=m["extraction"]["awb_recall"],
        addr_p=m["extraction"]["address_precision"],
        addr_r=m["extraction"]["address_recall"],
        sig_p=m["extraction"]["signature_precision"],
        sig_r=m["extraction"]["signature_recall"],
        tpr=m["address_contradiction"]["true_positive_rate"],
        fpr=m["address_contradiction"]["false_positive_rate"],
        rep_p=m["representment"]["precision"],
        rep_r=m["representment"]["recall"],
        yield_inr=m["financial"]["net_yield_inr"],
        disputed_inr=m["financial"]["total_disputed_inr"],
        yield_rate=m["financial"]["yield_rate"],
    )

    for split, data in m.get("split_breakdown", {}).items():
        report += f"| {split} | {data['total']} | {data['correct']} | {data['accuracy']:.1%} |\n"

    report += """
## Target Validation

| Target | Threshold | Actual | Status |
|--------|-----------|--------|--------|
| Extraction Precision | >= 90% | {awb_p:.1%} | {awb_status} |
| Address Contradiction TPR | >= 80% | {tpr:.1%} | {tpr_status} |
| Mean Latency | < 15s | {latency:.3f}s | {lat_status} |

---
*Generated by SentinelShield AI Benchmark Runner*
""".format(
        awb_p=m["extraction"]["awb_precision"],
        tpr=m["address_contradiction"]["true_positive_rate"],
        latency=m["latency"]["mean_seconds"],
        awb_status="PASS" if m["extraction"]["awb_precision"] >= 0.90 else "NEEDS IMPROVEMENT",
        tpr_status="PASS" if m["address_contradiction"]["true_positive_rate"] >= 0.80 else "NEEDS IMPROVEMENT",
        lat_status="PASS" if m["latency"]["mean_seconds"] < 15.0 else "NEEDS IMPROVEMENT",
    )

    return report


if __name__ == "__main__":
    metrics = asyncio.run(run_benchmark())

    report = generate_markdown_report(metrics)
    report_path = BASE_DIR / "BENCHMARK_RESULTS.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")

    print("\n=== Key Metrics ===")
    m = metrics_to_dict(metrics)
    print(f"Accuracy: {m['accuracy']:.1%}")
    print(f"AWB Precision: {m['extraction']['awb_precision']:.1%}")
    print(f"Address TPR: {m['address_contradiction']['true_positive_rate']:.1%}")
    print(f"Mean Latency: {m['latency']['mean_seconds']:.3f}s")
    print(f"Net Yield: Rs. {m['financial']['net_yield_inr']:,.2f}")
