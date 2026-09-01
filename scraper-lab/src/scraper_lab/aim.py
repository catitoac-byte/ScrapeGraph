"""
Extrator dos socios da AIM Chile (aimchile.cl/socios).

Particularidade desta fonte: o diretorio publica apenas logo e link do site
de cada associada. Nao ha nome em texto, nem e-mail, telefone ou endereco.

Por isso a coleta tem duas camadas:
  1. A AIM da a lista de sites das associadas.
  2. Cada site da empresa e visitado para obter nome e e-mail de contato.

A camada 2 respeita o robots.txt de cada dominio e se limita a home mais
algumas paginas de contato. A procedencia de cada campo fica registrada na
coluna `origem_dados`, para nunca confundir o que veio da AIM com o que veio
do site da propria empresa.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

SOCIOS = "https://aimchile.cl/socios/"
BUSCA = "https://aimchile.cl/socios-busqueda/"
SECAO_EMPRESAS = "1151"
PAIS = "Chile"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Paginas onde uma empresa costuma publicar contato.
CAMINHOS_CONTATO = ("", "/contacto", "/contacto/", "/contact", "/contactanos",
                    "/quienes-somos", "/nosotros")

# Enderecos de servico que nao servem como contato comercial.
_LIXO_EMAIL = re.compile(
    r"(sentry|wixpress|\.png|\.jpg|\.gif|\.webp|@sentry|noreply|no-reply|@2x|"
    # placeholders de formulario, em ingles e espanhol
    r"example\.|ejemplo|domain\.com|dominio\.com|tudominio|yourdomain|"
    r"email\.com|correo\.com|usuario@|user@|nombre@|tucorreo)", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ESPACOS = re.compile(r"\s+")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _uma_tentativa(url: str, timeout: int) -> str:
    req = Request(url, headers={"User-Agent": UA,
                                "Accept-Language": "es-CL,es;q=0.9,pt-BR;q=0.8"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(1_500_000).decode("utf-8", errors="replace")


def _baixar(url: str, timeout: int = 20) -> str:
    """
    Busca a pagina, caindo para http quando o https falha.

    Alguns sites de associadas tem certificado quebrado. Nao desativamos a
    verificacao, que seria abrir espaco para interceptacao; tentamos http e,
    se tambem falhar, deixamos o erro subir com o motivo real.
    """
    try:
        return _uma_tentativa(url, timeout)
    except Exception as exc:
        if "CERTIFICATE" in str(exc).upper() and url.startswith("https://"):
            try:
                return _uma_tentativa("http://" + url[len("https://"):], timeout)
            except Exception as exc2:
                raise RuntimeError(_motivo(exc2)) from None
        raise RuntimeError(_motivo(exc)) from None


def _motivo(exc: Exception) -> str:
    t = str(exc).upper()
    if "CERTIFICATE" in t:
        return "certificado TLS invalido"
    if "TIMED OUT" in t or "TIMEOUT" in t:
        return "tempo esgotado"
    if "NAME OR SERVICE" in t or "NODENAME" in t:
        return "dominio nao resolve"
    return f"{type(exc).__name__}"[:40]


@dataclass
class Socio:
    site: str
    nome: str = ""
    email: str = ""
    pais: str = PAIS
    telefone: str = ""
    logo: str = ""
    origem_dados: str = ""
    coletado_em: str = ""
    erro: str = ""
    emails_extras: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Camada 1: a lista da AIM
# --------------------------------------------------------------------------

def _cards(html: str) -> list[dict]:
    sopa = BeautifulSoup(html, "html.parser")
    saida = []
    for c in sopa.select("a.member"):
        img = c.find("img")
        h6 = c.find("h6")
        sec = c.find_parent("section")
        saida.append({
            "href": (c.get("href") or "").strip(),
            "img": (img.get("src") or "").split("/")[-1] if img else "",
            "nome": _limpar(h6.get_text()) if h6 else "",
            "sec": sec.get("id") if sec else "",
        })
    return saida


def listar_socios() -> list[Socio]:
    """
    Sites das empresas associadas.

    O nome vem da pagina de busca, casado pelo arquivo de logo. Logos com
    nome generico ("sin-titulo") se repetem entre empresas, entao so
    aproveitamos o casamento quando o arquivo aponta para uma unica empresa.
    """
    empresas = [c for c in _cards(_baixar(SOCIOS)) if c["sec"] == SECAO_EMPRESAS]

    contagem: dict[str, set[str]] = {}
    for c in _cards(_baixar(BUSCA)):
        if c["img"] and c["nome"]:
            contagem.setdefault(c["img"], set()).add(c["nome"])
    nomes = {img: next(iter(n)) for img, n in contagem.items() if len(n) == 1}

    agora = datetime.now(timezone.utc).isoformat()
    saida = []
    for c in empresas:
        if not c["href"] or c["href"].startswith("javascript"):
            continue
        nome = nomes.get(c["img"], "")
        saida.append(Socio(site=c["href"], nome=nome, logo=c["img"],
                           coletado_em=agora,
                           origem_dados="aim" if nome else ""))
    return saida


# --------------------------------------------------------------------------
# Camada 2: o site da propria empresa
# --------------------------------------------------------------------------

def pode_acessar(url: str) -> bool:
    """Consulta o robots.txt do dominio com o verificador proprio, que
    entende curingas e busca o arquivo com User-Agent de navegador."""
    return robots_permitido(url, agente=UA)


def _nome_do_html(html: str, dominio: str) -> str:
    sopa = BeautifulSoup(html, "html.parser")
    for og in sopa.select('meta[property="og:site_name"], meta[property="og:title"]'):
        v = _limpar(og.get("content"))
        if v:
            return re.split(r"\s*[|\-–—:]\s*", v)[0].strip()[:80]
    if sopa.title and _limpar(sopa.title.get_text()):
        return re.split(r"\s*[|\-–—:]\s*", _limpar(sopa.title.get_text()))[0].strip()[:80]
    return dominio


# Multinacionais servem o mesmo site global para todos os paises, e dele saem
# enderecos de outra regiao. Num diretorio de socios chilenos, um
# "info.indonesia@kantar.com" parece valido e nao e: vazio informa mais.
_OUTRA_REGIAO = re.compile(
    r"\b(indonesia|brasil|brazil|mexico|argentina|peru|colombia|ecuador|"
    r"bolivia|uruguay|paraguay|venezuela|india|china|japan|korea|usa|uk|"
    r"france|germany|spain|italy|poland|turkey|egypt|nigeria|kenya)\b", re.I)


def _de_outra_regiao(email: str) -> bool:
    return bool(_OUTRA_REGIAO.search(email.split("@")[0]))


def _emails_do_html(html: str) -> list[str]:
    achados = []
    for e in _EMAIL.findall(html):
        e = e.strip(".,;:)").lower()
        if not _LIXO_EMAIL.search(e) and not _de_outra_regiao(e) and e not in achados:
            achados.append(e)
    return achados


def enriquecer(s: Socio, *, delay: float = 1.0, verbose: bool = True) -> Socio:
    """Visita a home e paginas de contato da empresa em busca de nome e e-mail."""
    base = s.site.strip()
    if not base.startswith("http"):
        base = "https://" + base
    dominio = urlparse(base).netloc.replace("www.", "")

    if not pode_acessar(base):
        s.erro = "robots.txt do dominio nao permite"
        if not s.nome:
            s.nome = dominio
        return s

    vistos: list[str] = []
    for caminho in CAMINHOS_CONTATO:
        url = urljoin(base, caminho) if caminho else base
        try:
            if not pode_acessar(url):
                continue
            html = _baixar(url)
        except Exception as exc:
            if caminho == "":
                s.erro = str(exc)[:60]
            continue

        if caminho == "" and not s.nome:
            s.nome = _nome_do_html(html, dominio)
            s.origem_dados = "site-empresa"

        for e in _emails_do_html(html):
            if e not in vistos:
                vistos.append(e)
        if vistos:
            break  # ja achamos contato, nao precisa varrer o resto
        time.sleep(delay)

    if vistos:
        s.email = vistos[0]
        s.emails_extras = vistos[1:5]
        s.origem_dados = (s.origem_dados + "+site-empresa").strip("+") \
            if s.origem_dados != "site-empresa" else "site-empresa"
    if not s.nome:
        s.nome = dominio
    if verbose:
        marca = "!" if s.erro else "."
        print(f"  {marca} {s.nome[:30]:30} | {s.email[:32]:32} | {dominio[:26]}")
    return s


COLUNAS = ["nome", "email", "site", "pais", "telefone", "origem_dados",
           "emails_extras", "logo", "erro"]


def exportar(socios: list[Socio], nome: str = "aim_chile") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(s) for s in socios], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for s in socios:
            d = asdict(s)
            d["emails_extras"] = " | ".join(d.get("emails_extras") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
