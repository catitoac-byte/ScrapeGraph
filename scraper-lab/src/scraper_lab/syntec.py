"""
Extrator dos membros da expertise Etudes do Syntec Conseil (Franca).

Contexto que muda o alvo: a antiga Syntec Etudes foi absorvida pelo Syntec
Conseil. O dominio syntec-etudes.com nao resolve mais, e o ramo de pesquisa
virou uma "expertise" dentro de syntec-conseil.fr. O diretorio que interessa
esta em /expertises/etudes/, sob o titulo "Les membres de l'expertise etudes",
e nao em /nos-membres/, que mistura as 183 empresas de TODAS as disciplinas de
consultoria (recrutamento, coaching, estrategia). Coletar /nos-membres/ inteiro
encheria a base de consultorias que nao fazem pesquisa de mercado.

Conformidade: o robots.txt do Syntec tem uma unica regra Disallow, sobre
/evenements/.../publications_prix_management/, que nao toca o diretorio. Ainda
assim toda URL passa por `permitido()` antes da requisicao. O site responde no
dominio sem www; o verificador le o robots.txt do host de destino.

Limite conhecido da fonte: o Syntec publica somente logotipo, razao social e
link para o site da empresa. Nao ha ficha de perfil, e-mail nem endereco. As
colunas de contato saem vazias de proposito, com o nome e o site preenchidos,
para o enriquecimento posterior trabalhar em cima.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://syntec-conseil.fr"
ETUDES = f"{BASE}/expertises/etudes/"
TODOS_MEMBROS = f"{BASE}/nos-membres/"
PAIS = "France"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# A grade do diretorio usa uma classe propria, `annuaireSyntec`, aplicada so
# aos cartoes de membro. Ancorar nela evita capturar os banners editoriais da
# mesma pagina (manifesto de IA, carta deontologica), que tambem sao figuras
# com imagem e as vezes tem link.
_SELETOR_CARTAO = ".annuaireSyntec"

# Dominios da propria organizacao e redes sociais: nunca sao o site do membro.
_DOMINIO_IGNORADO = ("syntec-conseil.fr", "syntec-etudes.com", "syntec.fr",
                     "linkedin.com", "twitter.com", "x.com", "facebook.com",
                     "youtube.com", "instagram.com")

_ESPACOS = re.compile(r"\s+")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", (t or "").replace("\xa0", " ")).strip()


def _decodificar(bruto: bytes, ctype: str) -> str:
    """
    Resolve a codificacao pelo cabecalho, depois pela meta tag, e so entao
    tenta utf-8 e latin-1.

    Razoes sociais francesas trazem acento agudo, grave e cedilha. Ler utf-8
    como latin-1 grava "Mediametrie" com lixo no lugar do acento sem levantar
    excecao, e o estrago so aparece no CSV final.
    """
    candidatos: list[str] = []
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        candidatos.append(m.group(1))
    m = re.search(rb'charset=["\']?([\w-]+)', bruto[:2048], re.I)
    if m:
        candidatos.append(m.group(1).decode("ascii", "ignore"))
    candidatos += ["utf-8", "latin-1"]
    for enc in candidatos:
        try:
            return bruto.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return bruto.decode("utf-8", errors="replace")


_ESPERA_RETENTATIVA = (0, 5, 12, 25)


def _baixar(url: str, *, timeout: int = 40) -> str:
    """Baixa uma URL aprovada pelo robots, insistindo em falha transitoria."""
    if not robots_permitido(url, agente=UA):
        raise PermissionError("robots.txt proibe")

    cabecalhos = {"User-Agent": UA,
                  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                  "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7"}
    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, headers=cabecalhos), timeout=timeout) as r:
                return _decodificar(r.read(6_000_000), r.headers.get("Content-Type", ""))
        except HTTPError as exc:
            ultimo = exc
            if exc.code in (404, 410):
                break
        except (URLError, TimeoutError, OSError) as exc:
            ultimo = exc
    raise ultimo if ultimo else RuntimeError("falha desconhecida")


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    expertise: str = "Études"
    tambem_em_nos_membros: str = ""
    coletado_em: str = ""
    erro: str = ""


def _cartoes(html: str) -> list[tuple[str, str]]:
    """Pares (nome, site) da grade de membros de uma pagina do Syntec."""
    sopa = BeautifulSoup(html, "html.parser")
    itens: list[tuple[str, str]] = []
    for cartao in sopa.select(_SELETOR_CARTAO):
        img = cartao.find("img")
        # O nome so existe no alt/title do logotipo: o cartao nao tem texto.
        nome = _limpar((img.get("alt") if img else "") or (img.get("title") if img else ""))
        link = cartao.find("a", href=True)
        site = (link["href"] if link else "").strip()
        if site and any(d in urlparse(site).netloc.lower() for d in _DOMINIO_IGNORADO):
            site = ""
        if nome:
            itens.append((nome, site))
    return itens


def listar_membros_etudes(*, verbose: bool = True) -> list[tuple[str, str]]:
    """Membros da expertise Etudes, sem repeticao, na ordem da pagina."""
    itens = _cartoes(_baixar(ETUDES))
    vistos: dict[str, tuple[str, str]] = {}
    for nome, site in itens:
        vistos.setdefault(nome.upper(), (nome, site))
    if verbose:
        print(f"      {len(vistos)} membros na expertise Etudes")
    return list(vistos.values())


def listar_todos_membros(*, verbose: bool = True) -> set[str]:
    """
    Razoes sociais de TODOS os membros do Syntec Conseil, so para conferencia.

    Serve para responder uma pergunta de qualidade: a lista de etudes e mesmo
    um subconjunto do quadro geral? Divergencia aqui indica pagina de
    expertise desatualizada, e nao entra na base como registro.
    """
    nomes = {nome.upper() for nome, _ in _cartoes(_baixar(TODOS_MEMBROS))}
    if verbose:
        print(f"      {len(nomes)} membros no quadro geral (referencia)")
    return nomes


def coletar(*, delay: float = 1.6, verbose: bool = True) -> list[Empresa]:
    """
    Base do Syntec: membros da expertise Etudes.

    Nao ha ficha individual para visitar, entao a coleta e de duas
    requisicoes. A segunda, do quadro geral, existe so para marcar quais
    membros de etudes aparecem tambem na listagem principal.
    """
    membros = listar_membros_etudes(verbose=verbose)
    time.sleep(delay)
    try:
        quadro_geral = listar_todos_membros(verbose=verbose)
    except Exception as exc:
        quadro_geral = set()
        if verbose:
            print(f"      quadro geral indisponivel ({type(exc).__name__}), "
                  f"conferencia cruzada pulada")

    agora = datetime.now(timezone.utc).isoformat()
    empresas = []
    for nome, site in membros:
        e = Empresa(url_perfil=ETUDES, nome=nome, site=site, coletado_em=agora)
        if quadro_geral:
            e.tambem_em_nos_membros = "sim" if nome.upper() in quadro_geral else "nao"
        if not site:
            e.erro = "membro sem link de site na grade"
        empresas.append(e)
    return empresas


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "descricao",
           "expertise", "tambem_em_nos_membros", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "syntec_etudes") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig: sem BOM o Excel em maquina francesa le como latin-1 e corrompe
    # todo acento.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
