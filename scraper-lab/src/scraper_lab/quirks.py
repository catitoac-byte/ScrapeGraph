"""
Extrator do Sourcebook da Quirk's (quirks.com/directories/sourcebook).

A listagem roda sobre Algolia InstantSearch, porem o site expoe paginacao
classica por ?page=N, entao nao precisamos tocar na API de busca: basta
percorrer as paginas como um visitante faria.

O perfil traz nome, cidade/estado, descricao e link do site. E-mail nao e
publicado, o mesmo caso da Greenbook, e por isso o enriquecimento por site
(scraper_lab.enriquecer) e o passo seguinte natural.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.quirks.com"
PAIS_URL = BASE + "/directories/sourcebook/countries/{pais}"
# O diretorio tambem recorta por regiao, o que da granularidade estadual
# nos EUA sem precisar filtrar a lista do pais inteiro.
REGIAO_URL = BASE + "/directories/sourcebook/regions/{regiao}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

_ESPACOS = re.compile(r"\s+")
_SLUG = re.compile(r"/directories/[^/]+/company/([^/?#\"]+)")
# Links de rede social entram no HTML com /company/ e nao sao perfis daqui.
_EXTERNO = ("linkedin.com", "facebook.com", "twitter.com", "x.com")
# Dominios do proprio diretorio e de servicos, nunca da empresa listada.
_NAO_E_SITE = ("quirks.com", "bluetoad.com", "fontawesome", "algolia")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _baixar(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(1_500_000).decode("utf-8", errors="replace")


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""        # a Quirk's nao publica; enchemos no enriquecimento
    site: str = ""
    pais: str = ""
    cidade: str = ""
    estado: str = ""
    descricao: str = ""
    servicos: str = ""
    coletado_em: str = ""
    erro: str = ""


def _slugs(html: str) -> set[str]:
    return {m.group(1) for m in _SLUG.finditer(html)
            if not any(d in m.group(0) for d in _EXTERNO)}


def listar_por_regiao(regiao: str, **kw) -> list[str]:
    """Empresas de um estado ou regiao (ex.: new-york, florida, california)."""
    return _listar(REGIAO_URL.format(regiao=regiao), **kw)


def listar_por_pais(pais: str = "united-states", *, max_paginas: int = 80,
                    delay: float = 1.2, verbose: bool = True) -> list[str]:
    """
    Percorre ?page=N ate parar de aparecer perfil novo.

    Duas paginas seguidas sem novidade encerram: uma so poderia ser
    resposta lenta e truncaria a lista sem erro nenhum.
    """
    return _listar(PAIS_URL.format(pais=pais), max_paginas=max_paginas,
                   delay=delay, verbose=verbose)


def _listar(base: str, *, max_paginas: int = 80, delay: float = 1.2,
            verbose: bool = True) -> list[str]:
    if not robots_permitido(base, agente=UA):
        raise RuntimeError("robots.txt da Quirk's nao permite esta URL")

    vistos: set[str] = set()
    vazias = 0
    for n in range(1, max_paginas + 1):
        url = base if n == 1 else f"{base}?page={n}"
        try:
            achados = _slugs(_baixar(url))
        except Exception as exc:
            if verbose:
                print(f"      pagina {n}: falha ({type(exc).__name__})")
            achados = set()
        novos = achados - vistos
        vistos |= achados
        if verbose and (n <= 3 or n % 5 == 0 or not novos):
            print(f"      pagina {n:>2}: +{len(novos):>2} | acumulado {len(vistos)}")
        vazias = vazias + 1 if not novos else 0
        if vazias >= 2:
            break
        time.sleep(delay)

    urls = [f"{BASE}/directories/sourcebook/company/{s}" for s in sorted(vistos)]
    return [u for u in urls if robots_permitido(u, agente=UA)]


def extrair_empresa(html: str, url: str) -> Empresa:
    e = Empresa(url_perfil=url, coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    titulo = _limpar(sopa.title.get_text()) if sopa.title else ""
    e.nome = titulo.split("|")[0].strip()
    if not e.nome:
        h1 = sopa.find("h1")
        e.nome = _limpar(h1.get_text()) if h1 else ""

    # Sob o nome vem "Cidade, UF" e, fora dos EUA, o pais.
    texto = sopa.get_text("\n", strip=True)
    m = re.search(rf"{re.escape(e.nome)}\n([^\n]{{2,60}})", texto) if e.nome else None
    if m:
        local = _limpar(m.group(1))
        partes = [p.strip() for p in local.split(",")]
        if len(partes) >= 2 and len(partes[-1]) <= 3:
            e.cidade, e.estado, e.pais = partes[0], partes[-1], "United States"
        elif len(partes) >= 2:
            e.cidade, e.pais = partes[0], partes[-1]
        else:
            e.cidade = local

    m2 = re.search(r"Company Description\n(.{40,600}?)(?:\n[A-Z][^\n]{0,40}\n|\Z)",
                   texto, re.S)
    if m2:
        e.descricao = _limpar(m2.group(1))[:400]

    # O site da empresa esta no botao "View Website". Varrer qualquer link
    # externo trazia bluetoad.com, que hospeda a revista do proprio diretorio.
    for a in sopa.select("a[href^=http]"):
        rotulo = _limpar(a.get_text()).lower()
        if "website" in rotulo or "visit site" in rotulo:
            alvo = a["href"].split("?")[0]
            if not any(d in alvo for d in _NAO_E_SITE):
                e.site = alvo
                break

    if not e.nome:
        e.erro = "sem nome no perfil"
    return e


def coletar(urls: list[str], *, delay: float = 1.2, verbose: bool = True) -> list[Empresa]:
    saida: list[Empresa] = []
    for i, url in enumerate(urls, 1):
        try:
            e = extrair_empresa(_baixar(url), url)
        except Exception as exc:
            e = Empresa(url_perfil=url, erro=f"{type(exc).__name__}"[:50],
                        coletado_em=datetime.now(timezone.utc).isoformat())
        saida.append(e)
        if verbose:
            print(f"  [{i:>3}/{len(urls)}] {'!' if e.erro else '.'} "
                  f"{e.nome[:34]:34} | {e.cidade[:18]:18} {e.estado:3} | {e.site[:28]}")
        if i < len(urls):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "email", "site", "pais", "cidade", "estado",
           "descricao", "servicos", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "quirks_eua") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=1),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
