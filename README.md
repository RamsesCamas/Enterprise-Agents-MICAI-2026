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
# 2. In this folder, create the virtual environment and install everything into it:
uv venv .venv                             # creates the .venv folder
uv sync                                   # installs everything pinned in uv.lock into .venv
```

Activate the environment so `python`, `jupyter` and `streamlit` resolve to `.venv`:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat
```

Then provide your key and run the labs or the capstone:

```bash
# Put GROQ_API_KEY in labs/.env (copy labs/.env.example), or export it:
export GROQ_API_KEY=your-key              # free at console.groq.com  (Windows: set GROQ_API_KEY=...)
jupyter lab labs/                         # the labs
streamlit run capstone/app.py             # the capstone
```

With the environment activated the commands above run inside `.venv`. If you prefer
not to activate it, prefix each command with `uv run` instead (for example
`uv run jupyter lab labs/`).

## Setup with Google Colab

Upload any notebook from `labs/` to Colab and add a secret named `GROQ_API_KEY` (key icon in the left sidebar).
The first cell installs what it needs and downloads `labs/data/` from this repository.

## The labs

| # | Notebook | Minutes | Topic |
|---|---|---|---|
| 0 | `00_preparation` | 15 | Before the session: first model call, first tool call by hand |
| 1 | `01_control_loop` | 25 | The loop, its stop conditions, and what any successor must keep |
| 2 | `02_harness` | 40 | Idempotency, retries, circuit breaker, compensation, context, cost, replay, why the harness beats the model, tuning |
| 3 | `03_mcp_servers` | 25 | Read and write MCP servers, constrained schemas, a client with an allowlist and pinning |
| 4 | `04_governance` | 35 | Policy, personal data, permission-aware search, provenance, approvals |
| 5 | `05_evaluation` | 15 | A regression suite with four separate scores, then prompt changes |

The simulated company data (products, customers, invoices, policies) lives in `labs/data/*.jsonl`.
No real personal data and no corporate credentials are used anywhere.

## Using another model

Any OpenAI-compatible endpoint works: set `LLM_BASE_URL` and `LLM_MODEL`
(for example a local Ollama at `http://localhost:11434/v1`).
