"""
Extrator da comunidade da PTBRiO, a sociedade polonesa de pesquisa de
mercado e opiniao (Polskie Towarzystwo Badania Rynku i Opinii, ptbrio.pl).

O QUE ESTA FONTE E, E O QUE ELA NAO E. A PTBRiO associa PESSOAS, nao
empresas: /spolecznosc/ lista 374 perfis individuais. A fonte de EMPRESAS
polonesas e a OFBOR (ver `scraper_lab.ofbor`), com 21 associadas. Os dois
modulos se complementam: a OFBOR da a empresa e o site, a PTBRiO da o nome
da pessoa, o cargo e a empresa em que ela trabalha.

FORNECEDOR OU COMPRADOR DE PESQUISA. A PTBRiO NAO distingue os dois. Entre
os 374 perfis convivem gente de agencia (Kantar, 4P, IQS) e gente do lado
do cliente (PKO Bank Polski, por exemplo). Nao ha campo, rotulo nem secao
que separe um do outro, e o texto livre da biografia nao e base confiavel
para decidir. Por isso este modulo NAO classifica: publica `empresa` como a
fonte publicou e deixa a separacao para quem tiver uma lista de agencias
para cruzar. Chutar a classificacao aqui contaminaria a base com um rotulo
que ninguem conseguiria auditar depois.

E-MAIL. Parte dos perfis publica e-mail pessoal, num bloco de icones de
contato junto com LinkedIn e site. A maioria nao publica nada. O endereco
sekretariat@ptbrio.pl, da propria sociedade, esta no rodape de TODA pagina
e nunca entra na base: por isso o e-mail e lido do icone de contato do
perfil, e nao por expressao regular sobre o HTML inteiro.

O PERFIL, E POR QUE NAO SE LE POR POSICAO. Cada perfil e um gabarito
Elementor com campos dinamicos identificados por classe
(`elementor-element-<id>`). Quando um campo esta vazio, o widget inteiro
some do HTML em vez de vir em branco: o perfil de Andrzej Anterszlak nao
tem empresa nem cargo, e passa direto do sobrenome para o numero de socio.
Ler os campos pela ordem em que aparecem gravaria "numer czlonkowski: 367"
na coluna `empresa` dele, e o mesmo deslocamento aconteceria em todo perfil
incompleto, sem erro visivel. Mapeamos por identificador de campo, que e do
gabarito e nao da pessoa, e campo ausente fica vazio.

Codificacao: WordPress serve utf-8. `_decodificar` mesmo assim percorre
cabecalho, meta, utf-8, cp1250 e iso-8859-2 com teste de mojibake, porque
as tabelas polonesas nunca falham no decode e "Spławski" lido errado vira
"SpÅawski" em silencio.
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
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://ptbrio.pl"
LISTAGEM = f"{BASE}/spolecznosc/"

PAIS = "Poland"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# robots.txt da PTBRiO proibe /wp-admin/ e libera admin-ajax.php. Nao ha
# Crawl-delay declarado, entao vale a pausa padrao do projeto.
PAUSA_PADRAO = 1.5

_EMAIL_INSTITUCIONAL = {"sekretariat@ptbrio.pl", "biuro@ptbrio.pl"}

_ESPACOS = re.compile(r"[\s ​]+")
_VAZIOS = {"", "-", "--", "n/a", "brak", "brak danych"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", _html.unescape(texto or "")).strip()
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)
_CANDIDATOS = ("utf-8", "cp1250", "iso-8859-2")
_APELIDOS = {"utf8": "utf-8", "windows-1250": "cp1250", "iso8859-2": "iso-8859-2",
             "latin2": "iso-8859-2", "iso_8859-2": "iso-8859-2"}
_UM_BYTE = {"cp1250", "iso-8859-2", "latin-1", "iso-8859-1"}
_MOJIBAKE = re.compile(r"[ÃÄÅÂ][-¿˘Ą˝]")

_codificacoes_vistas: dict[str, int] = {}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """Texto e codificacao usada; ver a docstring do modulo para o porque."""
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


_DOBRA = str.maketrans({"ą": "a", "Ą": "A", "ć": "c", "Ć": "C", "ę": "e",
                        "Ę": "E", "ł": "l", "Ł": "L", "ń": "n", "Ń": "N",
                        "ó": "o", "Ó": "O", "ś": "s", "Ś": "S", "ź": "z",
                        "Ź": "Z", "ż": "z", "Ż": "Z"})


def dobrar_para_ascii(nome: str) -> str:
    """Forma sem diacritico. "ł" nao decompoe em NFKD, entao vai no mapa."""
    t = (nome or "").translate(_DOBRA)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


# ------------------------------------------------------------------- download

def situacao_robots() -> str:
    return robots_situacao(LISTAGEM, agente=UA)


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


def _baixar(url: str, timeout: int = 40) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")

    def uma_vez() -> str:
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept-Language": "pl,en;q=0.7"})
        with urlopen(req, timeout=timeout) as r:
            bruto = r.read(8_000_000)
            charset = r.headers.get_content_charset()
        texto, usada = _decodificar(bruto, charset)
        _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
        return texto

    return _tentar(uma_vez)


# -------------------------------------------------------------------- registro

@dataclass
class Pessoa:
    nome: str = ""              # nome completo, como a PTBRiO exibe
    nome_latino: str = ""       # sem diacritico, para cruzar com bases globais
    primeiro_nome: str = ""
    sobrenome: str = ""
    empresa: str = ""           # como publicado; pode ser agencia OU cliente
    cargo: str = ""
    email: str = ""             # so quando o perfil publica; muitos nao
    site: str = ""
    linkedin: str = ""          # anotado do perfil; nunca acessado
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    numero_socio: str = ""
    setores: str = ""           # Branze
    areas: str = ""             # Obszary biznesowe
    metodos: str = ""           # Metody i techniki badawcze
    tipo_associacao: str = "Czlonek PTBRiO"
    url_perfil: str = ""
    coletado_em: str = ""
    erro: str = ""


# ------------------------------------------------------------------- listagem

def listar_perfis(*, verbose: bool = True) -> list[dict]:
    """
    Nome e URL de perfil de cada associado.

    A grade declara `load_more_type: scroll`, o que sugere rolagem infinita,
    mas o atributo `data-pages` vale 1 e os 374 itens ja vem no HTML: nao ha
    segunda pagina a buscar. Contamos URLS UNICAS, nao elementos da grade,
    porque o tema repete o mesmo item em variantes de layout e contar nos do
    DOM inflaria o total.

    A busca fica restrita ao bloco `#ludzie`. A pagina usa o mesmo
    componente de grade em outros trechos, e varrer o documento inteiro
    traria itens que nao sao associados.
    """
    sopa = BeautifulSoup(_baixar(LISTAGEM), "html.parser")
    bloco = sopa.select_one("#ludzie")
    if bloco is None:
        raise RuntimeError("grade #ludzie nao encontrada em /spolecznosc/")

    vistos: set[str] = set()
    perfis: list[dict] = []
    itens = bloco.select(".jet-listing-grid__item")
    for item in itens:
        a = item.select_one("a.jet-listing-dynamic-image__link[href]")
        url = (a.get("href") or "").strip() if a else ""
        if not url or url in vistos:
            continue
        vistos.add(url)
        campo = item.select_one(".jet-listing-dynamic-field__content")
        perfis.append({
            "url": url,
            "nome_listagem": _limpar(campo.get_text()) if campo else "",
        })
    if verbose:
        print(f"      {len(itens)} itens na grade, {len(perfis)} perfis unicos")
    return perfis


# -------------------------------------------------------------------- extracao

# Identificadores dos campos no gabarito Elementor do perfil. Sao do
# GABARITO, iguais em todos os perfis; o que muda de pessoa para pessoa e
# quais deles existem. Ver a docstring do modulo: campo vazio some do HTML,
# entao ler por ordem deslocaria todos os campos seguintes.
_CAMPOS = {
    "elementor-element-e516c04": "primeiro_nome",
    "elementor-element-402d90e": "sobrenome",
    "elementor-element-a931b9b": "empresa",
    "elementor-element-648f896": "cargo",
    "elementor-element-d0ddc50": "numero_socio",
    "elementor-element-8f76130": "descricao",
    "elementor-element-e60eb01": "setores",
    "elementor-element-18f3629": "areas",
    "elementor-element-a0a1220": "metodos",
}

_NUMERO_SOCIO = re.compile(r"(\d+)")

# Redes sociais da propria PTBRiO e hosts que nao sao site institucional.
_HOSTS_SOCIAIS = ("linkedin.com", "facebook.com", "twitter.com", "x.com",
                  "youtube.com", "instagram.com", "spotify.com", "tiktok.com")


def _anexar_contatos(sopa, reg: "Pessoa") -> None:
    """
    E-mail, site e LinkedIn do bloco de icones do perfil.

    Ler o e-mail por expressao regular sobre o HTML inteiro pegaria tambem o
    sekretariat@ptbrio.pl do rodape e qualquer endereco que apareca dentro
    de script de terceiro. Os icones pessoais do perfil sao os unicos
    marcados com a classe `elementor-icon`; o mailto do rodape nao tem
    classe nenhuma. Filtramos por essa classe e, por seguranca, descartamos
    qualquer endereco do dominio da propria sociedade.

    O LinkedIn e apenas ANOTADO, a partir do que a PTBRiO ja publica. Este
    projeto nao acessa o linkedin.com: o robots.txt deles proibe todo
    agente. A URL fica na base para cruzamento posterior, sem requisicao.
    Distinguimos /in/ (pessoa) de /company/ptbrio/ (a propria sociedade, que
    aparece no rodape de todas as paginas).
    """
    for a in sopa.select("a.elementor-icon[href]"):
        href = (a.get("href") or "").strip()
        alvo = href.lower()

        if alvo.startswith("mailto:"):
            achado = _EMAIL.search(href)
            if not achado:
                continue
            email = achado.group(0).lower()
            if email in _EMAIL_INSTITUCIONAL or email.endswith("@ptbrio.pl"):
                continue
            if not reg.email:
                reg.email = email
            continue

        if "linkedin.com/in/" in alvo:
            if not reg.linkedin:
                reg.linkedin = href.split("?")[0][:200]
            continue

        if alvo.startswith("http") and not any(h in alvo for h in _HOSTS_SOCIAIS):
            if not reg.site and "ptbrio.pl" not in alvo:
                reg.site = href.split("?")[0][:200]


def extrair_perfil(html: str, perfil: dict) -> Pessoa:
    reg = Pessoa(url_perfil=perfil["url"],
                 nome=perfil["nome_listagem"],
                 coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    achados: dict[str, str] = {}
    for div in sopa.select("div.elementor-widget-jet-listing-dynamic-field"):
        classes = div.get("class", [])
        campo = next((_CAMPOS[c] for c in classes if c in _CAMPOS), None)
        if not campo or campo in achados:
            continue
        achados[campo] = _limpar(div.get_text(" "))

    reg.primeiro_nome = achados.get("primeiro_nome", "")
    reg.sobrenome = achados.get("sobrenome", "")
    reg.empresa = achados.get("empresa", "")[:200]
    reg.cargo = achados.get("cargo", "")[:200]
    reg.descricao = achados.get("descricao", "")[:800]
    reg.setores = achados.get("setores", "")[:400]
    reg.areas = achados.get("areas", "")[:400]
    reg.metodos = achados.get("metodos", "")[:400]

    bruto_numero = achados.get("numero_socio", "")
    m = _NUMERO_SOCIO.search(bruto_numero)
    reg.numero_socio = m.group(1) if m else ""

    montado = _limpar(f"{reg.primeiro_nome} {reg.sobrenome}")
    if montado:
        reg.nome = montado
    reg.nome_latino = dobrar_para_ascii(reg.nome)

    _anexar_contatos(sopa, reg)

    if not achados:
        reg.erro = "perfil sem campos reconheciveis"
    elif not reg.empresa:
        # Nao e falha de coleta: a pessoa nao declarou onde trabalha.
        reg.erro = "perfil sem empresa declarada"
    return reg


def coletar(perfis: list[dict], *, delay: float = PAUSA_PADRAO,
            verbose: bool = True) -> list[Pessoa]:
    saida: list[Pessoa] = []
    for i, p in enumerate(perfis, 1):
        try:
            reg = extrair_perfil(_baixar(p["url"]), p)
        except Exception as exc:
            reg = Pessoa(url_perfil=p["url"], nome=p["nome_listagem"],
                         nome_latino=dobrar_para_ascii(p["nome_listagem"]),
                         coletado_em=datetime.now(timezone.utc).isoformat(),
                         erro=f"{type(exc).__name__}: {exc}"[:150])
        saida.append(reg)
        if verbose and (i % 25 == 0 or i == len(perfis)):
            com_empresa = sum(1 for r in saida if r.empresa)
            print(f"  [{i:>3}/{len(perfis)}] {com_empresa} com empresa; "
                  f"ultimo: {reg.nome[:26]} / {reg.empresa[:26]}")
        if i < len(perfis):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "nome_latino", "primeiro_nome", "sobrenome", "empresa",
           "cargo", "email", "site", "linkedin", "pais", "telefone",
           "endereco", "descricao", "numero_socio", "setores", "areas",
           "metodos", "tipo_associacao", "url_perfil", "coletado_em", "erro"]


def exportar(pessoas: list[Pessoa], nome: str = "ptbrio") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(p) for p in pessoas],
                             ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig: sem BOM o Excel polones le o CSV como cp1250 e quebra
    # "Spławski", "Łukasz" e qualquer sobrenome com ł, ń ou ż.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for p in pessoas:
            d = asdict(p)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
