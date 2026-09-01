"""
Extrator do diretorio de empresas da Greenbook (greenbook.org).

O perfil publica um bloco JSON-LD do tipo LocalBusiness, com nome, telefone
e endereco ja estruturados. E a fonte mais limpa das tres que coletamos.

Restricoes do robots.txt que respeitamos aqui:
  - /company/*/email      o endpoint de e-mail e proibido. Nao o tocamos, e
                          por isso esta fonte sai sem e-mail.
  - /company/ThinkNow-Research   empresa que se excluiu do rastreamento.
  - /keyword-search-results      nao usamos busca por palavra-chave.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.greenbook.org"
CATEGORIA_PADRAO = "/market-research-firms/full-service"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

_ESPACOS = re.compile(r"\s+")
_SOCIAL = ("linkedin.com", "facebook.com", "twitter.com", "x.com",
           "youtube.com", "instagram.com", "google.com")

def permitido(url: str) -> bool:
    """Usa o verificador proprio: o do Python ignora curingas como
    /company/*/email e devolveria True para uma URL proibida."""
    return robots_permitido(url, agente=UA)


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _baixar(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000).decode("utf-8", errors="replace")


def _sem_utm(url: str) -> str:
    """Tira os parametros de rastreio que a Greenbook anexa ao site da empresa."""
    p = urlparse(url)
    manter = "&".join(q for q in p.query.split("&")
                      if q and not q.lower().startswith(("utm_", "ref=")))
    return urlunparse(p._replace(query=manter))


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""          # a Greenbook nao publica; fica vazio de proposito
    site: str = ""
    pais: str = ""
    regiao: str = ""
    cidade: str = ""
    telefone: str = ""
    endereco: str = ""
    linkedin: str = ""
    descricao: str = ""
    servicos: str = ""
    categoria: str = ""
    coletado_em: str = ""
    erro: str = ""


def listar_empresas(caminho: str = CATEGORIA_PADRAO) -> list[str]:
    """URLs de perfil da categoria, ja filtrando o que o robots.txt proibe."""
    html = _baixar(BASE + caminho)
    sopa = BeautifulSoup(html, "html.parser")
    # so caminhos internos: "/company/" tambem aparece em URLs do LinkedIn
    brutos = {a["href"] for a in sopa.select("a[href]")
              if a["href"].startswith("/company/")
              or a["href"].startswith(f"{BASE}/company/")}

    urls = []
    for h in sorted(brutos):
        u = h if h.startswith("http") else BASE + h
        if "/email" in u or "/preview-" in u:
            continue
        if permitido(u):
            urls.append(u)
    return urls


# A Greenbook usa mais de um tipo de schema para o mesmo cartao de empresa.
_TIPOS_EMPRESA = {"LocalBusiness", "Organization", "Corporation", "ProfessionalService"}


SITEMAP = BASE + "/sitemaps/companies.xml"


def listar_do_sitemap() -> list[str]:
    """
    Lista canonica de empresas, do sitemap que a propria Greenbook publica.

    Percorrer as 396 categorias traria as mesmas empresas varias vezes; o
    sitemap entrega o diretorio inteiro numa requisicao e sem sobreposicao.
    """
    xml = _baixar(SITEMAP)
    urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    return sorted({u for u in urls
                   if "/company/" in u and "/email" not in u and permitido(u)})


def _json_ld(sopa: BeautifulSoup) -> dict:
    for sc in sopa.select('script[type="application/ld+json"]'):
        try:
            d = json.loads(sc.string or "{}")
        except Exception:
            continue
        for item in (d if isinstance(d, list) else [d]):
            if isinstance(item, dict) and item.get("@type") in _TIPOS_EMPRESA:
                return item
    return {}


def extrair_empresa(html: str, url: str) -> Empresa:
    e = Empresa(url_perfil=url, coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    ld = _json_ld(sopa)
    e.nome = _limpar(ld.get("name"))
    e.telefone = _limpar(ld.get("telephone"))
    e.servicos = _limpar(ld.get("keywords"))

    end = ld.get("address") or {}
    if isinstance(end, dict):
        e.pais = _limpar(end.get("addressCountry"))
        e.regiao = _limpar(end.get("addressRegion"))
        e.cidade = _limpar(end.get("addressLocality"))
        partes = [end.get("streetAddress"), end.get("addressLocality"),
                  end.get("addressRegion"), end.get("postalCode"),
                  end.get("addressCountry")]
        e.endereco = ", ".join(_limpar(p) for p in partes if _limpar(p))

    # O h1 traz o nome em todos os perfis, inclusive nos sem JSON-LD.
    h1 = sopa.find("h1")
    if h1:
        e.nome = e.nome or _limpar(h1.get_text())

    # O titulo tem tres formatos: "Nome | Categoria from Pais | Greenbook",
    # "Nome | Categoria, Pais | Greenbook" e "Nome | Pais | Greenbook".
    titulo = _limpar(sopa.title.get_text()) if sopa.title else ""
    partes = [p.strip() for p in titulo.split("|")]
    if len(partes) >= 3:
        e.nome = e.nome or partes[0]
        meio = partes[1]
        m = re.match(r"(.+?)(?:\s+from\s+|\s*,\s*)(.+)$", meio)
        if m:
            e.categoria = e.categoria or _limpar(m.group(1))
            e.pais = e.pais or _limpar(m.group(2))
        else:
            e.pais = e.pais or _limpar(meio)

    desc = sopa.find("meta", attrs={"name": "description"})
    if desc:
        e.descricao = _limpar(desc.get("content"))[:400]

    for a in sopa.select("a[href]"):
        h = a.get("href", "")
        if not h.startswith("http"):
            continue
        if "linkedin.com/company" in h and not e.linkedin:
            e.linkedin = h.split("?")[0]
        elif ("greenbook" not in h and not any(s in h for s in _SOCIAL)
              and not e.site):
            e.site = _sem_utm(h)

    if not e.nome:
        e.erro = "sem nome: nem h1, nem JSON-LD, nem titulo"
    return e


def coletar(urls: list[str], *, delay: float = 1.5, verbose: bool = True) -> list[Empresa]:
    saida: list[Empresa] = []
    for i, url in enumerate(urls, 1):
        try:
            e = extrair_empresa(_baixar(url), url)
        except Exception as exc:
            e = Empresa(url_perfil=url, erro=f"{type(exc).__name__}"[:60],
                        coletado_em=datetime.now(timezone.utc).isoformat())
        saida.append(e)
        if verbose:
            print(f"  [{i:>3}/{len(urls)}] {'!' if e.erro else '.'} "
                  f"{e.nome[:34]:34} | {e.pais[:16]:16} | {e.telefone[:18]}")
        if i < len(urls):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "email", "site", "pais", "regiao", "cidade", "telefone",
           "endereco", "linkedin", "categoria", "servicos", "descricao",
           "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "greenbook") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
