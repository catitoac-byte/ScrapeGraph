"""
Extrator do USAspending.gov para o NAICS 541910.

541910 = "Marketing Research and Public Opinion Polling", o equivalente
americano do CNAE 7320-3/00 brasileiro.

Nao existe nos EUA um cadastro publico de todas as empresas como o CNPJ da
Receita: o registro e estadual e fragmentado em 50 sistemas. O que existe
de federal e aberto sao os fornecedores do governo, e e isso que esta aqui.
Portanto o recorte nao e "toda empresa de pesquisa dos EUA", e sim "toda
empresa de pesquisa que ja vendeu para o governo federal". Isso enviesa
para empresas maiores e formalizadas, o que convem dizer em vez de fingir
cobertura total.

API publica, sem chave.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

# O certificado do usaspending.gov e aceito pelo repositorio do sistema, mas
# nao pelo pacote embutido do Python: sem isso a chamada falha com
# "self-signed certificate in certificate chain". truststore faz o Python
# usar o mesmo conjunto de raizes que o sistema operacional.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # ambiente sem truststore segue com o padrao
    pass

API = "https://api.usaspending.gov/api/v2"
NAICS = "541910"
UA = "scraper-lab/1.0 (pesquisa de mercado; contato via usuario)"


# Excecoes onde title() erra a caixa.
_CAIXA = {"Usa": "United States", "Uk": "United Kingdom",
          "United States Of America": "United States"}


def _NOME_PAIS(bruto: str) -> str:
    t = " ".join((bruto or "").strip().title().split())
    return _CAIXA.get(t, t)


@dataclass
class Fornecedor:
    recipient_id: str
    nome: str = ""
    uei: str = ""
    duns: str = ""
    valor_total: float = 0.0
    endereco: str = ""
    cidade: str = ""
    estado: str = ""
    cep: str = ""
    pais: str = "United States"
    tipos_negocio: str = ""
    matriz: str = ""
    email: str = ""     # a API nao publica; vem do enriquecimento por site
    site: str = ""
    erro: str = ""


def _post(caminho: str, corpo: dict, timeout: int = 60) -> dict:
    req = Request(API + caminho, data=json.dumps(corpo).encode(),
                  headers={"Content-Type": "application/json", "User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(caminho: str, timeout: int = 30) -> dict:
    req = Request(API + caminho, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def listar_fornecedores(*, desde: str = "2015-01-01", ate: str = "2026-08-31",
                        max_paginas: int = 60, delay: float = 1.0,
                        verbose: bool = True) -> list[Fornecedor]:
    """Percorre a paginacao da busca por destinatario ate acabar."""
    saida: list[Fornecedor] = []
    pagina = 1
    while pagina <= max_paginas:
        d = _post("/search/spending_by_category/recipient/", {
            "filters": {"naics_codes": {"require": [NAICS]},
                        "time_period": [{"start_date": desde, "end_date": ate}]},
            "limit": 100, "page": pagina,
        })
        res = d.get("results", [])
        for r in res:
            saida.append(Fornecedor(
                recipient_id=r.get("recipient_id") or "",
                nome=(r.get("name") or "").strip(),
                uei=(r.get("uei") or "").strip(),
                duns=(r.get("code") or "").strip(),
                valor_total=float(r.get("amount") or 0),
            ))
        meta = d.get("page_metadata", {})
        if verbose:
            print(f"      pagina {pagina:>2}: +{len(res)} | acumulado {len(saida)}")
        if not meta.get("hasNext") or not res:
            break
        pagina += 1
        time.sleep(delay)
    return saida


def detalhar(f: Fornecedor, *, delay: float = 0.4) -> Fornecedor:
    """Busca endereco e tipo de negocio do destinatario."""
    if not f.recipient_id:
        f.erro = "sem recipient_id"
        return f
    try:
        d = _get(f"/recipient/{f.recipient_id}/")
    except Exception as exc:
        f.erro = f"{type(exc).__name__}"[:40]
        return f
    loc = d.get("location") or {}
    f.endereco = " ".join(x for x in (loc.get("address_line1"),
                                      loc.get("address_line2")) if x).strip()
    f.cidade = (loc.get("city_name") or "").strip()
    f.estado = (loc.get("state_code") or "").strip()
    f.cep = (loc.get("zip") or loc.get("zip5") or "").strip()
    # A API devolve o pais em caixa alta ("UNITED STATES"). Normalizamos para
    # o mesmo formato do resto da base, senao o cruzamento por pais falha.
    f.pais = _NOME_PAIS(loc.get("country_name") or "United States")
    f.tipos_negocio = " | ".join(d.get("business_types") or [])
    f.matriz = (d.get("parent_name") or "").strip()
    time.sleep(delay)
    return f


COLUNAS = ["nome", "email", "site", "pais", "estado", "cidade", "endereco", "cep",
           "uei", "duns", "valor_total", "tipos_negocio", "matriz",
           "recipient_id", "erro"]


def exportar(fs: list[Fornecedor], nome: str = "usaspending_naics541910",
             saida: Path | None = None) -> tuple[Path, Path]:
    saida = saida or Path("dados/saida")
    saida.mkdir(parents=True, exist_ok=True)
    cj, cc = saida / f"{nome}.json", saida / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(f) for f in fs], ensure_ascii=False, indent=1),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for f in fs:
            d = asdict(f)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
