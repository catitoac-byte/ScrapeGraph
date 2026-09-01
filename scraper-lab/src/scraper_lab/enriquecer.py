"""
Enriquecimento por site da empresa.

O e-mail do CNPJ e o contato fiscal, muitas vezes do contador ou um gmail
pessoal. Aqui visitamos o site da empresa para achar contato comercial.

De onde vem o dominio candidato:
  1. dominio proprio ja presente no e-mail do CNPJ (alta confianca);
  2. palpite a partir do nome fantasia ou razao social (a confirmar).

Todo palpite so vira dado se a pagina confirmar que e a empresa certa:
exigimos vestigio do nome E vocabulario de pesquisa de mercado. Sem isso o
registro fica sem site, que e melhor que um site errado.
"""

from __future__ import annotations

import re
import socket
import time
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

GRATUITOS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br",
             "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "live.com",
             "msn.com", "icloud.com", "globo.com", "aol.com", "protonmail.com"}

CAMINHOS = ("", "/contato", "/contato/", "/fale-conosco", "/contact", "/sobre")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LIXO = re.compile(
    r"(sentry|wixpress|\.(png|jpe?g|gif|webp|svg|css|js)$|@sentry|noreply|no-reply|"
    r"@2x|example\.|dominio\.com|domain\.com|seuemail|seudominio|email@|user@)", re.I)
# Enderecos comerciais valem mais que um contato qualquer.
_PREFERIDOS = ("comercial", "contato", "vendas", "atendimento", "sac",
               "novosnegocios", "hello", "info", "contact")
_PESQUISA = ("pesquisa", "market research", "insights", "opiniao", "opinião",
             "consumidor", "estudos de mercado", "survey", "qualitativa",
             "quantitativa", "inteligencia de mercado", "data")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


_DESCARTE = {"ltda", "me", "epp", "eireli", "sa", "s.a", "sociedade", "empresa",
             "servicos", "comercio", "e", "de", "da", "do", "dos", "das",
             "instituto", "consultoria", "pesquisa", "pesquisas", "assessoria"}


def _slug(nome: str) -> str:
    base = _norm(nome)
    base = re.sub(r"\b(ltda|me|epp|eireli|s\.?a\.?|sa|sociedade|empresa|"
                  r"servicos|comercio|e|de|da|do|dos|das)\b", " ", base)
    return re.sub(r"[^a-z0-9]", "", base)


def _resolve(dominio: str) -> bool:
    try:
        socket.getaddrinfo(dominio, None)
        return True
    except Exception:
        return False


def _baixar(url: str, timeout: int = 7) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(600_000).decode("utf-8", errors="replace")


# Ligar o navegador custa caro; quem chama decide.
_RENDERIZAR = [False]


def usar_navegador(ativo: bool) -> None:
    _RENDERIZAR[0] = ativo


def _emails_via_navegador(base: str, dominio: str) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page()
            try:
                pg.goto(base, wait_until="domcontentloaded", timeout=15_000)
                pg.wait_for_timeout(3500)
                html = pg.content()
            finally:
                b.close()
        return _emails(html, dominio)
    except Exception:
        return []


@dataclass
class Enriquecido:
    cnpj: str
    site: str = ""
    origem_site: str = ""      # email-proprio | palpite | nao encontrado
    email_comercial: str = ""
    emails_site: list[str] = field(default_factory=list)
    confirmado: bool = False
    erro: str = ""


def dominio_do_email(email: str) -> str:
    d = (email or "").split("@")[-1].strip().lower()
    return "" if (not d or d in GRATUITOS or "contab" in d) else d


def candidatos(razao: str, fantasia: str, email: str) -> list[tuple[str, str]]:
    """(dominio, origem), do mais confiavel ao mais especulativo."""
    saida: list[tuple[str, str]] = []
    d = dominio_do_email(email)
    if d:
        saida.append((d, "email-proprio"))
    # Varios recortes do nome: empresas usam desde a sigla ate o nome inteiro.
    for base_nome in (fantasia, razao):
        if not base_nome:
            continue
        palavras = [w for w in _norm(base_nome).split()
                    if w not in _DESCARTE and len(w) > 1]
        recortes = {_slug(" ".join(palavras[:n])) for n in (1, 2, 3)}
        recortes.add(_slug(base_nome))
        for r in sorted(recortes, key=len, reverse=True):
            if 4 <= len(r) <= 30:
                for tld in (".com.br", ".com"):
                    saida.append((r + tld, "palpite"))
    vistos, unicos = set(), []
    for dom, org in saida:
        if dom not in vistos:
            vistos.add(dom)
            unicos.append((dom, org))
    return unicos


def _emails(html: str, dominio: str) -> list[str]:
    achados = []
    for e in _EMAIL.findall(html):
        e = e.strip(".,;:)").lower()
        if _LIXO.search(e) or e in achados:
            continue
        achados.append(e)
    # e-mail no dominio da empresa primeiro, depois prefixos comerciais
    achados.sort(key=lambda e: (
        0 if e.split("@")[-1] == dominio else 1,
        0 if any(e.startswith(p) for p in _PREFERIDOS) else 1,
    ))
    return achados[:6]


def _confirma(html: str, slug: str) -> bool:
    texto = _norm(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))[:20000]
    tem_pesquisa = any(p in texto for p in _PESQUISA)
    tem_nome = bool(slug) and slug[:8] in re.sub(r"[^a-z0-9]", "", texto)
    return tem_pesquisa and tem_nome


def enriquecer(cnpj: str, razao: str, fantasia: str, email: str,
               *, delay: float = 0.6) -> Enriquecido:
    r = Enriquecido(cnpj=cnpj)
    slug = _slug(fantasia or razao)

    for dominio, origem in candidatos(razao, fantasia, email):
        if not _resolve(dominio):
            continue
        for esquema in ("https://", "http://"):
            base = esquema + dominio
            if not robots_permitido(base, agente=UA):
                r.erro = "robots do dominio nao permite"
                break
            try:
                home = _baixar(base)
            except Exception:
                continue

            # palpite so vale se a pagina confirmar a empresa
            if origem == "palpite" and not _confirma(home, slug):
                break

            r.site, r.origem_site = base, origem
            r.confirmado = origem == "email-proprio" or _confirma(home, slug)
            achados = _emails(home, dominio)
            for caminho in CAMINHOS[1:]:
                if achados:
                    break
                try:
                    achados = _emails(_baixar(base + caminho), dominio)
                except Exception:
                    continue
                time.sleep(delay)
            # Site que devolve HTML minusculo costuma ser SPA: o conteudo
            # so existe apos o JavaScript rodar.
            if not achados and len(home) < 4000 and _RENDERIZAR[0]:
                achados = _emails_via_navegador(base, dominio)
                if achados:
                    r.origem_site += "+render"
            r.emails_site = achados
            r.email_comercial = achados[0] if achados else ""
            return r
        if r.site:
            break
    if not r.site and not r.erro:
        r.origem_site = "nao encontrado"
    return r
