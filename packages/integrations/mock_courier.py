"""
Mock courier/logistics connector for SentinelShield AI.

Simulates Shiprocket, Delhivery, and other courier APIs for offline evaluation.
Returns AWB tracking data, delivery status, and file paths to generated POD documents.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_ground_truth.json"


@dataclass
class CourierDocument:
    """Represents a retrieved courier document (invoice PDF or POD image)."""
    file_path: str
    file_exists: bool


@dataclass
class CourierShipment:
    awb_number: str
    courier_name: str
    order_id: str
    delivery_status: str
    delivery_timestamp: str
    invoice: CourierDocument
    pod: CourierDocument


class MockCourier:
    """Simulates a courier/logistics API for offline testing."""

    def __init__(self, ground_truth_path: Optional[str] = None):
        self._ground_truth = self._load_ground_truth(ground_truth_path or GROUND_TRUTH_PATH)
        self._base_dir = Path(__file__).resolve().parent.parent.parent

    def _load_ground_truth(self, path: str) -> dict:
        with open(path) as f:
            data = json.load(f)
        return {case["order_id"]: case for case in data["cases"]}

    def get_shipment_by_order_id(self, order_id: str) -> Optional[CourierShipment]:
        """Retrieve shipment tracking and documents by order ID."""
        case = self._ground_truth.get(order_id)
        if case is None:
            return None

        invoice_path = self._base_dir / case["invoice_path"] if case["invoice_path"] else None
        pod_path = self._base_dir / case["pod_path"] if case["pod_path"] else None

        return CourierShipment(
            awb_number=case["awb_number"],
            courier_name=case["courier_name"],
            order_id=case["order_id"],
            delivery_status="delivered" if case["pod_path"] else "not_found",
            delivery_timestamp=case.get("delivery_timestamp", ""),
            invoice=CourierDocument(
                file_path=str(invoice_path) if invoice_path else "",
                file_exists=invoice_path.exists() if invoice_path else False,
            ),
            pod=CourierDocument(
                file_path=str(pod_path) if pod_path else "",
                file_exists=pod_path.exists() if pod_path else False,
            ),
        )

    def get_documents(self, order_id: str):
        """Convenience method: returns (pod_path, invoice_path) tuple.

        Returns (None, None) if order not found or documents missing.
        """
        shipment = self.get_shipment_by_order_id(order_id)
        if shipment is None:
            return None, None

        pod_path = shipment.pod.file_path if shipment.pod.file_exists else None
        invoice_path = shipment.invoice.file_path if shipment.invoice.file_exists else None
        return pod_path, invoice_path
