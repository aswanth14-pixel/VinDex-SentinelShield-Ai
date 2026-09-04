"""
Evaluation Routes.

Exposes on-demand benchmark evaluation trigger endpoint
and retrieval of benchmark results.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter()

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
BENCHMARK_RESULTS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "BENCHMARK_RESULTS.md"


@router.post("/eval/benchmark")
async def trigger_benchmark():
    """Trigger a full 200-case benchmark evaluation run.

    Returns the computed metrics after completion.
    """
    from packages.eval.run_benchmark import run_benchmark, metrics_to_dict

    metrics = await run_benchmark()
    return {
        "status": "completed",
        "metrics": metrics_to_dict(metrics),
    }


@router.get("/eval/results")
async def get_results():
    """Retrieve the latest benchmark results JSON."""
    results_path = RESULTS_DIR / "benchmark_results.json"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="No benchmark results found")

    import json
    with open(results_path) as f:
        data = json.load(f)

    return data


@router.get("/eval/report")
async def get_report():
    """Retrieve the latest benchmark report as Markdown."""
    if not BENCHMARK_RESULTS_PATH.exists():
        raise HTTPException(status_code=404, detail="No benchmark report found")

    return FileResponse(
        path=str(BENCHMARK_RESULTS_PATH),
        media_type="text/markdown",
        filename="BENCHMARK_RESULTS.md",
    )
