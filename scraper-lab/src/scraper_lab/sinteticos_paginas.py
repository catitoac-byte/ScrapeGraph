"""
Paginas da vertical sinteticos: abrir, guardar e citar.

Regra central do PRD: todo achado vem de pagina realmente aberta, e toda
citacao precisa existir literalmente no texto guardado. Por isso este modulo
guarda o texto de cada pagina no disco (o que o validador le depois) e so
produz citacoes recortadas desse mesmo texto.

Bloqueio nao se contorna. HTTP 403, 429 e 999 viram "not accessible" e nao
ganham segunda tentativa por navegador. O Chromium so entra quando a pagina
respondeu 200 mas veio quase vazia, sinal de site montado por JavaScript.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.pipeline import gravar_json, ler_json
from scraper_lab.robots import UA_PADRAO, permitido

UA = UA_PADRAO
BLOQUEIO_HTTP = {401, 403, 429, 451, 999}
MIN_TEXTO = 800          # abaixo disso a pagina provavelmente depende de JS
MAX_TEXTO = 400_000
PAUSA_DOMINIO = 1.2      # segundos entre duas requisicoes ao mesmo dominio


# --------------------------------------------------------------------------
# Normalizacao e citacao
# --------------------------------------------------------------------------

_TROCAS = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    " ": " ", " ": " ", " ": " ", "​": "", "‌": "",
    "‍": "", "﻿": "", "­": "",
}
_ESPACO = re.compile(r"\s+")
_RETICENCIAS = re.compile(r"\s*(?:\.\.\.|…)\s*")


def normalizar(texto: str) -> str:
    """Forma canonica para comparar citacao com pagina.

    Unifica aspas, travessoes e espacos (diferencas tipograficas, nao de
    conteudo). Nao muda caixa nem pontuacao: a comparacao continua literal.
    """
    t = unicodedata.normalize("NFKC", texto or "")
    for de, para in _TROCAS.items():
        t = t.replace(de, para)
    return _ESPACO.sub(" ", t).strip()


def citacao_confere(citacao: str, texto: str) -> bool:
    """True se a citacao esta no texto. Reticencias marcam fragmentos, que
    precisam aparecer todos e na ordem."""
    alvo = normalizar(texto)
    pedacos = [p for p in _RETICENCIAS.split(normalizar(citacao)) if p.strip()]
    if not pedacos:
        return False
    pos = 0
    for p in pedacos:
        i = alvo.find(p.strip(), pos)
        if i < 0:
            return False
        pos = i + len(p.strip())
    return True


def recortar(frase: str, limite: int = 360) -> str:
    """Encurta uma frase em fronteira de palavra. Fragmento continua literal."""
    f = normalizar(frase)
    if len(f) <= limite:
        return f
    corte = f[:limite].rsplit(" ", 1)[0]
    return corte.rstrip(",;:")


# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------

def dominio(url: str) -> str:
    net = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    net = net.split("@")[-1].split(":")[0]
    return net[4:] if net.startswith("www.") else net


_SUFIXOS_DUPLOS = {"co.uk", "org.uk", "ac.uk", "com.br", "org.br", "gov.br", "co.jp", "or.jp", "ne.jp",
                   "com.au", "com.mx", "com.ar", "com.co", "co.kr", "co.in", "co.za", "com.sg", "co.nz", "com.tr"}


def registravel(url: str) -> str:
    """Dominio que identifica a empresa: api.delve.ai e www.delve.ai viram delve.ai."""
    partes = dominio(url).split(".")
    n = 3 if ".".join(partes[-2:]) in _SUFIXOS_DUPLOS else 2
    return ".".join(partes[-n:])


def canonica(url: str) -> str:
    p = urlparse(url.strip())
    if not p.scheme:
        p = urlparse("https://" + url.strip())
    caminho = p.path or "/"
    if caminho != "/" and caminho.endswith("/"):
        caminho = caminho[:-1]
    manter = "&".join(q for q in p.query.split("&")
                      if q and not q.lower().startswith(("utm_", "ref=", "gclid", "fbclid")))
    return urlunparse((p.scheme.lower(), p.netloc.lower(), caminho, "", manter, ""))


def casa_dominio(url: str, padrao: str) -> bool:
    """padrao pode ser so dominio (g2.com) ou dominio com caminho (linkedin.com/in/)."""
    d = dominio(url)
    if "/" in padrao:
        dom, caminho = padrao.split("/", 1)
        return (d == dom or d.endswith("." + dom)) and urlparse(url).path.lstrip("/").startswith(caminho)
    return d == padrao or d.endswith("." + padrao)


# --------------------------------------------------------------------------
# Pagina guardada
# --------------------------------------------------------------------------

@dataclass
class Pagina:
    url: str
    url_final: str = ""
    estado: str = ""            # ok | not accessible | erro
    status: int = 0
    motivo: str = ""
    metodo: str = ""            # urllib | chromium | pdf
    coletado_em: str = ""
    titulo: str = ""
    h1: list[str] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    texto: str = ""
    alts: list[str] = field(default_factory=list)
    jsonld: list = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    iframes: list[str] = field(default_factory=list)
    bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.estado == "ok"

    @property
    def data(self) -> str:
        return self.coletado_em[:10]

    def texto_validacao(self) -> str:
        """Tudo o que esta escrito na pagina e pode ser citado: corpo,
        titulo, metadados, texto alternativo de imagem, JSON-LD e o destino
        dos links e videos embutidos (para citar a URL de um video)."""
        partes = [self.titulo, self.texto, *self.meta.values(), *self.alts,
                  *self.h1, json.dumps(self.jsonld, ensure_ascii=False),
                  *self.iframes, *(l["href"] for l in self.links)]
        return "\n".join(p for p in partes if p)

    def frases(self) -> list[str]:
        # guardado fora dos campos da dataclass: asdict nao leva para o disco
        if "_frases" in self.__dict__:
            return self.__dict__["_frases"]
        saida: list[str] = []
        for linha in self.texto.split("\n"):
            linha = normalizar(linha)
            if len(linha) < 25:
                continue
            for f in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", linha):
                if len(f) >= 25:
                    saida.append(f)
        self.__dict__["_frases"] = saida
        return saida


def _slug(url: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", url.lower().split("://", 1)[-1]).strip("-")[:70]
    return f"{base}-{hashlib.sha256(url.encode()).hexdigest()[:10]}"


def _analisar_html(p: Pagina, html: str) -> None:
    sopa = BeautifulSoup(html, "lxml")
    for s in sopa.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            p.jsonld.append(json.loads(s.string or ""))
        except Exception:
            pass
    meta: dict[str, str] = {}
    for m in sopa.find_all("meta"):
        chave = (m.get("property") or m.get("name") or "").lower()
        valor = m.get("content")
        if valor and chave in {
            "description", "og:title", "og:description", "og:site_name",
            "twitter:title", "twitter:description", "citation_title",
            "citation_abstract", "citation_date", "citation_publication_date",
            "citation_online_date", "citation_journal_title", "citation_doi",
            "dc.title", "dc.description", "dc.date", "article:published_time",
            "citation_author",
        }:
            meta[chave] = meta.get(chave, "") + ((" ; " + valor) if chave in meta else valor)
    p.meta = {k: normalizar(v) for k, v in meta.items()}
    p.titulo = normalizar(sopa.title.get_text(" ") if sopa.title else "")
    for f in sopa.find_all("iframe"):
        if f.get("src"):
            p.iframes.append(urljoin(p.url_final or p.url, f["src"]))
    for v in sopa.find_all(["video", "source"]):
        if v.get("src"):
            p.iframes.append(urljoin(p.url_final or p.url, v["src"]))
    base = p.url_final or p.url
    vistos = set()
    for a in sopa.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absoluta = canonica(urljoin(base, href))
        if absoluta in vistos:
            continue
        vistos.add(absoluta)
        p.links.append({"href": absoluta, "texto": normalizar(a.get_text(" "))[:120]})
    for img in sopa.find_all("img"):
        alt = normalizar(img.get("alt") or "")
        if alt:
            p.alts.append(alt)
    for tag in sopa(["script", "style", "noscript", "template", "svg", "iframe"]):
        tag.decompose()
    p.h1 = [normalizar(h.get_text(" ")) for h in sopa.find_all("h1") if normalizar(h.get_text(" "))]
    for br in sopa.find_all("br"):
        br.replace_with("\n")
    texto = sopa.get_text("\n")
    linhas = [normalizar(x) for x in texto.split("\n")]
    p.texto = "\n".join(x for x in linhas if x)[:MAX_TEXTO]


def _analisar_pdf(p: Pagina, dados: bytes) -> None:
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(dados))
    paginas = []
    for pg in leitor.pages[:80]:
        try:
            paginas.append(pg.extract_text() or "")
        except Exception:
            paginas.append("")
    info = leitor.metadata or {}
    p.titulo = normalizar(str(info.get("/Title") or ""))
    # PDF quebra linha no meio da frase; junta tudo e reparte por frase
    corrido = normalizar(" ".join(paginas))
    corrido = re.sub(r"(\w)- (\w)", r"\1\2", corrido)
    p.texto = "\n".join(re.split(r"(?<=[.!?])\s+(?=[A-Z])", corrido))[:MAX_TEXTO]


class CachePaginas:
    """Cache em disco, uma pagina por arquivo. Retomavel por construcao:
    pagina ja guardada nao e buscada de novo."""

    def __init__(self, raiz: Path, bloqueios: dict[str, str] | None = None):
        self.dir = raiz / "paginas"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bloqueios = bloqueios or {}
        self._ultimo: dict[str, float] = {}
        self._mem: dict[str, Pagina] = {}
        self.stats = {"abertas_agora": 0, "do_cache": 0, "urllib": 0, "chromium": 0,
                      "pdf": 0, "not_accessible": 0, "erro": 0, "bytes": 0}

    def _arquivo(self, url: str) -> Path:
        return self.dir / f"{_slug(url)}.json"

    def obter(self, url: str) -> Pagina | None:
        url = canonica(url)
        if url in self._mem:
            return self._mem[url]
        arq = self._arquivo(url)
        if arq.exists():
            d = ler_json(arq)
            p = Pagina(**d)
            self._mem[url] = p
            return p
        return None

    def _guardar(self, p: Pagina) -> Pagina:
        gravar_json(self._arquivo(p.url), asdict(p), indent=0)
        self._mem[p.url] = p
        return p

    def _pausar(self, url: str) -> None:
        d = dominio(url)
        espera = PAUSA_DOMINIO - (time.time() - self._ultimo.get(d, 0))
        if espera > 0:
            time.sleep(espera)
        self._ultimo[d] = time.time()

    def abrir(self, url: str, *, navegador: bool = True) -> Pagina:
        url = canonica(url)
        guardada = self.obter(url)
        if guardada is not None and guardada.estado != "erro":
            self.stats["do_cache"] += 1
            return guardada

        p = Pagina(url=url, coletado_em=datetime.now(timezone.utc).isoformat())
        for padrao, motivo in self.bloqueios.items():
            if casa_dominio(url, padrao):
                # bloqueio conhecido: uma tentativa, para registrar o status real
                p.motivo = f"bloqueio conhecido ({motivo})"
                break

        if not permitido(url, agente=UA, silencioso=True):
            p.estado, p.motivo = "not accessible", "robots.txt proibe"
            self.stats["not_accessible"] += 1
            return self._guardar(p)

        self._pausar(url)
        self.stats["abertas_agora"] += 1
        try:
            req = Request(url, headers={"User-Agent": UA,
                                        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,es;q=0.7"})
            with urlopen(req, timeout=30) as r:
                dados = r.read(8_000_000)
                p.status = r.status
                p.url_final = canonica(r.geturl())
                tipo = r.headers.get("Content-Type", "")
        except HTTPError as e:
            p.status = e.code
            if e.code in BLOQUEIO_HTTP:
                p.estado = "not accessible"
                p.motivo = f"HTTP {e.code}" + (f"; {p.motivo}" if p.motivo else "")
                self.stats["not_accessible"] += 1
            else:
                p.estado, p.motivo = "erro", f"HTTP {e.code}"
                self.stats["erro"] += 1
            return self._guardar(p)
        except (URLError, TimeoutError, OSError, ValueError) as e:
            p.estado, p.motivo = "erro", f"{type(e).__name__}: {str(e)[:120]}"
            self.stats["erro"] += 1
            return self._guardar(p)

        p.bytes = len(dados)
        self.stats["bytes"] += len(dados)
        if "pdf" in tipo.lower() or dados[:5] == b"%PDF-":
            try:
                _analisar_pdf(p, dados)
                p.metodo, p.estado = "pdf", "ok"
                self.stats["pdf"] += 1
            except Exception as e:
                p.estado, p.motivo = "erro", f"PDF ilegivel: {type(e).__name__}"
                self.stats["erro"] += 1
            return self._guardar(p)

        html = dados.decode("utf-8", errors="replace")
        _analisar_html(p, html)
        p.metodo, p.estado = "urllib", "ok"
        self.stats["urllib"] += 1

        if navegador and len(p.texto) < MIN_TEXTO:
            self._via_navegador(p)
        return self._guardar(p)

    def _via_navegador(self, p: Pagina) -> None:
        """Pagina respondeu 200 com pouco texto: renderiza com o Chromium da
        camada de coleta (scraper_lab.coleta) e fica com a versao mais rica."""
        try:
            from scraper_lab.coleta import coletar

            pag = coletar([p.url_final or p.url])[0]
            renderizada = Pagina(url=p.url, url_final=p.url_final, status=p.status,
                                 coletado_em=p.coletado_em)
            _analisar_html(renderizada, pag.html)
            if len(renderizada.texto) > len(p.texto):
                for campo_ in ("titulo", "h1", "meta", "texto", "alts", "jsonld", "links", "iframes"):
                    setattr(p, campo_, getattr(renderizada, campo_))
                p.metodo = "chromium"
                self.stats["chromium"] += 1
        except Exception as e:
            p.motivo = f"chromium falhou: {type(e).__name__}"

    def todas(self) -> list[Pagina]:
        return [Pagina(**ler_json(a)) for a in sorted(self.dir.glob("*.json"))]

