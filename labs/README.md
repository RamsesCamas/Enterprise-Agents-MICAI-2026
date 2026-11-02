# Labs

Each notebook is self-contained: it defines its own small ERP, its own model call and everything it uses.
Nothing is imported from `capstone/`. Run the cells as we reach them on the screen.

```
data/
  products.jsonl     12 products with price and stock
  customers.jsonl    8 customers in three regions (one has a planted prompt injection)
  invoices.jsonl     6 invoices
  documents.jsonl    company policies, some visible only to finance
```

Lab 3 writes a few files next to the notebook (`acme_erp.py`, `acme_read.py`, `acme_write.py`,
`acme_state.json`): those are the MCP servers it builds. Lab 5 writes `good_runs.jsonl`.
