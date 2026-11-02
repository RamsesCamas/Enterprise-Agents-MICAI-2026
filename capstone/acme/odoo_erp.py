"""Optional backend: the same ERP methods, against a real Odoo 19.

NOT TESTED against a live Odoo yet. Use the local ERP if anything here fails.

    export ODOO_URL=http://localhost:8069 ODOO_DB=acme ODOO_API_KEY=...
    uv run python -m acme.odoo_erp seed        # load data/*.jsonl into Odoo once
    ACME_BACKEND=odoo uv run streamlit run app.py

Three things Odoo teaches that the local ERP cannot:
1. Odoo's API is generic: any method on any model (/json/2/<model>/<method>).
   Our MCP servers are what reduce it to a few safe tools.
2. Odoo has no idempotency keys. We keep our own record of finished writes,
   and we turn "add 5 units" into "set stock to 62", so a retry does no harm.
3. Who may see what belongs in Odoo itself (users, groups, record rules).
   If the API key belongs to an administrator, every rule is skipped.
"""
import json
import os
import sys

import httpx

from acme.erp import DATA_DIR, RUNTIME_DIR, ERPError, read_jsonl

INTENTS_FILE = RUNTIME_DIR / "odoo_writes.json"


class OdooERP:
    def __init__(self, url, database, api_key):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"bearer {api_key}", "X-Odoo-Database": database}

    @classmethod
    def from_environment(cls):
        return cls(os.environ["ODOO_URL"], os.environ["ODOO_DB"], os.environ["ODOO_API_KEY"])

    def call(self, model, method, **arguments):
        try:
            response = httpx.post(f"{self.url}/json/2/{model}/{method}", json=arguments,
                                  headers=self.headers, timeout=20)
        except httpx.TimeoutException:
            raise ERPError("timeout", "Odoo did not answer in time", retryable=True)
        if response.status_code in (502, 503, 504):
            raise ERPError("unavailable", f"Odoo returned {response.status_code}", retryable=True)
        if response.status_code >= 400:
            raise ERPError("odoo_error", response.text[:200])
        return response.json()

    # ---------- reads ----------

    def _product_row(self, sku):
        rows = self.call("product.product", "search_read", domain=[["default_code", "=", sku]],
                         fields=["id", "default_code", "name", "categ_id", "list_price", "qty_available"], limit=1)
        if not rows:
            raise ERPError("not_found", f"Product {sku} not found")
        return rows[0]

    @staticmethod
    def _as_product(row):
        return {"sku": row["default_code"], "name": row["name"], "category": row["categ_id"][1],
                "price": row["list_price"], "stock": int(row["qty_available"])}

    def get_product(self, sku):
        return self._as_product(self._product_row(sku))

    def find_products(self, category=None, max_stock=None):
        domain = [["default_code", "=like", "SKU-%"]]
        if category:
            domain.append(["categ_id.name", "=", category])
        rows = self.call("product.product", "search_read", domain=domain,
                         fields=["default_code", "name", "categ_id", "list_price", "qty_available"])
        products = [self._as_product(row) for row in rows]
        if max_stock is not None:
            products = [p for p in products if p["stock"] <= max_stock]
        return products

    def get_customer(self, customer_id):
        rows = self.call("res.partner", "search_read", domain=[["ref", "=", customer_id]],
                         fields=["ref", "name", "email", "phone", "comment", "city"], limit=1)
        if not rows:
            raise ERPError("not_found", f"Customer {customer_id} not found")
        row = rows[0]
        return {"id": row["ref"], "name": row["name"], "email": row["email"], "phone": row["phone"],
                "region": row["city"], "tier": "", "notes": row["comment"] or ""}

    def get_invoice(self, invoice_id):
        rows = self.call("account.move", "search_read", domain=[["ref", "=", invoice_id]],
                         fields=["ref", "partner_id", "state", "payment_state", "amount_total"], limit=1)
        if not rows:
            raise ERPError("not_found", f"Invoice {invoice_id} not found")
        row = rows[0]
        status = row["state"]
        if row["state"] == "posted":
            status = "paid" if row["payment_state"] in ("paid", "in_payment") else "issued"
        return {"id": row["ref"], "customer_id": row["partner_id"][1], "status": status,
                "total": row["amount_total"], "refunded": 0.0}

    # ---------- writes ----------

    def _finished_writes(self):
        if INTENTS_FILE.exists():
            return json.loads(INTENTS_FILE.read_text())
        return {}

    def _remember(self, key, value):
        RUNTIME_DIR.mkdir(exist_ok=True)
        writes = self._finished_writes()
        writes[key] = value
        INTENTS_FILE.write_text(json.dumps(writes, indent=1))

    def adjust_stock(self, sku, delta, reason, idempotency_key=None):
        row = self._product_row(sku)
        writes = self._finished_writes()

        # Decide the TARGET once per key. A retry sets the same target again: no double count.
        if idempotency_key and idempotency_key in writes:
            target = writes[idempotency_key]["target"]
        else:
            target = int(row["qty_available"]) + delta
            if target < 0:
                raise ERPError("insufficient_stock", f"Stock is {int(row['qty_available'])}, cannot apply {delta}")
            if idempotency_key:
                self._remember(idempotency_key, {"target": target})

        if int(row["qty_available"]) == target:
            return {"sku": sku, "stock": target, "replayed": True}

        context = {"inventory_mode": True}
        location = self.call("stock.warehouse", "search_read", domain=[], fields=["lot_stock_id"], limit=1)[0]
        quant_ids = self.call("stock.quant", "search", domain=[["product_id", "=", row["id"]],
                                                                ["location_id", "=", location["lot_stock_id"][0]]])
        if quant_ids:
            self.call("stock.quant", "write", ids=quant_ids, vals={"inventory_quantity": target}, context=context)
        else:
            quant_ids = self.call("stock.quant", "create", vals_list=[{
                "product_id": row["id"], "location_id": location["lot_stock_id"][0], "inventory_quantity": target}],
                context=context)
        self.call("stock.quant", "action_apply_inventory", ids=quant_ids, context=context)
        return {"sku": sku, "stock": target}

    def create_refund(self, invoice_id, amount, reason, idempotency_key=None):
        if idempotency_key and idempotency_key in self._finished_writes():
            return {**self._finished_writes()[idempotency_key], "replayed": True}
        invoice = self.get_invoice(invoice_id)
        if invoice["status"] != "paid":
            raise ERPError("invalid_state", "Only paid invoices can be refunded")
        move = self.call("account.move", "search_read", domain=[["ref", "=", invoice_id]],
                         fields=["id", "partner_id"], limit=1)[0]
        refund_ids = self.call("account.move", "create", vals_list=[{
            "move_type": "out_refund", "partner_id": move["partner_id"][0], "reversed_entry_id": move["id"],
            "invoice_line_ids": [[0, 0, {"name": f"Refund {invoice_id}: {reason}", "quantity": 1, "price_unit": amount}]],
        }])
        self.call("account.move", "action_post", ids=refund_ids)
        reply = {"invoice_id": invoice_id, "refunded": amount}
        if idempotency_key:
            self._remember(idempotency_key, reply)
        return reply


def seed():
    """Load data/*.jsonl into an empty Odoo database (apps: Inventory, Invoicing)."""
    odoo = OdooERP.from_environment()
    categories = {}
    for product in read_jsonl(DATA_DIR / "products.jsonl"):
        category = product["category"]
        if category not in categories:
            categories[category] = odoo.call("product.category", "create", vals_list=[{"name": category}])[0]
        odoo.call("product.product", "create", vals_list=[{
            "name": product["name"], "default_code": product["sku"], "list_price": product["price"],
            "categ_id": categories[category], "type": "consu", "is_storable": True}])
        if product["stock"]:
            odoo.adjust_stock(product["sku"], product["stock"], "restock")
    for customer in read_jsonl(DATA_DIR / "customers.jsonl"):
        odoo.call("res.partner", "create", vals_list=[{
            "name": customer["name"], "ref": customer["id"], "email": customer["email"],
            "phone": customer["phone"], "city": customer["region"], "comment": customer["notes"]}])
    print("Products and customers loaded. Create the invoices in Odoo by hand if you need them.")


if __name__ == "__main__":
    if sys.argv[1:] == ["seed"]:
        seed()
