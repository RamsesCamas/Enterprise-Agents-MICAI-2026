"""Load configuration from a local .env file when running outside a shell
that already exported it (for example `streamlit run`, which does not read
.env on its own).

Values already present in the real environment win, so
`export GROQ_API_KEY=...` still takes precedence over the file. The loaded
values land in os.environ, so the MCP server subprocesses inherit them too
(see agent.connect, which passes dict(os.environ) to each child).
"""
import os
from pathlib import Path


def load_dotenv():
    """Read the nearest .env into os.environ. Looks next to the capstone
    package and in parent folders, so capstone/.env, a project-root .env,
    or labs/.env are all found."""
    here = Path(__file__).resolve().parent          # capstone/acme
    search = [here, here.parent, *here.parents]
    seen = set()
    for folder in search:
        if folder in seen:
            continue
        seen.add(folder)
        env_file = folder / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return env_file
    return None
