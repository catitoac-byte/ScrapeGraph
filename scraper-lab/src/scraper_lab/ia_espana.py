"""
Extrator das empresas associadas da Insights + Analytics Espana
(ia-espana.org/empresas-asociadas-ia-espana).

Detalhe de conformidade: o robots.txt do site proibe /directorio-de-negocios
e /directorio-de-negocios/*. As fichas que nos interessam ficam em slugs de
primeiro nivel (/gfk/, /dvj-insights/), fora dessa restricao, e o
verificador confirma cada URL antes da requisicao.

Todas as associadas sao espanholas, entao o pais e fixo.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

LISTAGEM = "https://ia-espana.org/empresas-asociadas-ia-espana/"
PAIS = "Spain"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Contatos da propria associacao e ruido de terceiros, presentes em toda ficha.
_EMAIL_INSTITUCIONAL = {"secretaria@ia-espana.org", "info@ia-espana.org"}
_DOMINIO_IGNORADO = ("ia-espana.org", "linkedin.com", "facebook.com", "twitter.com",
                     "x.com", "youtube.com", "instagram.com", "google.com",
                     "cookiedatabase.org", "wordpress.org")
# Sufixos de arquivo que o regex de e-mail captura por engano (logo@2x.png).
_NAO_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|^leaflet@", re.I)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ESPACOS = re.compile(r"\s+")

# Paginas que aparecem como slug de topo mas nao sao empresas.
_NAO_EMPRESA = {
    "empresas-asociadas-ia-espana", "socios", "contacto", "aviso-legal",
    "politica-de-privacidad", "politica-de-cookies", "blog", "noticias",
    "eventos", "formacion", "identificate", "quienes-somos", "asociarse",
}


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _baixar(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000).decode("utf-8", errors="replace")


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    descricao: str = ""
    associacoes: str = ""
    coletado_em: str = ""
    erro: str = ""
    emails_extras: list[str] = field(default_factory=list)


# Marcadores que so aparecem em ficha de associada, nunca em pagina
# institucional. Classificar por conteudo e mais seguro que por nome de
# slug: paginas como "etica" ou "premios-ia" moram no mesmo nivel das
# empresas, e nem toda associada tem logo na listagem.
_MARCADORES = ("especializaci", "miembro de:", "servicios:", "contacto:")

_SLUG_TOPO = re.compile(r"^https://ia-espana\.org/([^/]+)/$")


def _parece_empresa(html: str) -> bool:
    """
    Uma ficha e de empresa quando tem estrutura de ficha E dado de contato
    proprio. Exigir dois marcadores deixava de fora associadas com ficha
    curta (a Sigmados tem so "Miembro de:", mas publica e-mail e site).
    """
    sopa = BeautifulSoup(html, "html.parser")
    corpo = sopa.get_text(" ", strip=True).lower()
    if not any(m in corpo for m in _MARCADORES):
        return False

    tem_site = any(
        a["href"].startswith("http")
        and not any(d in a["href"] for d in _DOMINIO_IGNORADO)
        for a in sopa.select("a[href]")
    )
    tem_email = any(
        (v := a["href"][7:].split("?")[0].strip().lower())
        and v not in _EMAIL_INSTITUCIONAL and not _NAO_EMAIL.search(v)
        for a in sopa.select('a[href^="mailto:"]')
    )
    return tem_site or tem_email


def listar_empresas(*, verbose: bool = True) -> list[str]:
    """
    Fichas das associadas.

    A listagem mistura empresas e paginas institucionais no mesmo nivel de
    URL, entao abrimos cada candidata e mantemos as que tem estrutura de
    ficha de empresa.
    """
    sopa = BeautifulSoup(_baixar(LISTAGEM), "html.parser")
    candidatas = sorted({
        h for a in sopa.select("a[href]")
        if (h := (a.get("href") or "").split("?")[0]) and _SLUG_TOPO.match(h)
        and _SLUG_TOPO.match(h).group(1) not in _NAO_EMPRESA
    })
    candidatas = [u for u in candidatas if robots_permitido(u, agente=UA)]
    if verbose:
        print(f"      {len(candidatas)} candidatas; classificando por conteudo")

    empresas = []
    for u in candidatas:
        try:
            if _parece_empresa(_baixar(u)):
                empresas.append(u)
        except Exception:
            continue
        time.sleep(0.8)
    return empresas


def extrair_empresa(html: str, url: str) -> Empresa:
    e = Empresa(url_perfil=url, coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    titulo = _limpar(sopa.title.get_text()) if sopa.title else ""
    e.nome = re.sub(r"\s*[-–|]\s*Insights \+ Analytics Espa[nñ]a\s*$", "", titulo).strip()
    if not e.nome:
        h1 = sopa.find("h1")
        e.nome = _limpar(h1.get_text()) if h1 else ""

    encontrados: list[str] = []
    for a in sopa.select('a[href^="mailto:"]'):
        v = a["href"][7:].split("?")[0].strip().lower()
        if v and v not in _EMAIL_INSTITUCIONAL and not _NAO_EMAIL.search(v):
            if v not in encontrados:
                encontrados.append(v)
    if not encontrados:
        for v in _EMAIL.findall(html):
            v = v.lower()
            if v not in _EMAIL_INSTITUCIONAL and not _NAO_EMAIL.search(v) and v not in encontrados:
                encontrados.append(v)
    if encontrados:
        e.email = encontrados[0]
        e.emails_extras = encontrados[1:4]

    for a in sopa.select("a[href^=http]"):
        h = a["href"].split("?")[0]
        if not any(d in h for d in _DOMINIO_IGNORADO):
            e.site = h
            break

    corpo = sopa.get_text("\n", strip=True)
    m = re.search(r"Especializaci[oó]n:\s*\n(.{40,600}?)(?:\n[A-ZÁÉÍÓÚ][^\n]{0,40}:|\Z)",
                  corpo, re.S)
    if m:
        e.descricao = _limpar(m.group(1))[:400]
    m2 = re.search(r"Miembro de:\s*\n([^\n]{3,200})", corpo)
    if m2:
        e.associacoes = _limpar(m2.group(1))

    m3 = re.search(r"(\+?\d[\d\s().\-]{7,18}\d)", corpo)
    if m3:
        e.telefone = _limpar(m3.group(1))

    if not e.nome:
        e.erro = "sem nome na ficha"
    return e


def coletar(urls: list[str], *, delay: float = 1.2, verbose: bool = True) -> list[Empresa]:
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
                  f"{e.nome[:30]:30} | {e.email[:32]:32}")
        if i < len(urls):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "email", "site", "pais", "telefone", "descricao",
           "associacoes", "emails_extras", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "ia_espana") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            d["emails_extras"] = " | ".join(d.get("emails_extras") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
