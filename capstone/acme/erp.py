"""The Acme ERP used by the MCP servers.

Same class as in the labs, plus a state file: the read server and the write
server are separate processes, so they share the ERP through runtime/state.json.
"""
import json
import os
from pathlib import Path

CAPSTONE = Path(__file__).resolve().parent.parent
DATA_DIR = CAPSTONE / "data"
RUNTIME_DIR = CAPSTONE / "runtime"
STATE_FILE = RUNTIME_DIR / "state.json"


def read_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


class ERPError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class AcmeERP:
    def __init__(self):
        self.products = {row["sku"]: row for row in read_jsonl(DATA_DIR / "products.jsonl")}
        self.customers = {row["id"]: row for row in read_jsonl(DATA_DIR / "customers.jsonl")}
        self.invoices = {row["id"]: row for row in read_jsonl(DATA_DIR / "invoices.jsonl")}
        self.movements = []
        self.refunds = []
        self.saved_replies = {}
        self.pending_failures = []

    # ---------- shared state between processes ----------

    @classmethod
    def load(cls):
        erp = cls()
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            erp.products = state["products"]
            erp.invoices = state["invoices"]
            erp.movements = state["movements"]
            erp.refunds = state["refunds"]
            erp.saved_replies = state["saved_replies"]
            erp.pending_failures = state["pending_failures"]
        return erp

    def save(self):
        RUNTIME_DIR.mkdir(exist_ok=True)
        state = {
            "products": self.products,
            "invoices": self.invoices,
            "movements": self.movements,
            "refunds": self.refunds,
            "saved_replies": self.saved_replies,
            "pending_failures": self.pending_failures,
        }
        STATE_FILE.write_text(json.dumps(state, indent=1))

    # ---------- simulated outages ----------

    def fail_next(self, kind, times=1):
        """kind: 'unavailable', 'timeout' or 'lost_response'."""
        for _ in range(times):
            self.pending_failures.append(kind)

    def _check_failures(self):
        if not self.pending_failures:
            return False
        kind = self.pending_failures.pop(0)
        self.save()
        if kind == "unavailable":
            raise ERPError("unavailable", "503 Service unavailable", retryable=True)
        if kind == "timeout":
            raise ERPError("timeout", "No answer after 5 seconds", retryable=True)
        return kind == "lost_response"

    # ---------- reads ----------

    def get_product(self, sku):
        self._check_failures()
        if sku not in self.products:
            raise ERPError("not_found", f"Product {sku} not found")
        return dict(self.products[sku])

    def find_products(self, category=None, max_stock=None):
        self._check_failures()
        found = []
        for product in self.products.values():
            if category is not None and product["category"] != category:
                continue
            if max_stock is not None and product["stock"] > max_stock:
                continue
            found.append(dict(product))
        return found

    def get_customer(self, customer_id):
        self._check_failures()
        if customer_id not in self.customers:
            raise ERPError("not_found", f"Customer {customer_id} not found")
        return dict(self.customers[customer_id])

    def get_invoice(self, invoice_id):
        self._check_failures()
        if invoice_id not in self.invoices:
            raise ERPError("not_found", f"Invoice {invoice_id} not found")
        return dict(self.invoices[invoice_id])

    # ---------- writes: applied once per idempotency key ----------

    def adjust_stock(self, sku, delta, reason, idempotency_key=None):
        lose_reply = self._check_failures()
        if idempotency_key in self.saved_replies:
            return {**self.saved_replies[idempotency_key], "replayed": True}

        if sku not in self.products:
            raise ERPError("not_found", f"Product {sku} not found")
        product = self.products[sku]
        if product["stock"] + delta < 0:
            raise ERPError("insufficient_stock", f"Stock is {product['stock']}, cannot apply {delta}")
        product["stock"] += delta
        self.movements.append({"sku": sku, "delta": delta, "reason": reason})
        reply = {"sku": sku, "stock": product["stock"]}
        self._finish_write(idempotency_key, reply, lose_reply)
        return reply

    def create_refund(self, invoice_id, amount, reason, idempotency_key=None):
        lose_reply = self._check_failures()
        if idempotency_key in self.saved_replies:
            return {**self.saved_replies[idempotency_key], "replayed": True}

        if invoice_id not in self.invoices:
            raise ERPError("not_found", f"Invoice {invoice_id} not found")
        invoice = self.invoices[invoice_id]
        if invoice["status"] != "paid":
            raise ERPError("invalid_state", "Only paid invoices can be refunded")
        available = invoice["total"] - invoice["refunded"]
        if amount > available:
            raise ERPError("exceeds_refundable", f"Refundable balance is {available}")
        invoice["refunded"] += amount
        self.refunds.append({"invoice_id": invoice_id, "amount": amount, "reason": reason})
        reply = {"invoice_id": invoice_id, "refunded": amount, "remaining": available - amount}
        self._finish_write(idempotency_key, reply, lose_reply)
        return reply

    def _finish_write(self, idempotency_key, reply, lose_reply):
        if idempotency_key:
            self.saved_replies[idempotency_key] = reply
        self.save()
        if lose_reply:
            raise ERPError("bad_gateway", "502 Connection reset. The write may have been applied.", retryable=True)


def open_erp():
    """The backend the servers use: the local ERP, or Odoo when ACME_BACKEND=odoo."""
    if os.environ.get("ACME_BACKEND") == "odoo":
        from acme.odoo_erp import OdooERP
        return OdooERP.from_environment()
    return AcmeERP.load()


def reset():
    if STATE_FILE.exists():
        STATE_FILE.unlink()
