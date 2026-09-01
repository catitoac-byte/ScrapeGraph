"""
Extrator das empresas socias da CEIM, a Camara de Empresas de Investigacion
Social y de Mercado da Argentina (ceim.org.ar).

Por que CEIM e nao SAIMO
------------------------
A SAIMO responde em https://saimo.org.ar/ (sem www; o certificado do host
com www e de outro dominio e a conexao falha na verificacao). Mas a SAIMO
reune pesquisadores pessoa fisica e a pagina /socios/ traz apenas
"Proximamente": nao existe diretorio de empresas publicado. Quem agrupa as
empresas argentinas de pesquisa e a CEIM, e e dela que sai esta base.
`estado_diretorio_saimo()` reconfere isso a cada execucao, para que o dia em
que a SAIMO publicar a lista nao passe despercebido.

Limite conhecido desta fonte
----------------------------
A CEIM nao publica ficha por socia: o que existe e uma faixa de logos com
link para o site de cada empresa. Sai nome e site, nunca e-mail ou telefone.
O nome tambem nao aparece como texto, so no arquivo do logo, entao ele e
derivado e vem com `revisar_nome` marcado quando nao bate com o dominio.

robots.txt da CEIM proibe /wp-admin/ e nada mais que nos interesse; o
verificador confere cada URL antes da requisicao.
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

LISTAGEM = "https://ceim.org.ar/"
SOBRE = "https://ceim.org.ar/quienes-somos/"
SAIMO_SOCIOS = "https://saimo.org.ar/socios/"
PAIS = "Argentina"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

_ESPACOS = re.compile(r"\s+")

# Dominios da propria camara e de servicos: aparecem no rodape junto dos
# logos das socias e nao sao empresa de pesquisa.
_DOMINIO_IGNORADO = ("ceim.org.ar", "saimo.org.ar", "scidata.com.ar",
                     "google.com", "drive.google.com", "youtu.be",
                     "youtube.com", "facebook.com", "instagram.com",
                     "twitter.com", "x.com", "wordpress.org")
# LinkedIn entra aqui por regra do projeto: o robots.txt deles proibe todo
# agente, entao a URL e apenas registrada, nunca visitada.
_DOMINIO_SOCIAL = ("linkedin.com",)

# Sufixos que o WordPress e o time de design deixam no nome do arquivo.
_SUFIXOS_LOGO = [
    (re.compile(r"-e\d{10,}$"), ""),                    # id de edicao
    (re.compile(r"[-_]\d{2,4}x\d{2,4}$"), ""),          # tamanho da miniatura
    (re.compile(r"^\d{1,2}[-_]"), ""),                  # numeracao do carrossel
    (re.compile(r"^(logos?|nuevo[-_]logo)[-_]", re.I), ""),
    (re.compile(r"[-_](logo|logotipo|footer|verde|blanco|negro|black|white|"
                r"rgb|peque[nñ]o|grande|final|horizontal|hr|\d+)$", re.I), ""),
]


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _baixar(url: str, timeout: int = 40) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe: {url}")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(4_000_000).decode("utf-8", errors="replace")


def _dominio(url: str) -> str:
    return url.split("//", 1)[-1].split("/")[0].lower().removeprefix("www.")


def _rotulo_dominio(url: str) -> str:
    """Parte identificadora do dominio, sem www, sem TLD e sem subdominio."""
    partes = [p for p in _dominio(url).split(".") if p]
    if not partes:
        return ""
    # descarta os sufixos de pais/genericos do fim (com.ar, org.ar, co, info)
    while len(partes) > 1 and len(partes[-1]) <= 3:
        partes.pop()
    return partes[-1] if partes else ""


def _nome_do_logo(src: str) -> str:
    base = src.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    anterior = None
    while anterior != base:
        anterior = base
        for rx, sub in _SUFIXOS_LOGO:
            base = rx.sub(sub, base)
    palavras = [p for p in re.split(r"[-_\s]+", base) if p]
    return " ".join(p if p.isupper() else p.capitalize() for p in palavras)


def _so_letras(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


@dataclass
class Socia:
    url_perfil: str          # a CEIM nao tem ficha; guardamos a pagina de origem
    nome: str = ""
    email: str = ""          # a fonte nao publica e-mail
    site: str = ""
    pais: str = PAIS
    telefone: str = ""       # a fonte nao publica telefone
    endereco: str = ""
    descricao: str = ""
    dominio: str = ""
    arquivo_logo: str = ""
    perfil_social: str = ""  # quando a camara linka a rede social no lugar do site
    revisar_nome: str = ""   # "sim" quando o nome derivado nao bate com o dominio
    coletado_em: str = ""
    erro: str = ""


def estado_diretorio_saimo() -> str:
    """
    Como esta a pagina de socios da SAIMO.

    Existe para nao repetirmos a investigacao a cada coleta: se um dia sair
    do "Proximamente", a execucao avisa em vez de continuar ignorando a fonte.
    """
    try:
        sopa = BeautifulSoup(_baixar(SAIMO_SOCIOS), "html.parser")
    except Exception as exc:
        return f"nao verificado ({type(exc).__name__})"
    for t in sopa(["script", "style", "noscript", "nav", "header", "footer"]):
        t.decompose()
    corpo = _limpar(sopa.get_text(" ")).lower()
    if "próximamente" in corpo or "proximamente" in corpo:
        return "sem diretorio publicado (pagina diz 'Proximamente')"
    return "MUDOU: a pagina de socios nao diz mais 'Proximamente', reinvestigar"


def total_declarado() -> int:
    """Quantidade de socias que a propria CEIM anuncia, para conferencia."""
    m = re.search(r"participan\s+(\d+)\s+empresas", _baixar(SOBRE), re.I)
    return int(m.group(1)) if m else 0


def listar_socias(html: str | None = None) -> list[Socia]:
    """
    Socias a partir da faixa de logos, que e a unica listagem que a CEIM
    publica. Cada logo e um link para o site da empresa.
    """
    if html is None:
        html = _baixar(LISTAGEM)
    sopa = BeautifulSoup(html, "html.parser")
    agora = datetime.now(timezone.utc).isoformat()

    vistos: set[str] = set()
    socias: list[Socia] = []
    for a in sopa.select("a[href]"):
        img = a.find("img")
        if img is None:
            continue
        href = a["href"].split("?")[0].split("#")[0].rstrip("/")
        if not href.startswith("http"):
            continue
        dominio = _dominio(href)
        if any(d in dominio for d in _DOMINIO_IGNORADO):
            continue
        if href in vistos:
            continue
        vistos.add(href)

        src = img.get("src") or ""
        reg = Socia(url_perfil=LISTAGEM, arquivo_logo=src.rsplit("/", 1)[-1],
                    nome=_limpar(img.get("alt")) or _nome_do_logo(src),
                    coletado_em=agora)
        if any(d in dominio for d in _DOMINIO_SOCIAL):
            # Nao visitamos LinkedIn (robots deles proibe todo agente); a URL
            # fica registrada para conferencia manual, fora do campo `site`.
            reg.perfil_social = href
            reg.erro = "camara linka rede social no lugar do site"
        else:
            reg.site = href
            reg.dominio = dominio

        # O nome sai do arquivo do logo, entao pode nao ser o nome comercial.
        # Marcamos para revisao quando ele nao conversa com o dominio do site.
        rotulo = _so_letras(_rotulo_dominio(href)) if reg.site else ""
        nome_norm = _so_letras(reg.nome)
        if (not rotulo or len(nome_norm) < 3
                or (nome_norm not in rotulo and rotulo not in nome_norm)):
            reg.revisar_nome = "sim"
        socias.append(reg)
    return socias


def coletar(*, delay: float = 1.6, verbose: bool = True) -> list[Socia]:
    """
    Coleta completa. Uma requisicao para a listagem e outra para a pagina
    institucional, que traz o total declarado.
    """
    socias = listar_socias()
    if verbose:
        for i, s in enumerate(socias, 1):
            marca = "?" if (s.revisar_nome or s.erro) else "."
            print(f"  [{i:>2}/{len(socias)}] {marca} {s.nome[:26]:26} | "
                  f"{(s.site or s.perfil_social)[:50]}")
    time.sleep(delay)
    return socias


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "descricao",
           "dominio", "perfil_social", "revisar_nome", "arquivo_logo",
           "url_perfil", "erro"]


def exportar(regs: list[Socia], nome: str = "ceim_argentina") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(r) for r in regs], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for r in regs:
            d = asdict(r)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
