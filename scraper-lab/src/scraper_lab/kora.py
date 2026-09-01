"""
Extrator das associadas da KORA, a associacao coreana de pesquisa de mercado
(ikora.or.kr).

Por que nao KOSOMAR: o dominio kosomar.or.kr nao existe mais (NXDOMAIN, nao
timeout nem 5xx). A entidade viva e a 한국조사협회 / Korea Research
Association, fundada em 1992 sob a Statistics Korea, que publica o diretorio
de associadas em ikora.or.kr. KOSOMAR e a sigla antiga.

O site e um Imweb: a listagem mostra so o logo e o nome, e a ficha abre num
modal carregado por POST em /ajax/get_modal_menu.cm, que devolve JSON com o
HTML pronto. Isso dispensa navegador; HTTP puro basta.

Duas categorias, mantidas em `tipo_associacao`:

  정회원사 (jeonghoewonsa)  associadas plenas
  준회원사 (junhoewonsa)     associadas juniores

Nome em alfabeto latino: a KORA mantem o mesmo diretorio em en.ikora.or.kr,
com os nomes romanizados. As duas listas nao podem ser casadas por posicao:
a ordem alfabetica coreana e a inglesa divergem (na 9a e na 10a posicao,
"Research & Research" e "Research LIM" aparecem trocadas), e casar por indice
gravaria o nome latino de uma empresa na linha de outra sem erro visivel.
Casamos pelo e-mail publicado na ficha, e caimos para o dominio do site
quando o e-mail falta. Sem par confiavel, `nome_latino` fica vazio.

Codificacao: ikora.or.kr responde utf-8 no cabecalho e na meta. Ainda assim
`_decodificar` valida em modo estrito e tenta EUC-KR/CP949 antes de recorrer
a substituicao, porque hangul decodificado errado vira nome ilegivel sem
levantar excecao.
"""

from __future__ import annotations

import csv
import json
import re
import ssl
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import truststore
from bs4 import BeautifulSoup

from scraper_lab import robots as robots_mod
from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE_KO = "https://ikora.or.kr"
BASE_EN = "https://en.ikora.or.kr"
LISTA_KO = f"{BASE_KO}/About"
LISTA_EN = f"{BASE_EN}/About"
MODAL = "/ajax/get_modal_menu.cm"

PAIS = "South Korea"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# O certificado da KORA nao valida contra o bundle embutido do Python, so
# contra o trust store do sistema. Sem isto toda requisicao morre em
# CERTIFICATE_VERIFY_FAILED e a coleta parece "site fora do ar".
_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

# Contatos da propria associacao, no rodape de toda pagina.
_EMAIL_INSTITUCIONAL = {"kora@ikora.or.kr"}
_TELEFONE_INSTITUCIONAL = {"0225462360", "02546236", "0221799434"}

_ESPACOS = re.compile(r"[\s ]+")
_VAZIOS = {"", "-", "--", "n/a", "없음"}


def _limpar(t: str | None) -> str:
    v = _ESPACOS.sub(" ", t or "").strip()
    return "" if v.lower() in _VAZIOS else v


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)
_CANDIDATOS = ("utf-8", "cp949", "euc-kr")
_APELIDOS = {"utf8": "utf-8", "ms949": "cp949", "euc_kr": "euc-kr",
             "euckr": "euc-kr", "ks_c_5601-1987": "cp949"}

