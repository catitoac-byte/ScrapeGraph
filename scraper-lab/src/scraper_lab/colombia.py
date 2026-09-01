"""
Extrator das afiliadas da ACEI, a Asociacion Colombiana de Empresas de
Investigacion de Mercados y Opinion Publica (acei.co).

Qual e a associacao nacional
----------------------------
A ACEI e o gremio das empresas de pesquisa. A ANDA Colombia, a outra
candidata, reune anunciantes, nao institutos, entao ficou de fora.
O robots.txt da ACEI e `Allow: /`, sem nenhuma restricao.

O que a fonte publica e o que nao publica
-----------------------------------------
A pagina /afiliados/miembros-activos/ traz, para cada afiliada, o logo, um
texto de apresentacao e o link "Visitar sitio Web". Nao ha e-mail nem
telefone em lugar nenhum do site: a area /members/ e um diretorio de contas
com dois cadastros da propria ACEI, e a "Base Interagencias" exige login,
que este projeto nao faz.

O nome da empresa tambem nao aparece como texto, so no arquivo do logo.
Ele e derivado dai e conferido contra o dominio do site; quando os dois nao
conversam, `revisar_nome` marca o registro em vez de fingir certeza.
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

LISTAGEM = "https://acei.co/afiliados/miembros-activos/"
PAIS = "Colombia"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

_ESPACOS = re.compile(r"\s+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NAO_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$", re.I)
_EMAIL_PLACEHOLDER = re.compile(
    r"^(usuario|user|ejemplo|example|correo|email|e-mail|nombre|tu|su|abc|test|"
    r"sample)@(dominio|domain|ejemplo|example|correo|email|tudominio|"
    r"sudominio|mail)\.", re.I)

_DOMINIO_IGNORADO = ("acei.co", "google.com", "wordpress.org", "gravatar.com")
# Nao visitamos LinkedIn: o robots.txt deles proibe todo agente.
_DOMINIO_SOCIAL = ("linkedin.com", "facebook.com", "instagram.com",
                   "twitter.com", "x.com", "youtube.com")

# Sufixos e prefixos que sobram no nome do arquivo do logo.
_SUFIXOS_LOGO = [
    (re.compile(r"-e\d{10,}$"), ""),                        # id de edicao
    (re.compile(r"[-_]\d{2,4}x\d{2,4}\d*$"), ""),           # tamanho da miniatura
    (re.compile(r"[-_]?mesa[-_]de[-_]trabajo[-_]?\d*$", re.I), ""),
    (re.compile(r"[-_]?artboard[-_]?\d*$", re.I), ""),
    (re.compile(r"^(logos?|nuevo[-_]logo)[-_]", re.I), ""),
    (re.compile(r"[-_](logo|logotipo|footer|verde|blanco|negro|black|white|"
                r"rgb|cmyk|peque[nñ]o|grande|final|horizontal|hr|\d+)$", re.I), ""),
    (re.compile(r"[-_]+$"), ""),
]
# Arquivos genericos: nao dizem nada sobre a empresa.
_LOGO_GENERICO = re.compile(r"^(logos?|imagen?|img|image\d*|descarga|sin[-_]?"
                            r"titulo|untitled|foto|picture|screenshot)$", re.I)

_VISITAR = re.compile(r"visitar\s+sitio", re.I)


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _baixar(url: str, timeout: int = 40) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe: {url}")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(4_000_000).decode("utf-8", errors="replace")


def _dominio(url: str) -> str:
    return url.split("//", 1)[-1].split("/")[0].lower().removeprefix("www.")


def _rotulo_dominio(url: str) -> str:
    """Parte identificadora do dominio, sem www, sem TLD e sem subdominio."""
    partes = [p for p in _dominio(url).split(".") if p]
    while len(partes) > 1 and len(partes[-1]) <= 3:
        partes.pop()
    return partes[-1] if partes else ""


def _so_letras(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def _nome_do_logo(src: str, url_site: str) -> str:
    base = src.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    anterior = None
    while anterior != base:
        anterior = base
        for rx, sub in _SUFIXOS_LOGO:
            base = rx.sub(sub, base)
    if not base or _LOGO_GENERICO.match(base):
        # "LOGO.jpg" e "image002.png" nao identificam ninguem; o dominio sim.
        base = _rotulo_dominio(url_site)
    palavras = [p for p in re.split(r"[-_\s]+", base) if p]
    return " ".join(p if p.isupper() else p.capitalize() for p in palavras)


def _normalizar_email(v: str) -> str:
    v = _ESPACOS.sub("", (v or "").strip().lower()).strip(".,;:")
    if not v or _NAO_EMAIL.search(v) or _EMAIL_PLACEHOLDER.match(v):
        return ""
    if any(d in v.split("@")[-1] for d in _DOMINIO_IGNORADO):
        return ""
    return v


@dataclass
class Afiliada:
    url_perfil: str          # a ACEI nao tem ficha; guardamos a pagina de origem
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""       # a fonte nao publica telefone
    endereco: str = ""
    descricao: str = ""
    dominio: str = ""
    arquivo_logo: str = ""
    perfil_social: str = ""
    revisar_nome: str = ""
    coletado_em: str = ""
    erro: str = ""


def _blocos(sopa: BeautifulSoup) -> list:
    """
    Cada afiliada e uma coluna com a borda arredondada do tema.

    Selecionar pela classe do bloco, e nao por posicao, evita quebrar quando
    a ACEI reordena ou inclui uma afiliada no meio da pagina.
    """
    return sopa.select("div.fusion-layout-column.green-border")


def _descricao(bloco) -> str:
    """
    Texto de apresentacao da afiliada.

    Ler so os <p> perdia registros: pelo menos uma afiliada (Metis) tem o
    texto solto dentro da div, sem paragrafo nenhum. Por isso pegamos o texto
    do bloco inteiro e tiramos apenas o rotulo do link "Visitar sitio Web".
    """
    copia = BeautifulSoup(str(bloco), "html.parser")
    for a in copia.find_all("a"):
        if _VISITAR.search(a.get_text(" ")):
            a.decompose()
    return _limpar(copia.get_text(" "))[:1200]


def listar_afiliadas(html: str | None = None) -> list[Afiliada]:
    if html is None:
        html = _baixar(LISTAGEM)
    sopa = BeautifulSoup(html, "html.parser")
    agora = datetime.now(timezone.utc).isoformat()

    afiliadas: list[Afiliada] = []
    for bloco in _blocos(sopa):
        reg = Afiliada(url_perfil=LISTAGEM, coletado_em=agora)

        img = bloco.find("img")
        src = (img.get("src") or "") if img else ""
        reg.arquivo_logo = src.rsplit("/", 1)[-1]

        for a in bloco.select("a[href^=http]"):
            href = a["href"].split("?")[0].split("#")[0].rstrip("/")
            dominio = _dominio(href)
            if any(d in dominio for d in _DOMINIO_IGNORADO):
                continue
            if any(d in dominio for d in _DOMINIO_SOCIAL):
                reg.perfil_social = reg.perfil_social or href
                continue
            reg.site, reg.dominio = href, dominio
            break

        # A ACEI nao publica e-mail, mas se um dia publicar nao queremos
        # descobrir isso tarde: varremos o bloco de qualquer forma.
        for a in bloco.select('a[href^="mailto:"]'):
            v = _normalizar_email(a["href"][7:].split("?")[0])
            if v:
                reg.email = v
                break
        if not reg.email:
            for bruto in _EMAIL.findall(bloco.get_text(" ")):
                v = _normalizar_email(bruto)
                if v:
                    reg.email = v
                    break

        reg.descricao = _descricao(bloco)

        reg.nome = _limpar(img.get("alt")) if img else ""
        if not reg.nome:
            reg.nome = _nome_do_logo(src, reg.site)

        rotulo = _so_letras(_rotulo_dominio(reg.site)) if reg.site else ""
        nome_norm = _so_letras(reg.nome)
        if (not rotulo or len(nome_norm) < 3
                or (nome_norm not in rotulo and rotulo not in nome_norm)):
            reg.revisar_nome = "sim"

        if not (reg.nome and (reg.site or reg.descricao)):
            reg.erro = "bloco sem nome nem canal de contato"
        afiliadas.append(reg)
    return afiliadas


def coletar(*, delay: float = 1.6, verbose: bool = True) -> list[Afiliada]:
    afiliadas = listar_afiliadas()
    if verbose:
        for i, a in enumerate(afiliadas, 1):
            marca = "?" if (a.revisar_nome or a.erro) else "."
            print(f"  [{i:>2}/{len(afiliadas)}] {marca} {a.nome[:24]:24} | "
                  f"{a.site[:42]:42} | {len(a.descricao):>4} car.")
    time.sleep(delay)
    return afiliadas


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "descricao",
           "dominio", "perfil_social", "revisar_nome", "arquivo_logo",
           "url_perfil", "erro"]


def exportar(regs: list[Afiliada], nome: str = "acei_colombia") -> tuple[Path, Path]:
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
