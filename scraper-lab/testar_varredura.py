"""
Teste minimo da varredura: uma pagina, coleta sem LLM e extracao com SmartScraperGraph.

    LLM_PROVIDER=anthropic LLM_MODEL=claude-haiku-5-5 uv run python testar_varredura.py
    ... testar_varredura.py https://outra.url "Pergunta sobre a pagina"

A chave vem do .env ou do ambiente do shell. Nada e gravado em disco.
"""

import json
import sys

from scraper_lab.coleta import coletar
from scraper_lab.llm import build_graph_config, provedor_ativo
from scrapegraphai.graphs import SmartScraperGraph

URL = sys.argv[1] if len(sys.argv) > 1 else "https://quotes.toscrape.com/"
PERGUNTA = sys.argv[2] if len(sys.argv) > 2 else "Liste as tres primeiras citacoes com autor."

pagina = coletar([URL])[0]
print(f"[coleta] {URL}: {len(pagina.html)} chars de HTML, {len(pagina.markdown)} de markdown")

p = provedor_ativo()
print(f"[llm] provedor={p.nome} modelo={p.modelo} chave={'sim' if p.tem_chave else 'nao'}")
grafo = SmartScraperGraph(prompt=PERGUNTA, source=URL, config=build_graph_config())
print(json.dumps(grafo.run(), indent=2, ensure_ascii=False))