_codificacoes_vistas: dict[str, int] = {}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """
    Texto e codificacao efetivamente usada.

    CP949 vem antes de EUC-KR porque e superconjunto dela: o inverso rejeita
    hangul valido e nos empurraria para o modo de substituicao sem motivo.
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
            return bruto.decode(nome), nome
        except (UnicodeDecodeError, LookupError):
            continue
    return bruto.decode("utf-8", errors="replace"), "utf-8/replace"


def codificacoes_detectadas() -> dict[str, int]:
    return dict(_codificacoes_vistas)


# ------------------------------------------------------------------- download

def _preparar_robots() -> dict[str, str]:
    """
    Carrega o robots.txt dos dois dominios com o contexto TLS certo.

    `robots.para()` busca o arquivo sem esse contexto: aqui o TLS falha, a
    excecao e engolida e `permitido()` passa a devolver True para tudo. Uma
    permissao que na verdade e um erro de rede e o pior resultado possivel,
    entao buscamos o arquivo nos mesmos e so depois deixamos o cache do modulo
    atender as consultas.
    """
    relato: dict[str, str] = {}
    for base in (BASE_KO, BASE_EN):
        try:
            req = Request(f"{base}/robots.txt", headers={"User-Agent": UA})
            with urlopen(req, timeout=15, context=_CTX) as r:
                texto = r.read(500_000).decode("utf-8", errors="replace")
            regras = robots_mod.Robots(texto, UA)
            robots_mod._cache[base] = regras
            relato[base] = (f"{len(regras.proibir)} Disallow, "
                            f"{len(regras.permitir)} Allow")
        except Exception as exc:
            robots_mod._cache[base] = None
            relato[base] = f"ilegivel ({type(exc).__name__}); padrao permitir"
    return relato


def _baixar(url: str, timeout: int = 30) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    with urlopen(req, timeout=timeout, context=_CTX) as resp:
        bruto = resp.read(4_000_000)
        charset = resp.headers.get_content_charset()
    texto, usada = _decodificar(bruto, charset)
    _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
    return texto


def _abrir_modal(base: str, menu_code: str, base_menu_code: str,
                 timeout: int = 30) -> str:
    """HTML da ficha que o site carrega por AJAX ao clicar no logo."""
    url = base + MODAL
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    dados = urllib.parse.urlencode({"menu_code": menu_code,
                                    "base_menu_code": base_menu_code}).encode()
    req = Request(url, data=dados, headers={
        "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": f"{base}/About", "Accept-Language": "ko,en;q=0.8"})
    with urlopen(req, timeout=timeout, context=_CTX) as resp:
        bruto = resp.read(2_000_000)
        charset = resp.headers.get_content_charset()
    texto, usada = _decodificar(bruto, charset)
    _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
    resposta = json.loads(texto)
    if resposta.get("msg") != "SUCCESS":
        raise RuntimeError(f"modal recusado: {resposta.get('msg')}")
    return resposta.get("html", "")


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
    endereco_latino: str = ""
    descricao: str = ""
    tipo_associacao: str = ""
    representante: str = ""
    fundacao: str = ""
    funcionarios: str = ""
    composicao_receita: str = ""
    coletado_em: str = ""
    erro: str = ""


# Rotulos da ficha coreana e da inglesa apontam para o mesmo campo.
_CAMPOS = {
    "대표이사": "representante", "ceo/president": "representante",
    "설립연도": "fundacao", "year of establishment": "fundacao",
    "회사 이메일": "email", "company e-mail": "email",
    "대표전화": "telefone", "representative(contact)": "telefone",
    "홈페이지": "site", "homepage address": "site",
    "주소": "endereco", "address": "endereco",
    "종업원수": "funcionarios", "number of employees": "funcionarios",
    "매출비중": "composicao_receita", "percentage of sales": "composicao_receita",
    "회사소개 및 연혁": "descricao", "company introduction and history": "descricao",
}

# Rotulos que encerram a ficha; o que vem depois e galeria de fotos.
_FIM_DA_FICHA = {"주요 사진", "main photos", "사진"}


# ------------------------------------------------------------------- listagem

_MODAL_ARGS = re.compile(r"openModalMenu\('([^']+)',\s*'([^']+)'")

# A pagina tem uma galeria por categoria, na ordem em que o site as exibe.
_CATEGORIAS_KO = ["정회원사", "준회원사"]


def listar_membros(url: str = LISTA_KO, *,
                   categorias: list[str] | None = None,
                   verbose: bool = True) -> list[dict]:
    """
    Um dicionario por associada: nome, categoria e como chegar aos dados.

    A pagina traz um botao "더보기" (ver mais), mas ele so expande o que ja
    esta no HTML: nao ha AJAX de paginacao aqui, e a contagem de itens do
    documento e a lista inteira.

    Nem toda associada tem ficha. O logo leva a tres destinos diferentes, e
    ignorar os dois ultimos jogaria fora 20 das 55 empresas sem erro visivel:

      openModalMenu(...)   ficha completa carregada por AJAX
      http://...           link direto para o site da empresa, sem ficha
      sem link             so o nome e o logo
    """
    sopa = BeautifulSoup(_baixar(url), "html.parser")
    galerias = sopa.select("div.gallery2")
    if not galerias:
        raise RuntimeError(f"nenhuma galeria de associadas em {url}")

    rotulos = categorias if categorias is not None else _CATEGORIAS_KO
    membros: list[dict] = []
    for pos, galeria in enumerate(galerias):
        categoria = rotulos[pos] if pos < len(rotulos) else f"galeria{pos + 1}"
        itens = galeria.select("div._item.item_gallary")
        if verbose:
            print(f"      {categoria}: {len(itens)}")
        for item in itens:
            titulo = item.select_one("h4")
            nome = _limpar(titulo.get_text() if titulo else "")
            link = item.select_one("a[href]")
            href = (link.get("href") or "") if link else ""
            args = _MODAL_ARGS.search(href)

            registro = {"nome": nome, "tipo_associacao": categoria,
                        "menu_code": "", "base_menu_code": "",
                        "site_listagem": "", "origem": "sem_link"}
            if args:
                registro["menu_code"] = args.group(1)
                registro["base_menu_code"] = args.group(2)
                registro["origem"] = "ficha"
            elif href.startswith("http") and "ikora.or.kr" not in href:
                registro["site_listagem"] = href.split("?")[0]
                registro["origem"] = "so_link"
            membros.append(registro)
    return membros


# -------------------------------------------------------------------- extracao

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SO_DIGITOS = re.compile(r"\D")


def _campos_do_modal(html: str) -> dict[str, str]:
    """
    Pares rotulo/valor da ficha.

    O Imweb nao usa tabela nem <dl>: o modal e uma pilha de blocos de texto em
    que o rotulo antecede o valor. Lemos a sequencia de linhas e tratamos toda
    linha que seja um rotulo conhecido como chave da linha seguinte.
    """
    sopa = BeautifulSoup(html, "html.parser")
    for t in sopa(["script", "style"]):
        t.decompose()
    linhas = [_limpar(x) for x in sopa.get_text("\n").split("\n")]
    linhas = [x for x in linhas if x]

    out: dict[str, str] = {}
    i = 0
    while i < len(linhas):
        chave = linhas[i].lower().rstrip(":：")
        if chave in _FIM_DA_FICHA:
            break
        campo = _CAMPOS.get(chave)
        if campo:
            # a descricao se estende por varios paragrafos ate o proximo rotulo
            valores = []
            j = i + 1
            while j < len(linhas):
                seguinte = linhas[j].lower().rstrip(":：")
                if seguinte in _CAMPOS or seguinte in _FIM_DA_FICHA:
                    break
                valores.append(linhas[j])
                j += 1
                if campo != "descricao":
                    break
            if valores and campo not in out:
                out[campo] = " ".join(valores)
            i = j
            continue
        i += 1
    return out


def _dominio(site: str) -> str:
    d = re.sub(r"^https?://", "", (site or "").strip().lower()).split("/")[0]
    return d[4:] if d.startswith("www.") else d


def extrair_empresa(html: str, membro: dict, url_perfil: str) -> Empresa:
    reg = Empresa(url_perfil=url_perfil, nome=membro["nome"],
                  tipo_associacao=membro["tipo_associacao"],
                  coletado_em=datetime.now(timezone.utc).isoformat())
    campos = _campos_do_modal(html)

    email = (campos.get("email") or "").lower()
    achado = _EMAIL.search(email)
    if achado and achado.group(0) not in _EMAIL_INSTITUCIONAL:
        reg.email = achado.group(0)

    site = campos.get("site", "")
    if site.startswith("http") and "ikora.or.kr" not in site:
        reg.site = site.split("?")[0]

    telefone = campos.get("telefone", "")
    if _SO_DIGITOS.sub("", telefone) not in _TELEFONE_INSTITUCIONAL:
        reg.telefone = telefone

    reg.endereco = campos.get("endereco", "")[:300]
    reg.descricao = campos.get("descricao", "")[:800]
    reg.representante = campos.get("representante", "")[:120]
    reg.fundacao = campos.get("fundacao", "")[:60]
    reg.funcionarios = campos.get("funcionarios", "")[:60]
    reg.composicao_receita = campos.get("composicao_receita", "")[:300]

    if not campos:
        reg.erro = "ficha sem campos reconheciveis"
    return reg


def coletar(membros: list[dict], *, base: str = BASE_KO, delay: float = 1.6,
            verbose: bool = True) -> list[Empresa]:
    """
    Coleta as fichas. Quem nao tem ficha entra com o que a listagem oferece.

    Uma associada sem ficha nao e um erro de coleta: a KORA simplesmente nao
    publica os dados dela. Marcamos isso em `erro` para o registro nao ser
    confundido com uma falha de rede, e so gastamos requisicao com quem tem
    ficha de verdade.
    """
    saida: list[Empresa] = []
    com_ficha = sum(1 for m in membros if m["origem"] == "ficha")
    feitas = 0
    for i, m in enumerate(membros, 1):
        agora = datetime.now(timezone.utc).isoformat()
        if m["origem"] != "ficha":
            reg = Empresa(url_perfil=f"{base}/About", nome=m["nome"],
                          site=m["site_listagem"],
                          tipo_associacao=m["tipo_associacao"],
                          coletado_em=agora,
                          erro=("sem ficha publicada; a listagem so traz o site"
                                if m["origem"] == "so_link"
                                else "sem ficha publicada; a listagem so traz o nome"))
        else:
            url = f"{base}/About#{m['menu_code']}"
            try:
                reg = extrair_empresa(_abrir_modal(base, m["menu_code"],
                                                   m["base_menu_code"]), m, url)
            except Exception as exc:
                reg = Empresa(url_perfil=url, nome=m["nome"],
                              tipo_associacao=m["tipo_associacao"],
                              erro=f"{type(exc).__name__}: {exc}"[:150],
                              coletado_em=agora)
            feitas += 1
            if feitas < com_ficha:
                time.sleep(delay)
        saida.append(reg)
        if verbose:
            marca = "." if not reg.erro else ("~" if m["origem"] != "ficha" else "!")
            print(f"  [{i:>3}/{len(membros)}] {marca} "
                  f"{reg.nome[:20]:20} | {reg.email[:28]:28} | {reg.site[:30]}")
    return saida


# ---------------------------------------------------------------- nome latino

def anexar_nomes_latinos(empresas: list[Empresa], *, delay: float = 1.6,
                         verbose: bool = True) -> tuple[int, int]:
    """
    Preenche `nome_latino` e `endereco_latino` a partir do site em ingles.

    Casa pelo e-mail publicado na ficha e, na falta dele, pelo dominio do
    site. Ordem de listagem nao serve de chave: as duas versoes ordenam
    diferente e um casamento por posicao trocaria nomes entre empresas
    vizinhas sem deixar rastro. Chave que aponta para mais de uma empresa
    tambem nao decide nada, e e descartada.

    Devolve (casados, total_em_ingles).
    """
    membros_en = listar_membros(LISTA_EN, categorias=["Full members",
                                                      "Associate members"],
                                verbose=False)
    com_ficha = [m for m in membros_en if m["origem"] == "ficha"]
    if verbose:
        print(f"      {len(membros_en)} itens em ingles "
              f"({len(com_ficha)} com ficha a consultar)")

    # Chave -> candidatos. Nem e-mail nem dominio sao unicos neste diretorio:
    # Korea Research International e Korea Research Center publicam o mesmo
    # info@kric.com, e southernpost.co.kr serve Southern Post e Post Data.
    # Guardamos todos os candidatos e no fim so usamos as chaves que apontam
    # para uma empresa so; do contrario gravariamos o nome latino de uma
    # empresa na linha da vizinha sem nenhum sinal de erro.
    por_email: dict[str, list[dict]] = {}
    por_dominio: dict[str, list[dict]] = {}

    def indexar(nome: str, site: str, endereco: str, email: str) -> None:
        if not nome:
            return
        registro = {"nome": nome, "endereco": endereco}
        achado = _EMAIL.search((email or "").lower())
        if achado:
            por_email.setdefault(achado.group(0), []).append(registro)
        dom = _dominio(site)
        if dom:
            por_dominio.setdefault(dom, []).append(registro)

    for i, m in enumerate(membros_en, 1):
        if m["origem"] != "ficha":
            # sem ficha em ingles ainda ha nome romanizado e, as vezes, o site
            indexar(m["nome"], m["site_listagem"], "", "")
            continue
        try:
            campos = _campos_do_modal(_abrir_modal(BASE_EN, m["menu_code"],
                                                   m["base_menu_code"]))
        except Exception:
            # ficha em ingles e complemento: falhar aqui nao invalida o registro
            campos = {}
        indexar(m["nome"], campos.get("site", ""), campos.get("endereco", ""),
                campos.get("email", ""))
        if verbose and i % 10 == 0:
            print(f"      ... {i}/{len(membros_en)}")
        time.sleep(delay)

    def so_unicos(indice: dict[str, list[dict]]) -> dict[str, dict]:
        return {k: v[0] for k, v in indice.items()
                if len({c["nome"] for c in v}) == 1}

    emails = so_unicos(por_email)
    dominios = so_unicos(por_dominio)
    ambiguos = ((len(por_email) - len(emails)) + (len(por_dominio) - len(dominios)))

    casados = 0
    for e in empresas:
        par = emails.get(e.email.lower()) if e.email else None
        if par is None and e.site:
            par = dominios.get(_dominio(e.site))
        if par:
            e.nome_latino = par["nome"]
            e.endereco_latino = par["endereco"][:300]
            casados += 1
    if verbose and ambiguos:
        print(f"      {ambiguos} chave(s) ambigua(s) descartada(s) do casamento")
    return casados, len(membros_en)


COLUNAS = ["nome", "nome_latino", "email", "site", "pais", "telefone", "endereco",
           "endereco_latino", "descricao", "tipo_associacao", "representante",
           "fundacao", "funcionarios", "composicao_receita", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "kora") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig: sem BOM o Excel coreano le o CSV como CP949 e quebra o hangul
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
