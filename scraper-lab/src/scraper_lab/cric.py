"""
Extrator do diretorio de membros do CRIC (Canadian Research Insights Council).

O robots.txt do dominio tem um unico Disallow (/wp-admin/) com Allow para
admin-ajax.php. Nada do diretorio cai nele, e o verificador confirma cada
URL antes da requisicao. O host canonico e www.: a raiz sem www devolve 301.

O CRIC publica tres coisas diferentes, e so duas servem:

1. /member-directory/  -> pagina estatica com o elenco de membros. Traz nome
   e site de cada empresa, sem e-mail nem telefone. E a fonte principal.

2. /rvs/company-directory/ -> diretorio do Research Verification Service,
   renderizado no cliente a partir de organization/search.php. Traz o
   selo de agencia credenciada, que a pagina estatica so indica pela secao.
   Usamos como fonte complementar e como conferencia do total.

3. /find-a-supplier/ -> diretorio GeoDirectory, com ficha rica por empresa.
   Esta vazio: o endpoint geodir/v2/places devolve X-WP-Total 1, e o unico
   registro publicado e um teste do proprio CRIC. Nao entra na base.

Bilinguismo: /member-directory/?lang=fr lista as mesmas 123 empresas, com
oito nomes traduzidos e os links apontando para a versao francesa do site de
cada uma (manulife.ca vira manuvie.ca, surveysampler.com vira
echantillonneur.com). Nao existe chave confiavel para casar as duas edicoes
(nome muda, dominio muda, e posicao nao e chave), entao coletamos so a
edicao inglesa. A conferencia por dominio raiz mostrou 122 dominios de cada
lado, sem nenhuma empresa exclusiva do frances.
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

# Reaproveitamos o decodificador de e-mail do Cloudflare ja validado na ABEP.
from scraper_lab.abep import decodifica_cfemail
from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.canadianresearchinsightscouncil.ca"
DIRETORIO = f"{BASE}/member-directory/"
DIRETORIO_RVS = f"{BASE}/rvs/company-directory/"
# Mesma consulta que a pagina publica do RVS dispara ao carregar. E leitura:
# devolve a lista de organizacoes. Os endpoints de cadastro e de envio de
# comentario ficam intocados.
API_RVS = f"{BASE}/rvs/api/organization/search.php"

PAIS = "Canada"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

_DOMINIO_ASSOCIACAO = "canadianresearchinsightscouncil.ca"
_ESPACOS = re.compile(r"\s+")
_VAZIOS = {"", "-", "--", "n/a", "na"}
# Uma secao do diretorio tem dezenas de links; menu e rodape tem poucos.
_MIN_LINKS_SECAO = 5


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", (texto or "").replace("\xa0", " ")).strip()
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


def _baixar(url: str, timeout: int = 40) -> str:
    """Requisicao GET do modulo, sempre precedida da checagem de robots."""
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        bruto = r.read(4_000_000)
        ctype = r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    try:
        return bruto.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        return bruto.decode("utf-8", errors="replace")


@dataclass
class Membro:
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    tipo_membro: str = ""
    credenciada: str = ""
    # As duas fontes do CRIC discordam sobre quem e credenciado, entao a
    # coluna registra quem afirmou o que em vez de esconder a divergencia.
    origem_credenciamento: str = ""
    fonte: str = ""
    url_perfil: str = ""
    coletado_em: str = ""
    erro: str = ""
    emails_extras: list[str] = field(default_factory=list)


def _resolver_email_cloudflare(href: str) -> str:
    """
    O CRIC serve por Cloudflare, que troca alguns mailto por
    /cdn-cgi/l/email-protection#<hex>. Sem decodificar, o link vira lixo no
    campo de site.
    """
    if "/cdn-cgi/l/email-protection" not in href:
        return ""
    _, _, hexstr = href.partition("#")
    return decodifica_cfemail(hexstr)


def _links_da_secao(secao) -> list[tuple[str, str]]:
    """
    Pares (nome, href) de uma secao do diretorio.

    O HTML tem ancoras aninhadas: em "Elemental Data Collection" o editor
    deixou um <a> para environicsanalytics.com por fora do <a> correto para
    elementaldci.com. Quem varre todas as ancoras leva o site errado. Ficamos
    so com a ancora mais interna, que e a que envolve de fato o nome.
    """
    pares: list[tuple[str, str]] = []
    for a in secao.select("a[href]"):
        if a.find("a"):
            continue
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or _DOMINIO_ASSOCIACAO in href:
            continue
        nome = _limpar(a.get_text(" ", strip=True))
        if nome:
            pares.append((nome, href))
    return pares


def _secoes_do_diretorio(html: str) -> list[tuple[str, list[tuple[str, str]]]]:
    sopa = BeautifulSoup(html, "html.parser")
    for t in sopa(["script", "style", "noscript"]):
        t.decompose()
    achados = []
    for secao in sopa.select("div.et_pb_section"):
        pares = _links_da_secao(secao)
        if len(pares) < _MIN_LINKS_SECAO:
            continue
        titulo = secao.find(["h1", "h2", "h3", "h4"])
        rotulo = _limpar(titulo.get_text(" ", strip=True)) if titulo else ""
        achados.append((rotulo.lstrip("—- ").strip(), pares))
    return achados


def listar_membros(*, verbose: bool = True) -> list[Membro]:
    """
    Empresas das secoes do /member-directory/.

    A pagina nao pagina: e um layout Divi com o elenco inteiro. Ainda assim,
    zero secoes e tratado como suspeita e refeito uma vez antes de virar
    veredito, porque erro transitorio nao e ausencia de dado.
    """
    secoes = _secoes_do_diretorio(_baixar(DIRETORIO))
    if not secoes:
        time.sleep(3.0)
        secoes = _secoes_do_diretorio(_baixar(DIRETORIO))

    agora = datetime.now(timezone.utc).isoformat()
    por_chave: dict[str, Membro] = {}
    for rotulo, pares in secoes:
        if verbose:
            print(f"      {rotulo[:52]:52} {len(pares):>3} empresas")
        for nome, href in pares:
            email = _resolver_email_cloudflare(href)
            reg = Membro(nome=nome, pais=PAIS, tipo_membro=rotulo,
                         fonte="member-directory", url_perfil=DIRETORIO,
                         coletado_em=agora)
            if email:
                reg.email = email
            else:
                reg.site = href
            if "accredited" in rotulo.lower():
                reg.credenciada = "sim"
                reg.origem_credenciamento = "diretorio"

            # MD Analytics aparece nas duas secoes com o mesmo dominio. Uma
            # linha por empresa, com as duas categorias registradas.
            chave = _chave_dominio(reg.site) or _chave_nome(nome)
            anterior = por_chave.get(chave)
            if anterior is None:
                por_chave[chave] = reg
            elif rotulo not in anterior.tipo_membro:
                anterior.tipo_membro = f"{anterior.tipo_membro} | {rotulo}"
    return list(por_chave.values())


def _chave_dominio(site: str) -> str:
    """Dominio raiz, sem www, usado para deduplicar."""
    if not site or not site.startswith("http"):
        return ""
    return urllib.parse.urlparse(site).netloc.lower().removeprefix("www.")


_SUFIXOS = re.compile(r"\b(inc|ltd|llc|corp|corporation|limited|co|company|"
                      r"group|the|and|of|srl|sa|ulc|lp)\b")


def _chave_nome(nome: str) -> str:
    """Nome reduzido a tokens comparaveis, sem pontuacao nem sufixo juridico."""
    t = unicodedata.normalize("NFKD", nome.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = _SUFIXOS.sub(" ", t)
    return _ESPACOS.sub(" ", t).strip()


def _sublista(menor: list[str], maior: list[str]) -> bool:
    """menor aparece em maior como sequencia contigua de tokens."""
    n = len(menor)
    return any(maior[i:i + n] == menor for i in range(len(maior) - n + 1))


def _mesma_empresa(a: str, b: str) -> bool:
    """
    Casamento conservador entre nomes vindos de fontes diferentes.

    Tres criterios, todos exigindo que um nome esteja inteiro dentro do
    outro: igualdade das chaves, igualdade sem espacos ("Utility Pulse Inc."
    x "UtilityPULSE inc.") e sequencia contigua de tokens ("Ekos" x "Ekos
    Research Associates", "The Payroll Institute" x "National Payroll
    Institute"). Contiguidade e proposital: com simples interseccao de
    tokens, qualquer par que dividisse a palavra "research" casaria.

    Token unico curto nao vale como chave, senao siglas de duas letras
    grudariam em nomes sem relacao.
    """
    if not a or not b:
        return False
    if a == b or a.replace(" ", "") == b.replace(" ", ""):
        return True
    ta, tb = a.split(), b.split()
    menor, maior = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(menor) == 1 and len(menor[0]) < 4:
        return False
    return _sublista(menor, maior)


def buscar_rvs(*, timeout: int = 40) -> list[dict]:
    """
    Organizacoes do Research Verification Service.

    O endpoint recebe POST porque e assim que a pagina publica consulta, mas
    a chamada e de leitura: manda busca vazia e ordenacao, nao grava nada.

    A resposta inclui nome e e-mail da pessoa de contato de cada empresa,
    campos que a pagina publica nao mostra. Sao dados pessoais expostos por
    descuido da API, e nao entram na base: guardamos apenas os campos que o
    diretorio de fato publica.
    """
    if not robots_permitido(API_RVS, agente=UA):
        raise PermissionError(f"robots.txt proibe {API_RVS}")
    corpo = urllib.parse.urlencode({"search": "", "sort_by": "name",
                                    "lang": "en"}).encode()
    req = Request(API_RVS, data=corpo,
                  headers={"User-Agent": UA,
                           "Content-Type": "application/x-www-form-urlencoded",
                           "X-Requested-With": "XMLHttpRequest"})
    with urlopen(req, timeout=timeout) as r:
        bruto = json.loads(r.read(4_000_000).decode("utf-8", errors="replace"))
    return [{"nome": _limpar(o.get("name")),
             "membro": bool(o.get("is_cric_member")),
             "credenciada": bool(o.get("is_accredited"))}
            for o in bruto if _limpar(o.get("name"))]


# O proprio CRIC tem cadastro no RVS; nao e uma empresa da base. "test" vai
# com fronteira de palavra: sem ela, "R.A. Malatest & Associates" cairia fora.
_NAO_EMPRESA = re.compile(r"canadian research insights council|conseil de recherche"
                          r"|^cric\b|\btest\b", re.I)


def cruzar_com_rvs(membros: list[Membro], registros: list[dict],
                   *, verbose: bool = True) -> list[Membro]:
    """
    Marca credenciamento a partir do RVS e acrescenta empresas que so ele
    conhece.

    O RVS e uma base viva; a pagina de membros e mantida a mao e esta
    defasada. Quem so aparece no RVS entra como linha propria, com fonte
    declarada e sem site, para nao inventar dado que nao existe.
    """
    chaves = [(_chave_nome(m.nome), m) for m in membros]
    agora = datetime.now(timezone.utc).isoformat()
    novos: list[Membro] = []
    casados = ambiguos = 0

    for reg in registros:
        if _NAO_EMPRESA.search(reg["nome"]):
            continue
        alvo = _chave_nome(reg["nome"])
        achados = [m for k, m in chaves if _mesma_empresa(alvo, k)]

        if len(achados) == 1:
            casados += 1
            if reg["credenciada"]:
                achados[0].credenciada = "sim"
                achados[0].origem_credenciamento = (
                    "diretorio + rvs" if achados[0].origem_credenciamento else "rvs")
            achados[0].fonte = "member-directory + rvs"
            continue

        # Nome que casa com mais de uma empresa do diretorio nao vira
        # decisao automatica: entra como linha propria com o erro marcado,
        # para alguem conferir. Escolher uma das duas seria chutar.
        erro = ""
        if len(achados) > 1:
            ambiguos += 1
            erro = ("nome casa com mais de uma empresa do diretorio: "
                    + " / ".join(m.nome for m in achados))[:200]
        novos.append(Membro(nome=reg["nome"], pais=PAIS,
                            tipo_membro="CRIC member (via RVS)",
                            credenciada="sim" if reg["credenciada"] else "",
                            origem_credenciamento="rvs" if reg["credenciada"] else "",
                            fonte="rvs", url_perfil=DIRETORIO_RVS,
                            coletado_em=agora, erro=erro))

    if verbose:
        print(f"      RVS: {len(registros)} organizacoes, {casados} casadas "
              f"com o diretorio, {len(novos) - ambiguos} exclusivas, "
              f"{ambiguos} ambiguas")
    return membros + novos


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco",
           "tipo_membro", "credenciada", "origem_credenciamento", "descricao",
           "fonte", "emails_extras", "url_perfil", "erro"]


def exportar(membros: list[Membro], nome: str = "cric") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(m) for m in membros], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for m in membros:
            d = asdict(m)
            d["emails_extras"] = " | ".join(d.get("emails_extras") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
