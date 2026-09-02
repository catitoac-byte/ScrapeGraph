"""
Extrator das associadas da OFBOR, a organizacao polonesa das empresas de
pesquisa de opiniao e mercado (Organizacja Firm Badania Opinii i Rynku,
ofbor.pl).

Por que OFBOR e nao PTBRiO para empresas: a PTBRiO e sociedade de PESSOAS
(374 perfis individuais em /spolecznosc/), enquanto a OFBOR associa
EMPRESAS. Para uma base de empresas de pesquisa, a OFBOR e a fonte certa.

O QUE A OFBOR PUBLICA, E O QUE NAO PUBLICA. O quadro de associadas fica na
propria home, na ancora #czlonkowie, e e uma grade de LOGOS. Cada logo
linka para o site da empresa. Nao ha e-mail, telefone nem endereco: as
paginas individuais (/firmy/<slug>/) existem, respondem 200 e vem sem
conteudo nenhum alem do cabecalho e do rodape do site. Conferimos uma a uma
antes de escrever este modulo. O unico e-mail em todo o dominio e
biuro@ofbor.pl, da propria organizacao, e ele NAO entra na base.
Entregamos entao nome e site, que e o que a fonte tem, em vez de inventar
contato.

O CASAMENTO, que e onde este site engana. A grade de logos so tem imagem e
link; o nome da empresa nao aparece em lugar nenhum dela. Ha tres jeitos
tentadores e errados de descobrir o nome:

  ordem posicional     a home mistura, no mesmo padrao de grade, as
                       associadas e os membros do conselho
  alt da imagem        vale "yougiv" para a YouGov, "mnr" para a Minds &
                       Roses, "niq" para a NielsenIQ
  nome do arquivo      "gfk_ofbor.jpg", "iqs2022.jpg", "nielsen2.jpg"

Nenhum dos tres identifica a empresa. O que identifica e o `data-post-id`
de cada item da grade, que e a chave primaria do WordPress. O mesmo id
aparece na API REST do custom post type `firmy`, que devolve o nome
publicado. Casamos por esse id, e so por ele. Item da grade sem par na API
nao e associada: sao os membros do conselho, que moram noutro post type.

Codificacao: WordPress serve utf-8 no cabecalho e a API REST e utf-8 por
definicao. Ainda assim `_decodificar` percorre cabecalho, meta e depois
utf-8, cp1250 e iso-8859-2, com teste de mojibake: as duas tabelas
polonesas aceitam qualquer byte sem erro, e "Łukasz" lido como cp1250
sobre bytes utf-8 vira "Åukasz" sem levantar excecao nenhuma.
"""

from __future__ import annotations

import csv
import html as _html
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://ofbor.pl"
HOME = f"{BASE}/"
API_FIRMAS = f"{BASE}/wp-json/wp/v2/firmy"

PAIS = "Poland"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# robots.txt da OFBOR proibe apenas /stats/ e nao declara Crawl-delay.
PAUSA_PADRAO = 1.5

_DOMINIO_ASSOCIACAO = "ofbor.pl"
_EMAIL_INSTITUCIONAL = {"biuro@ofbor.pl"}

_ESPACOS = re.compile(r"[\s ​]+")
_VAZIOS = {"", "-", "--", "n/a", "brak"}


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", _html.unescape(texto or "")).strip()
    # NFC: em polones "ł" e "ó" existem composto e decomposto. Sem
    # normalizar, a mesma empresa pode virar duas na deduplicacao.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)
_CANDIDATOS = ("utf-8", "cp1250", "iso-8859-2")
_APELIDOS = {"utf8": "utf-8", "windows-1250": "cp1250", "iso8859-2": "iso-8859-2",
             "latin2": "iso-8859-2", "iso_8859-2": "iso-8859-2"}
_UM_BYTE = {"cp1250", "iso-8859-2", "latin-1", "iso-8859-1"}

# utf-8 lido como tabela de um byte deixa rastro em polones: "Å" e "Ä"
# seguidos de um byte de continuacao ("Łukasz" -> "Åukasz").
_MOJIBAKE = re.compile(r"[ÃÄÅÂ][-¿˘Ą˝]")

