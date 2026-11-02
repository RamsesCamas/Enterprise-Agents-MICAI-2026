# Capstone: Acme Agent Console

Everything from the labs, connected. A Streamlit dashboard where you sign in as different employees,
run requests, approve or reject actions, and watch governance, cost and quality.

```bash
uv run streamlit run capstone/app.py                         # with Groq (GROQ_API_KEY)
LLM_PROVIDER=offline uv run streamlit run capstone/app.py    # no network: a rule-based stand-in model
```

Provide your key by putting `GROQ_API_KEY=...` in a `.env` file (next to `app.py` in `capstone/`,
or at the project root) or by exporting it. `streamlit run` does not read `.env` on its own, so
`app.py` loads it at startup; an exported variable still takes precedence over the file.

## How it fits together

```
app.py (Streamlit)
  └─ acme/agent.py          the loop (Lab 1) + harness (Lab 2) + client (Lab 3) + governance (Lab 4)
       ├─ starts, per person, the MCP servers they are allowed to use:
       │    acme/read_server.py    everyone; filters regions, contact data and documents for that person
       │    acme/write_server.py   only operations and finance; refunds only exist for finance
       │         └─ acme/erp.py    the ERP, loaded from data/*.jsonl (or acme/odoo_erp.py)
       ├─ acme/governance.py   policy, personal-data vault, approvals
       ├─ acme/identity.py     people, roles, tokens (your identity provider in production)
       └─ acme/model.py        Groq, or the offline stand-in
  └─ acme/evals.py          the regression suite from Lab 5
```

Everything the system does is logged to `runtime/events.jsonl` with OpenTelemetry GenAI names.
`runtime/` holds the ERP state, approvals and pinned tool definitions. Delete it to start over.

## Demo script (about 20 minutes)

1. **Ana**, *Customer C-0007*: the note tells the model to refund 105,891 MXN. The refund waits for approval.
2. **Approvals** tab, deciding as **María**: try deciding as Ana first (refused: own request), then reject.
3. **Ana**, *Contact data*: the **Governance** tab shows email and phone hidden from the model provider.
4. **Pedro**, *Other region*: customer C-0002 is in another region, so it is "not found".
5. Sidebar *Lose the next write's response*, then **Luis**, *Restock*: **Operations** shows 2 attempts and one idempotent replay.
6. Turn on the **Kill switch** and run anything: it stops at the next step.
7. **Quality** tab: run the suite. The C-0007 case shows the model was fooled but the system was safe.

## Odoo (optional, untested)

`acme/odoo_erp.py` implements the same ERP methods against Odoo 19's JSON-2 API.
It has not been tested against a live Odoo. See the instructions at the top of that file.
