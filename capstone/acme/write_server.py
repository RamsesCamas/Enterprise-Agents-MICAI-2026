"""MCP server: actions that change Acme.

Only started for people who may write. The refund tool only exists when the
server is started for someone in finance.
"""
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from acme.erp import ERPError, open_erp
from acme.identity import allowed_effects, person_for_token

person = person_for_token(os.environ.get("ACME_TOKEN"))
if "write" not in allowed_effects(person):
    raise SystemExit(f"{person['id']} may not start the write server")

server = MCPServer("acme-write", version="1.0.0")


def idempotency_key(ctx):
    """The key travels in the request metadata, never as a model-visible argument."""
    metadata = ctx.request_context.meta or {}
    if isinstance(metadata, dict):
        return metadata.get("acme/idempotency-key")
    return None


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True))
def adjust_stock(sku: Annotated[str, Field(pattern=r"^SKU-[0-9]{3}$")],
                 delta: Annotated[int, Field(ge=-1000, le=1000)],
                 reason: Literal["restock", "sale", "damage", "correction"],
                 ctx: Context) -> dict:
    """Change the stock of one product by delta units (negative to remove)."""
    try:
        return open_erp().adjust_stock(sku, delta, reason, idempotency_key=idempotency_key(ctx))
    except ERPError as error:
        raise ToolError(f"{error.code}: {error.message}")


if "irreversible" in allowed_effects(person):

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
                 meta={"acme/irreversible": True})
    def create_refund(invoice_id: Annotated[str, Field(pattern=r"^INV-[0-9]{4}$")],
                      amount: Annotated[float, Field(gt=0, le=1_000_000)],
                      reason: Annotated[str, Field(min_length=3, max_length=200)],
                      ctx: Context) -> dict:
        """Refund part or all of a PAID invoice. Money leaves the company: this cannot be undone."""
        try:
            return open_erp().create_refund(invoice_id, amount, reason, idempotency_key=idempotency_key(ctx))
        except ERPError as error:
            raise ToolError(f"{error.code}: {error.message}")


if __name__ == "__main__":
    server.run("stdio")
