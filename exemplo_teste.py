"""
Teste rapido do ScrapeGraph-AI.

Rode com:
    cd "/Users/cassianoalbuquerque/Antigravity Projects/ScrapeGraph/Scrapegraph-ai"
    uv run python ../exemplo_teste.py

Requer OPENAI_API_KEY preenchida em Scrapegraph-ai/.env
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from scrapegraphai.graphs import SmartScraperGraph

REPO = Path(__file__).parent / "Scrapegraph-ai"
load_dotenv(REPO / ".env")

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit(
        f"OPENAI_API_KEY nao encontrada. Preencha em {REPO / '.env'}"
    )

graph_config = {
    "llm": {
        "api_key": api_key,
        "model": "openai/gpt-4o-mini",
    },
    "verbose": True,
    "headless": True,
}

graph = SmartScraperGraph(
    prompt="Liste os projetos com titulo e descricao.",
    source="https://perinim.github.io/projects/",
    config=graph_config,
)

result = graph.run()
print(json.dumps(result, indent=2, ensure_ascii=False))
