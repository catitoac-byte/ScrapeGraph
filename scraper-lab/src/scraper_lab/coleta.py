"""
Camada de coleta: busca paginas e normaliza para markdown.

Nao usa LLM. Roda hoje, sem chave nenhuma, e produz os artefatos que
alimentam tanto a extracao manual quanto os grafos do ScrapeGraph depois.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from scrapegraphai.docloaders import ChromiumLoader
from scrapegraphai.utils import convert_to_md

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"


@dataclass
class Pagina:
    url: str
    html: str
    markdown: str
    coletado_em: str

    @property
    def slug(self) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", self.url.lower()).strip("-")[:60]
        digest = hashlib.sha256(self.url.encode()).hexdigest()[:8]
        return f"{base}-{digest}"

    def salvar(self, destino: Path | None = None) -> Path:
        destino = destino or SAIDA
        destino.mkdir(parents=True, exist_ok=True)
        caminho = destino / f"{self.slug}.json"
        caminho.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return caminho


def coletar(urls: list[str], *, headless: bool = True) -> list[Pagina]:
    """Busca as URLs com Chromium e devolve HTML cru mais markdown limpo."""
    loader = ChromiumLoader(urls, backend="playwright", headless=headless)
    docs = loader.load()
    agora = datetime.now(timezone.utc).isoformat()

    paginas: list[Pagina] = []
    for url, doc in zip(urls, docs):
        html = doc.page_content
        paginas.append(
            Pagina(
                url=url,
                html=html,
                markdown=convert_to_md(html, url),
                coletado_em=agora,
            )
        )
    return paginas
