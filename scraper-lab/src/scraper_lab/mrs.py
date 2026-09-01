"""
Extrator do Research Buyers Guide da MRS (mrs.org.uk).

A fonte mais rica das que coletamos: o perfil publica microdados
schema.org com nome, endereco completo, telefone, e-mail e descricao.

Dois detalhes do site que moldam o codigo:
  - A listagem usa rolagem infinita. Sem rolar ate o fim, so vem 10 cartoes,
    e o total declarado ("Listing N companies") serve de criterio de parada.
  - A busca vazia devolve apenas destaques rotativos. A consulta por espaco
    (q=%20) e a que retorna o conjunto mais amplo.
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
from playwright.sync_api import sync_playwright

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.mrs.org.uk"
RESULTADOS = BASE + "/researchbuyersguide-results/q/{q}"
CONSULTA_AMPLA = "%20"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# E-mails da propria MRS e do fornecedor do CMS, presentes em toda pagina.
_EMAIL_INSTITUCIONAL = {"info@mrs.org.uk", "support@ama.uk.com"}
_ESPACOS = re.compile(r"\s+")
# Sobras de elementos ocultos no bloco de endereco: numeros soltos e ruido.
_LIXO_LINHA = re.compile(r"^[\d\s\-.,;:|]{1,4}$")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _baixar(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000).decode("utf-8", errors="replace")


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = ""
    cidade: str = ""
    telefone: str = ""
    endereco: str = ""
    tipo_membro: str = ""
    descricao: str = ""
    coletado_em: str = ""
    erro: str = ""


def listar_empresas(consulta: str = CONSULTA_AMPLA, *,
                    headless: bool = True, verbose: bool = True) -> list[str]:
    """
    Percorre a rolagem infinita e devolve as URLs de perfil.

    Paramos quando o numero de cartoes alcanca o total declarado pela pagina
    ou quando duas rolagens seguidas nao trazem nada novo.
    """
    url = RESULTADOS.format(q=consulta)
    if not robots_permitido(url, agente=UA):
        raise RuntimeError("robots.txt da MRS nao permite esta URL")

    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        pg = b.new_page()
        try:
            pg.goto(url, wait_until="networkidle", timeout=60_000)
            pg.wait_for_timeout(5000)

            m = re.search(r"Listing\s+([\d,]+)\s+companies", pg.inner_text("body"))
            total = int(m.group(1).replace(",", "")) if m else 0
            if verbose:
                print(f"      total declarado: {total or '?'}")

            vistos, paradas = 0, 0
            for volta in range(160):
                pg.mouse.wheel(0, 25_000)
                pg.wait_for_timeout(1800)
                # Contamos hrefs DISTINTOS: cada cartao tem dois links para o
                # mesmo perfil (logo e nome), e contar elementos faria a
                # rolagem parar na metade das empresas.
                n = pg.evaluate(
                    "() => new Set([...document.querySelectorAll('a[href^=\"/researchcompany/\"]')]"
                    ".map(a => a.getAttribute('href'))).size")
                if verbose and volta % 5 == 0:
                    print(f"      rolagem {volta:>2}: {n} cartoes")
                if n <= vistos:
                    paradas += 1
                    if paradas >= 3:
                        break
                else:
                    paradas = 0
                vistos = n
                if total and n >= total:
                    break

            hrefs = pg.eval_on_selector_all(
                'a[href^="/researchcompany/"]',
                "e => e.map(x => x.getAttribute('href'))")
        finally:
            b.close()

    urls = sorted({BASE + h for h in hrefs if h})
    return [u for u in urls if robots_permitido(u, agente=UA)]


# A MRS escreve o pais na ultima linha util do endereco, com variacoes.
_NORM_PAIS = {
    "united states (usa)": "United States", "usa": "United States",
    "united states": "United States", "uk": "United Kingdom",
    "united kingdom": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom", "republic of ireland": "Ireland",
    "eire": "Ireland",
}


def _pais_do_endereco(endereco: str) -> str:
    """
    Pais do endereco, com o Reino Unido como padrao.

    O guia e de fornecedores acreditados do Reino Unido e da Irlanda, e a
    MRS omite o pais nos enderecos britanicos por ser implicito. So trocamos
    o padrao quando o endereco nomeia um pais que reconhecemos.
    """
    partes = [p.strip() for p in endereco.split(",") if p.strip()]
    for parte in reversed(partes):
        chave = parte.lower().strip(".")
        if chave in _NORM_PAIS:
            return _NORM_PAIS[chave]
    return "United Kingdom"


def _texto_com_quebras(el) -> str:
    """Converte <br> em quebra de linha antes de extrair o texto."""
    for br in el.find_all("br"):
        br.replace_with("\n")
    return el.get_text("\n")


def extrair_empresa(html: str, url: str) -> Empresa:
    """
    Le o perfil.

    Cuidado necessario: a propria MRS publica microdados schema.org no
    rodape de toda pagina. Buscar itemprop solto devolve "The Market
    Research Society" e o telefone de Londres deles para qualquer empresa.
    Os dados do associado ficam em p.address_block e #rbg_addresses.
    """
    e = Empresa(url_perfil=url, coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    og = sopa.find("meta", attrs={"property": "og:title"})
    if og:
        e.nome = _limpar((og.get("content") or "").split("|")[0])
    if not e.nome:
        logo = sopa.select_one("p.company_logo img[alt]")
        if logo:
            e.nome = _limpar(re.sub(r"\s*Company Logo$", "", logo["alt"]))

    ribbon = sopa.select_one("span.favourite_suppliers_ribbon")
    e.tipo_membro = _limpar(ribbon.get_text()) if ribbon else ""

    bloco = sopa.select_one("p.address_block")
    if bloco is not None:
        linhas = [_limpar(l) for l in _texto_com_quebras(bloco).split("\n")]
        linhas = [l for l in linhas if l]
        endereco, telefone = [], ""
        for l in linhas:
            m = re.match(r"^Tel:\s*(.+)$", l, re.I)
            if m:
                telefone = _limpar(m.group(1))
            elif not l.lower().startswith("email") and not _LIXO_LINHA.match(l):
                endereco.append(l)
        e.endereco = ", ".join(endereco)
        e.telefone = telefone
        if endereco:
            e.cidade = endereco[1] if len(endereco) > 1 else ""

        for a in bloco.select('a[href^="mailto:"]'):
            v = a["href"][7:].split("?")[0].strip().lower()
            if v and v not in _EMAIL_INSTITUCIONAL:
                e.email = v
                break
        for a in bloco.select("a[href^=http]"):
            h = a["href"].split("?")[0]
            if "mrs.org.uk" not in h and "ama.uk.com" not in h:
                e.site = h
                break

    # Enderecos adicionais: usados como reserva de e-mail, telefone e pais.
    extras = sopa.select_one("#rbg_addresses")
    if extras is not None:
        texto = _texto_com_quebras(extras)
        if not e.email:
            for a in extras.select('a[href^="mailto:"]'):
                v = a["href"][7:].split("?")[0].strip().lower()
                if v and v not in _EMAIL_INSTITUCIONAL:
                    e.email = v
                    break
        if not e.telefone:
            m = re.search(r"Tel:\s*([^\n]+)", texto, re.I)
            if m:
                e.telefone = _limpar(m.group(1))
        if not e.endereco:
            e.endereco = ", ".join(_limpar(l) for l in texto.split("\n") if _limpar(l))

    e.pais = _pais_do_endereco(e.endereco)

    desc = sopa.find("meta", attrs={"name": "description"})
    if desc:
        e.descricao = _limpar(desc.get("content"))[:400]

    if not e.nome:
        e.erro = "sem nome no perfil"
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
                  f"{e.nome[:32]:32} | {e.email[:30]:30} | {e.pais[:14]}")
        if i < len(urls):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "email", "site", "pais", "cidade", "telefone", "endereco",
           "tipo_membro", "descricao", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "mrs_uk") -> tuple[Path, Path]:
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