_codificacoes_vistas: dict[str, int] = {}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """
    Texto e nome da codificacao efetivamente usada.

    Ordem: cabecalho HTTP, meta charset, depois os candidatos do idioma.
    Quando o vencedor e uma tabela de um byte, conferimos contra a
    assinatura de mojibake antes de aceitar: cp1250 e iso-8859-2 mapeiam os
    256 bytes e nunca falham, entao um nome polones corrompido passaria
    direto se confiassemos so na ausencia de excecao.
    """
    ordem: list[str] = []

    def somar(nome: str | None) -> None:
        if not nome:
            return
        n = _APELIDOS.get(nome.strip().lower(), nome.strip().lower())
        if n not in ordem:
            ordem.append(n)

    somar(charset_http)
    m = _META_CHARSET.search(bruto[:4096])
    if m:
        somar(m.group(1).decode("ascii", "ignore"))
    for c in _CANDIDATOS:
        somar(c)

    for nome in ordem:
        try:
            texto = bruto.decode(nome)
        except (UnicodeDecodeError, LookupError):
            continue
        if nome in _UM_BYTE and _MOJIBAKE.search(texto):
            try:
                return bruto.decode("utf-8"), f"utf-8 (corrigido de {nome})"
            except UnicodeDecodeError:
                pass
        return texto, nome
    return bruto.decode("utf-8", errors="replace"), "utf-8/replace"


def codificacoes_detectadas() -> dict[str, int]:
    return dict(_codificacoes_vistas)


_LETRAS_POLONESAS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


def tem_letras_polonesas(texto: str) -> bool:
    return any(c in _LETRAS_POLONESAS for c in texto or "")


# ------------------------------------------------------------------- download

def situacao_robots() -> str:
    return robots_situacao(HOME, agente=UA)


def _tentar(func, *, tentativas: int = 3, base_espera: float = 2.0):
    """Repete com espera crescente; timeout nao e ausencia de dado."""
    ultimo: Exception | None = None
    for i in range(tentativas):
        try:
            return func()
        except Exception as exc:
            ultimo = exc
            if i < tentativas - 1:
                time.sleep(base_espera * (i + 1))
    raise ultimo  # type: ignore[misc]


def _baixar(url: str, timeout: int = 40) -> tuple[str, dict]:
    """Devolve (texto, cabecalhos). Os cabecalhos trazem a contagem do CMS."""
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")

    def uma_vez() -> tuple[str, dict]:
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept-Language": "pl,en;q=0.7"})
        with urlopen(req, timeout=timeout) as r:
            bruto = r.read(8_000_000)
            charset = r.headers.get_content_charset()
            cabecalhos = {k.lower(): v for k, v in r.headers.items()}
        texto, usada = _decodificar(bruto, charset)
        _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
        return texto, cabecalhos

    return _tentar(uma_vez)


# -------------------------------------------------------------------- registro

@dataclass
class Empresa:
    id_post: int
    nome: str = ""
    nome_latino: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    tipo_associacao: str = "Czlonek OFBOR"
    slug: str = ""
    logo: str = ""
    url_perfil: str = ""
    coletado_em: str = ""
    erro: str = ""


# ------------------------------------------------------------------ listagens

def listar_api(*, por_pagina: int = 100, delay: float = PAUSA_PADRAO,
               verbose: bool = True) -> tuple[dict[int, dict], int | None]:
    """
    Empresas do post type `firmy` pela API REST do WordPress.

    Devolve ({id: registro}, total declarado pelo CMS).

    A parada exige DUAS paginas vazias seguidas, e nao uma. Uma pagina vazia
    isolada pode ser um erro momentaneo do CMS, e parar nela truncaria a
    lista sem deixar sinal. O cabecalho X-WP-Total serve de conferencia
    independente contra o que efetivamente coletamos.
    """
    registros: dict[int, dict] = {}
    total_declarado: int | None = None
    pagina = 1
    vazias_seguidas = 0

    while vazias_seguidas < 2 and pagina <= 50:
        url = f"{API_FIRMAS}?per_page={por_pagina}&page={pagina}"
        try:
            texto, cabecalhos = _baixar(url)
            dados = json.loads(texto)
        except Exception as exc:
            # Pagina alem do fim devolve 400 no WordPress; tratamos como
            # vazia, mas ainda exigimos a segunda confirmacao.
            if verbose:
                print(f"      pagina {pagina}: {type(exc).__name__}")
            dados = []
            cabecalhos = {}

        if total_declarado is None and cabecalhos.get("x-wp-total"):
            try:
                total_declarado = int(cabecalhos["x-wp-total"])
            except ValueError:
                pass

        if not isinstance(dados, list) or not dados:
            vazias_seguidas += 1
        else:
            vazias_seguidas = 0
            for item in dados:
                ident = item.get("id")
                if not isinstance(ident, int):
                    continue
                registros[ident] = {
                    "id": ident,
                    "nome": _limpar((item.get("title") or {}).get("rendered", "")),
                    "slug": _limpar(item.get("slug", "")),
                    "url_perfil": item.get("link", ""),
                }
        if verbose:
            print(f"      pagina {pagina}: {len(dados) if isinstance(dados, list) else 0} "
                  f"itens (acumulado {len(registros)})")
        pagina += 1
        time.sleep(delay)

    return registros, total_declarado


