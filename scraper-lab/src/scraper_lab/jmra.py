"""
Extrator dos associados da JMRA, a associacao japonesa de pesquisa de mercado
(jmra-net.or.jp).

Duas categorias convivem no site e nao valem o mesmo para a base:

  正会員 (seikaiin)      empresas que vivem de pesquisa de mercado. E o alvo.
  賛助法人会員 (sanjo)    pessoas juridicas que apoiam a associacao. A lista
                        inclui Asahi, Kao, Shiseido, Nissan: sao clientes do
                        setor, nao institutos. Coletamos com rotulo proprio
                        em `tipo_associacao` para o squad de uniao decidir,
                        em vez de misturar as duas coisas na mesma linha.

A JMRA publica a contagem oficial em /membership/member_trend/, e conferimos
o total coletado contra ela: divergencia significa lista truncada.

Sobre a fonte da listagem: /membership/sponsorship.html tambem lista fichas,
mas devolve 104 empresas porque arrasta dois ex-正会員 que migraram para
賛助 (Intage Technosphere e T-Gaia). A pagina em ordem silabica
(regular_member.html) devolve os 102 que a propria associacao declara, entao
e ela que manda.

Codificacao: a JMRA responde utf-8 no cabecalho e na meta, mas o site e
antigo (ASP.NET) e algumas paginas soltas ainda saem em Shift_JIS sem
declarar. Por isso `_decodificar` nunca confia num unico sinal e valida a
decodificacao em modo estrito antes de aceitar.

Nome em alfabeto latino: a JMRA nao publica razao social romanizada. A pagina
institucional em ingles (/Portals/0/aboutus/en/index.html) fala da associacao
e nao traz lista de membros. `nome_latino` sai vazio de proposito, em vez de
uma transliteracao inventada por nos.
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

from scraper_lab import robots as robots_mod
from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.jmra-net.or.jp"
LISTA_REGULAR = f"{BASE}/membership/regular_member.html"
LISTA_SANJO = f"{BASE}/membership/support_corp_member.html"
CONTAGEM_OFICIAL = f"{BASE}/membership/member_trend/tabid622.html"
PERFIL = f"{BASE}/membership/sponsorship_detail.html?pdid1={{}}"

PAIS = "Japan"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Contatos da propria JMRA, presentes no rodape de toda pagina.
_EMAIL_INSTITUCIONAL = {"office@jmra-net.or.jp", "info@jmra-net.or.jp"}
_TELEFONE_INSTITUCIONAL = {"03-3256-3101", "0332563101"}

_ESPACOS = re.compile(r"[\s　]+")
_VAZIOS = {"", "-", "--", "なし", "n/a"}


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", texto or "").strip()
    return "" if t.lower() in _VAZIOS else t


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)

# Ordem importa: utf-8 primeiro porque um texto Shift_JIS raramente passa como
# utf-8 valido, enquanto o inverso acontece o tempo todo e grava mojibake.
_CANDIDATOS = ("utf-8", "cp932", "euc-jp", "iso-2022-jp")

_APELIDOS = {
    "shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932",
    "windows-31j": "cp932", "ms932": "cp932", "euc_jp": "euc-jp",
    "utf8": "utf-8", "utf-8": "utf-8",
}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """
    Texto e nome da codificacao efetivamente usada.

    Decodificar japones errado nao levanta excecao: gera nome ilegivel que
    passa despercebido ate alguem abrir o CSV. Por isso tentamos em modo
    estrito e so aceitamos a codificacao que decodifica o documento inteiro
    sem erro; `errors="replace"` fica como ultimo recurso, e o nome retornado
    avisa que houve perda.
    """
    ordem: list[str] = []

    def somar(nome: str | None) -> None:
        if not nome:
            return
        n = _APELIDOS.get(nome.strip().lower(), nome.strip().lower())
        if n not in ordem:
            ordem.append(n)

    somar(charset_http)
    # a meta charset costuma estar nos primeiros 4 KB; ler o resto so atrasa
    m = _META_CHARSET.search(bruto[:4096])
    if m:
        somar(m.group(1).decode("ascii", "ignore"))
    for c in _CANDIDATOS:
        somar(c)

    for nome in ordem:
        try:
            return bruto.decode(nome), nome
        except (UnicodeDecodeError, LookupError):
            continue
    return bruto.decode("utf-8", errors="replace"), "utf-8/replace"


# ------------------------------------------------------------------- download

_codificacoes_vistas: dict[str, int] = {}


def _preparar_robots() -> str:
    """
    Garante que o verificador decida pelo robots.txt real deste dominio.

    `robots.para()` engole qualquer falha de rede e devolve None, que o
    `permitido()` interpreta como "libera tudo". Numa coleta isso e pior que
    um erro: passariamos por cima de uma proibicao sem saber. Aqui buscamos o
    arquivo, registramos o que aconteceu e so entao deixamos o cache do modulo
    responder as consultas seguintes.
    """
    alvo = f"{BASE}/robots.txt"
    try:
        with urlopen(Request(alvo, headers={"User-Agent": UA}), timeout=15) as r:
            texto = r.read(500_000).decode("utf-8", errors="replace")
        robots_mod._cache[BASE] = robots_mod.Robots(texto, UA)
        return f"robots.txt lido ({len(texto)} bytes)"
    except Exception as exc:
        # 404/302 e o caso da JMRA: sem arquivo, o padrao da web e permitir.
        robots_mod._cache[BASE] = None
        return f"sem robots.txt utilizavel ({type(exc).__name__}); padrao permitir"


def _baixar(url: str, timeout: int = 30) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    req = Request(url, headers={"User-Agent": UA,
                                "Accept-Language": "ja,en;q=0.8"})
    with urlopen(req, timeout=timeout) as resp:
        bruto = resp.read(4_000_000)
        charset = resp.headers.get_content_charset()
    texto, usada = _decodificar(bruto, charset)
    _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
    return texto


def codificacoes_detectadas() -> dict[str, int]:
    """Quantas paginas cairam em cada codificacao, para o relatorio."""
    return dict(_codificacoes_vistas)


# -------------------------------------------------------------------- registro

@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    nome_latino: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    tipo_associacao: str = ""
    codigo_membro: str = ""
    representante: str = ""
    fundacao: str = ""
    funcionarios: str = ""
    filiais: str = ""
    recursos: str = ""
    site_carreiras: str = ""
    contato_url: str = ""
    privacy_mark: str = ""
    coletado_em: str = ""
    erro: str = ""


# Rotulo da ficha -> campo do registro. A JMRA usa sempre os mesmos termos.
_CAMPOS = {
    "代表者名": "representante",
    "本社所在地": "endereco",
    "電話番号": "telefone",
    "ホームページ": "site",
    "採用ホームページ": "site_carreiras",
    "eメール": "email",
    "設立年月日": "fundacao",
    "従業員総数": "funcionarios",
    "pマーク登録番号": "privacy_mark",
    "拠点": "filiais",
}

# Texto livre da ficha. O rotulo vem num <h3> e o conteudo sao os irmaos
# seguintes ate o proximo <h3>; os blocos ficam espalhados entre
# div.ProductSummary e div.ProductDescription, entao andamos pelos titulos em
# vez de fixar um container.
_BLOCOS = {
    "わが社の特徴": "descricao",   # o que a empresa faz
    "提供リソース": "recursos",    # paineis, metodologias e bases proprias
}


# ------------------------------------------------------------------- listagem

_ID_PERFIL = re.compile(r"pdid1=(\d+)")


def _listar(url: str, tipo: str) -> list[tuple[int, str, str]]:
    """(id, nome, tipo) das empresas de uma pagina de listagem."""
    sopa = BeautifulSoup(_baixar(url), "html.parser")
    # o menu lateral repete links de ficha; restringir ao #main evita
    # arrastar empresas de outra categoria para dentro desta lista
    principal = sopa.select_one("#main")
    if principal is None:
        raise RuntimeError(f"bloco #main ausente em {url}")

    vistos: dict[int, str] = {}
    for a in principal.select("a[href]"):
        m = _ID_PERFIL.search(a.get("href") or "")
        if not m:
            continue
        ident = int(m.group(1))
        nome = _limpar(a.get_text(" "))
        # o mesmo id aparece no logo (sem texto) e no nome; fica o que tem texto
        if nome or ident not in vistos:
            vistos.setdefault(ident, "")
            if nome:
                vistos[ident] = nome
    return [(i, n, tipo) for i, n in sorted(vistos.items())]


def listar_empresas(*, incluir_sanjo: bool = True,
                    verbose: bool = True) -> list[tuple[int, str, str]]:
    regulares = _listar(LISTA_REGULAR, "正会員")
    if verbose:
        print(f"      正会員 (institutos de pesquisa): {len(regulares)}")
    if not incluir_sanjo:
        return regulares

    time.sleep(1.6)
    sanjo = _listar(LISTA_SANJO, "賛助法人会員")
    if verbose:
        print(f"      賛助法人会員 (apoiadoras): {len(sanjo)}")
    # ids nao se sobrepoem (20xxx x 30xxx), mas conferimos em vez de supor
    ids_reg = {i for i, _, _ in regulares}
    sanjo = [t for t in sanjo if t[0] not in ids_reg]
    return regulares + sanjo


def contagem_declarada() -> dict[str, int]:
    """
    Numeros que a propria JMRA publica em 会員動向.

    Serve de contraprova: se a listagem devolver menos que isto, algo foi
    truncado e o resultado nao pode ser publicado como completo.
    """
    texto = BeautifulSoup(_baixar(CONTAGEM_OFICIAL), "html.parser").get_text(" ")
    texto = _ESPACOS.sub(" ", texto)
    out: dict[str, int] = {}
    for chave, padrao in (("正会員", r"法人正会員社\s*([\d,]+)\s*社"),
                          ("賛助法人会員", r"法人賛助会員社\s*([\d,]+)\s*社"),
                          ("賛助個人会員", r"個人賛助会員者\s*([\d,]+)\s*名")):
        m = re.search(padrao, texto)
        if m:
            out[chave] = int(m.group(1).replace(",", ""))
    return out


# -------------------------------------------------------------------- extracao

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _normalizar_telefone(valor: str) -> str:
    t = _limpar(valor)
    return "" if t.replace("-", "").replace(" ", "") in _TELEFONE_INSTITUCIONAL else t


def extrair_empresa(html: str, url: str, nome_listagem: str, tipo: str) -> Empresa:
    reg = Empresa(url_perfil=url, nome=nome_listagem, tipo_associacao=tipo,
                  coletado_em=datetime.now(timezone.utc).isoformat())
    m = _ID_PERFIL.search(url)
    reg.codigo_membro = m.group(1) if m else ""

    sopa = BeautifulSoup(html, "html.parser")
    principal = sopa.select_one("#main")
    if principal is None:
        reg.erro = "bloco #main ausente"
        return reg

    # A ficha e uma tabela rotulo/valor. Ha uma segunda tabela (resumo de
    # servicos) sem rotulos que nos interessem, entao filtramos por rotulo
    # conhecido em vez de assumir posicao.
    for tr in principal.select("table tr"):
        celulas = tr.find_all(["th", "td"], recursive=False)
        if len(celulas) < 2:
            continue
        rotulo = _limpar(celulas[0].get_text(" ")).rstrip(":：").lower()
        campo = _CAMPOS.get(rotulo)
        if not campo or getattr(reg, campo):
            continue

        valor_el = celulas[1]
        if campo == "email":
            # a JMRA aceita URL de formulario no lugar do e-mail; guardar essa
            # URL na coluna de e-mail contaminaria a base de contato
            bruto = _limpar(valor_el.get_text(" "))
            achado = _EMAIL.search(bruto)
            if achado and achado.group(0).lower() not in _EMAIL_INSTITUCIONAL:
                reg.email = achado.group(0)
            elif bruto.startswith("http"):
                reg.contato_url = bruto
            continue

        if campo in ("site", "site_carreiras"):
            link = valor_el.find("a", href=True)
            alvo = link["href"] if link else _limpar(valor_el.get_text(" "))
            if alvo.startswith("http") and "jmra-net.or.jp" not in alvo:
                setattr(reg, campo, alvo.split("?")[0])
            continue

        if campo == "telefone":
            reg.telefone = _normalizar_telefone(valor_el.get_text(" "))
            continue

        setattr(reg, campo, _limpar(valor_el.get_text(" "))[:600])

    for titulo in principal.find_all("h3"):
        campo = _BLOCOS.get(_limpar(titulo.get_text()))
        if not campo or getattr(reg, campo):
            continue
        partes = []
        for irmao in titulo.find_next_siblings():
            if irmao.name == "h3":
                break
            partes.append(irmao.get_text(" "))
        setattr(reg, campo, _limpar(" ".join(partes))[:800])

    if not reg.nome:
        # sem nome na listagem, o titulo traz "... ｜<empresa>"
        titulo = _limpar(sopa.title.get_text() if sopa.title else "")
        reg.nome = titulo.rsplit("｜", 1)[-1].strip() if "｜" in titulo else ""
    if not reg.nome:
        reg.erro = "sem nome"
    return reg


def coletar(alvos: list[tuple[int, str, str]], *, delay: float = 1.6,
            verbose: bool = True) -> list[Empresa]:
    """
    Coleta as fichas. `delay` respeita o minimo de 1,5s por dominio.

    Erro de rede vira `erro` no registro e nao interrompe a coleta: um timeout
    e falha transitoria, nao prova de que a empresa nao publica dado.
    """
    saida: list[Empresa] = []
    for i, (ident, nome, tipo) in enumerate(alvos, 1):
        url = PERFIL.format(ident)
        try:
            reg = extrair_empresa(_baixar(url), url, nome, tipo)
        except Exception as exc:
            reg = Empresa(url_perfil=url, nome=nome, tipo_associacao=tipo,
                          erro=f"{type(exc).__name__}: {exc}"[:150],
                          coletado_em=datetime.now(timezone.utc).isoformat())
        saida.append(reg)
        if verbose:
            print(f"  [{i:>3}/{len(alvos)}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:26]:26} | {reg.email[:28]:28} | {reg.site[:30]}")
        if i < len(alvos):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "nome_latino", "email", "site", "pais", "telefone", "endereco",
           "descricao", "tipo_associacao", "codigo_membro", "representante",
           "fundacao", "funcionarios", "filiais", "recursos", "site_carreiras",
           "contato_url", "privacy_mark", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "jmra") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig: sem BOM o Excel japones abre o CSV como Shift_JIS e embaralha
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
