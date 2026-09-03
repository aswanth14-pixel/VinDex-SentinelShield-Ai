"""
Mock e-commerce store connector for SentinelShield AI.

Provides synthetic customer metadata, shipping addresses, and order line items
for evaluation and testing without requiring live Shopify/WooCommerce API access.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_ground_truth.json"


@dataclass
class OrderLineItem:
    product_name: str
    quantity: int
    unit_price: int
    total_price: int


@dataclass
class StoreOrder:
    order_id: str
    payment_id: str
    customer_name: str
    shipping_address: str
    shipping_pincode: str
    line_items: List[OrderLineItem]
    invoice_id: str
    total_amount: int


class MockStore:
    """Simulates an e-commerce store API (Shopify/WooCommerce) for offline testing."""

    def __init__(self, ground_truth_path: Optional[str] = None):
        self._ground_truth = self._load_ground_truth(ground_truth_path or GROUND_TRUTH_PATH)

    def _load_ground_truth(self, path: str) -> dict:
        with open(path) as f:
            data = json.load(f)
        return {case["payment_id"]: case for case in data["cases"]}

    def get_order_by_payment_id(self, payment_id: str) -> Optional[StoreOrder]:
        """Retrieve order metadata by Razorpay payment ID."""
        case = self._ground_truth.get(payment_id)
        if case is None:
            return None

        line_item = OrderLineItem(
            product_name=case["product_name"],
            quantity=1,
            unit_price=case["product_amount"],
            total_price=case["product_amount"],
        )

        return StoreOrder(
            order_id=case["order_id"],
            payment_id=case["payment_id"],
            customer_name=case["customer_name"],
            shipping_address=case["shipping_address"],
            shipping_pincode=case["shipping_pincode"],
            line_items=[line_item],
            invoice_id=f"INV-{case['case_id'].upper()}",
            total_amount=case["total_amount"],
        )

    def get_order_by_id(self, order_id: str) -> Optional[StoreOrder]:
        """Retrieve order metadata by store order ID."""
        for payment_id, case in self._ground_truth.items():
            if case["order_id"] == order_id:
                return self.get_order_by_payment_id(payment_id)
        return None
