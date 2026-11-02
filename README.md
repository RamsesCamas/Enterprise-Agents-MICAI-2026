# Reliable Enterprise Agents: Harness, Techniques, and Secure MCP Integration

Tutorial at **MICAI 2026**, Tecnológico de Monterrey, Campus Chihuahua. Monday, November 2, 11:00–14:00.
Ramsés Camas, Universidad Politécnica de Chiapas.

```
labs/        Six notebooks we go through together. Each one is self-contained.
capstone/    The same ideas connected into one system: what an enterprise agent looks like.
```

## Setup with uv (recommended)

```bash
# 1. Install uv once: https://docs.astral.sh/uv/getting-started/installation/
# 2. In this folder:
uv sync                                   # creates .venv with everything pinned in uv.lock
export GROQ_API_KEY=your-key              # free at console.groq.com  (Windows: set GROQ_API_KEY=...)
uv run jupyter lab labs/                  # the labs
uv run streamlit run capstone/app.py      # the capstone
```

## Setup with Google Colab

Upload any notebook from `labs/` to Colab and add a secret named `GROQ_API_KEY` (key icon in the left sidebar).
The first cell installs what it needs and downloads `labs/data/` from this repository.

## The labs

| # | Notebook | Minutes | Topic |
|---|---|---|---|
| 0 | `00_preparation` | 15 | Before the session: first model call, first tool call by hand |
| 1 | `01_control_loop` | 25 | The loop, its stop conditions, and what any successor must keep |
| 2 | `02_harness` | 30 | Idempotency, safe retries, circuit breaker, compensation, context, cost, replay |
| 3 | `03_mcp_servers` | 25 | Read and write MCP servers, constrained schemas, a client with an allowlist and pinning |
| 4 | `04_governance` | 35 | Policy, personal data, permission-aware search, provenance, approvals |
| 5 | `05_evaluation` | 15 | A regression suite with four separate scores, then prompt changes |

The simulated company data (products, customers, invoices, policies) lives in `labs/data/*.jsonl`.
No real personal data and no corporate credentials are used anywhere.

## Using another model

Any OpenAI-compatible endpoint works: set `LLM_BASE_URL` and `LLM_MODEL`
(for example a local Ollama at `http://localhost:11434/v1`).
