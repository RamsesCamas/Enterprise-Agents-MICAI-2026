"""MCP server: read-only access to Acme.

Started by the client with one person's token. Everything it returns is
already filtered for that person: regions, contact data, documents.
"""
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from acme.erp import DATA_DIR, ERPError, open_erp, read_jsonl
from acme.identity import person_for_token

person = person_for_token(os.environ.get("ACME_TOKEN"))
server = MCPServer("acme-read", version="1.0.0")
read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)

Sku = Annotated[str, Field(pattern=r"^SKU-[0-9]{3}$", description="For example SKU-007")]
CustomerId = Annotated[str, Field(pattern=r"^C-[0-9]{4}$", description="For example C-0001")]
InvoiceId = Annotated[str, Field(pattern=r"^INV-[0-9]{4}$", description="For example INV-0003")]
Category = Literal["computo", "perifericos", "mobiliario", "redes", "oficina", "almacenamiento"]


def fail(error):
    raise ToolError(f"{error.code}: {error.message}")


@server.tool(annotations=read_only)
def get_product(sku: Sku) -> dict:
    """Get one product: name, category, price (MXN) and stock (units)."""
    try:
        return open_erp().get_product(sku)
    except ERPError as error:
        fail(error)


@server.tool(annotations=read_only)
def find_products(category: Category | None = None,
                  max_stock: Annotated[int | None, Field(ge=0, le=10000)] = None) -> dict:
    """Search products. Use max_stock to find items with low stock."""
    try:
        return {"products": open_erp().find_products(category, max_stock)}
    except ERPError as error:
        fail(error)


@server.tool(annotations=read_only, meta={"acme/untrusted_fields": ["notes"]})
def get_customer(customer_id: CustomerId) -> dict:
    """Get a customer's profile. 'notes' is free text written by staff."""
    try:
        customer = open_erp().get_customer(customer_id)
    except ERPError as error:
        fail(error)
    # Not allowed looks exactly like not found: we never reveal that the record exists.
    if customer["region"] not in person["regions"]:
        raise ToolError(f"not_found: Customer {customer_id} not found")

    visible = {
        "id": customer["id"],
        "name": customer["name"],
        "region": customer["region"],
        "tier": customer["tier"],
        "email": customer["email"],
        "phone": customer["phone"],
        "notes": customer["notes"],
    }
    if "finance" not in person["roles"]:
        visible["email"] = "hidden"
        visible["phone"] = "hidden"
    return visible


@server.tool(annotations=read_only)
def get_invoice(invoice_id: InvoiceId) -> dict:
    """Get one invoice: status, total (MXN) and amount already refunded."""
    try:
        return open_erp().get_invoice(invoice_id)
    except ERPError as error:
        fail(error)


def can_see(document):
    if document["roles"] is not None:
        if not any(role in document["roles"] for role in person["roles"]):
            return False
    if document["regions"] is not None:
        if not any(region in document["regions"] for region in person["regions"]):
            return False
    return True


def all_documents():
    documents = read_jsonl(DATA_DIR / "documents.jsonl")
    for customer in read_jsonl(DATA_DIR / "customers.jsonl"):
        if customer["notes"]:
            documents.append({"id": "NOTE-" + customer["id"], "title": "Account note",
                              "text": customer["notes"], "roles": None, "regions": [customer["region"]]})
    return documents


@server.tool(annotations=read_only, meta={"acme/untrusted_fields": ["untrusted"]})
def search_documents(query: Annotated[str, Field(min_length=2, max_length=120)]) -> dict:
    """Search company policies and account notes you are allowed to see."""
    query_words = set(query.lower().split())
    scored = []
    for document in all_documents():
        if not can_see(document):          # filter by permission BEFORE ranking
            continue
        score = len(query_words & set(document["text"].lower().split()))
        if score > 0:
            scored.append((score, document))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = []
    untrusted = []
    for score, document in scored[:3]:
        results.append({"id": document["id"], "title": document["title"], "text": document["text"]})
        if document["id"].startswith("NOTE-"):
            untrusted.append(document["id"])
    return {"results": results, "untrusted": untrusted}


if __name__ == "__main__":
    server.run("stdio")