def listar_grade(*, verbose: bool = True) -> dict[int, dict]:
    """
    Site e logo de cada associada, lidos da grade da home.

    Restringimos a busca ao bloco `div#firmy` dentro da secao
    `#czlonkowie`. A home repete o mesmo componente de grade para os membros
    do conselho logo abaixo; varrer a pagina inteira misturaria pessoas com
    empresas, e a diferenca nao aparece no HTML do item.
    """
    texto, _ = _baixar(HOME)
    sopa = BeautifulSoup(texto, "html.parser")

    bloco = sopa.select_one("#czlonkowie #firmy") or sopa.select_one("#firmy")
    if bloco is None:
        raise RuntimeError("bloco #firmy nao encontrado na home da OFBOR")

    grade: dict[int, dict] = {}
    for item in bloco.select(".jet-listing-grid__item"):
        bruto = item.get("data-post-id")
        if not bruto or not bruto.isdigit():
            continue
        ident = int(bruto)
        a = item.select_one("a.jet-listing-dynamic-image__link[href]")
        img = item.select_one("img")
        href = (a.get("href") or "").strip() if a else ""
        # Link de volta para a propria OFBOR nao e site da empresa.
        if _DOMINIO_ASSOCIACAO in href.lower():
            href = ""
        grade[ident] = {
            "site": href.split("?")[0][:200],
            "logo": (img.get("src") or "") if img else "",
        }
    if verbose:
        print(f"      {len(grade)} itens na grade #firmy")
    return grade


def montar(api: dict[int, dict], grade: dict[int, dict], *,
           verbose: bool = True) -> tuple[list[Empresa], dict]:
    """
    Junta nome (API) e site (grade) pelo id do post.

    Id ausente de um dos lados nao vira registro adivinhado: a empresa entra
    com o campo faltante vazio e o motivo anotado em `erro`.
    """
    agora = datetime.now(timezone.utc).isoformat()
    empresas: list[Empresa] = []
    for ident, reg in sorted(api.items(), key=lambda kv: kv[1]["nome"].lower()):
        par = grade.get(ident)
        e = Empresa(
            id_post=ident,
            nome=reg["nome"],
            # O nome da OFBOR ja e latino; a forma sem diacritico ajuda a
            # cruzar com Esomar e Greenbook, que costumam gravar assim.
            nome_latino=_dobrar(reg["nome"]),
            slug=reg["slug"],
            url_perfil=reg["url_perfil"],
            coletado_em=agora,
        )
        if par:
            e.site = par["site"]
            e.logo = par["logo"]
        else:
            e.erro = "sem item correspondente na grade da home; site indisponivel"
        if not e.site and not e.erro:
            e.erro = "grade sem link externo para esta empresa"
        empresas.append(e)

    sem_par = sorted(set(grade) - set(api))
    resumo = {
        "na_api": len(api),
        "na_grade": len(grade),
        "casados_por_id": len(set(api) & set(grade)),
        "grade_sem_par_na_api": len(sem_par),
    }
    if verbose and sem_par:
        # Esperado: sao os itens de outro post type que dividem a grade.
        print(f"      {len(sem_par)} item(ns) da grade fora do post type "
              f"`firmy`, ignorados: {sem_par}")
    return empresas, resumo


_DOBRA = str.maketrans({"ą": "a", "Ą": "A", "ć": "c", "Ć": "C", "ę": "e",
                        "Ę": "E", "ł": "l", "Ł": "L", "ń": "n", "Ń": "N",
                        "ó": "o", "Ó": "O", "ś": "s", "Ś": "S", "ź": "z",
                        "Ź": "Z", "ż": "z", "Ż": "Z"})


def _dobrar(nome: str) -> str:
    """Forma sem diacritico. NFKD sozinho nao resolve "ł", que nao decompoe."""
    t = (nome or "").translate(_DOBRA)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def coletar(*, delay: float = PAUSA_PADRAO,
            verbose: bool = True) -> tuple[list[Empresa], dict]:
    if verbose:
        print("      lendo a API do post type `firmy`")
    api, total_declarado = listar_api(delay=delay, verbose=verbose)
    time.sleep(delay)

    if verbose:
        print("      lendo a grade de logos da home")
    grade = listar_grade(verbose=verbose)

    empresas, resumo = montar(api, grade, verbose=verbose)
    resumo["total_declarado_cms"] = total_declarado
    # Conferencia contra a propria fonte, como exige o procedimento.
    resumo["bate_com_o_declarado"] = (total_declarado is None
                                      or total_declarado == len(empresas))
    return empresas, resumo


COLUNAS = ["nome", "nome_latino", "email", "site", "pais", "telefone",
           "endereco", "descricao", "tipo_associacao", "slug", "logo",
           "id_post", "url_perfil", "coletado_em", "erro"]


def exportar(empresas: list[Empresa], nome: str = "ofbor") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas],
                             ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig: sem BOM o Excel polones le o CSV como cp1250 e quebra
    # "Łukasz", "Gdańsk" e qualquer nome com ł, ń ou ż.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
