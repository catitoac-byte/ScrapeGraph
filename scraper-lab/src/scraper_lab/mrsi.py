"""
Extrator do diretorio de associadas da MRSI, a Market Research Society of
India (mrsi.co.in).

Por que a raiz parece um placeholder: https://www.mrsi.co.in/ devolve 99
bytes porque e so um <meta refresh> apontando para /new/index.html, uma
pagina de "novo site em breve". O site real continua em /home.html e o
diretorio de associadas em /mrsicms/, ambos publicos e sem login.

Duas armadilhas de acesso:

  TLS   o servidor nao entrega a cadeia completa, e o bundle embutido do
        Python recusa o certificado. So o trust store do sistema aceita, dai
        o truststore em toda requisicao.
  JSP   a aplicacao e uma Struts com sessao. Sem carregar a listagem antes e
        guardar o JSESSIONID, o POST de detalhe volta para a home. Por isso
        toda a coleta corre sobre um unico opener com cookies.

A listagem tem tres abas (type): 1 corporativas, 2 educacionais, 3
individuais. So a primeira interessa a uma base de empresas; as individuais
sao pessoas fisicas e nao entram.

Codificacao: a MRSI responde utf-8 e o conteudo e latino, entao `nome` e
`nome_latino` coincidem. Mantemos as duas colunas para o CSV casar com o
formato do Japao e da Coreia na hora de unir as bases.
"""

from __future__ import annotations

import csv
import http.cookiejar
import json
import re
import ssl
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

import truststore
from bs4 import BeautifulSoup

from scraper_lab import robots as robots_mod
from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.mrsi.co.in"
LISTAGEM = f"{BASE}/mrsicms/home/HomeAction?doDirectorys=yes&type={{}}"
PAGINACAO = f"{BASE}/mrsicms/ajax/home/getinfo_directory2.jsp"
ACAO = f"{BASE}/mrsicms/home/HomeAction"

PAIS = "India"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

TIPO_CORPORATIVO = 1

# Contatos da propria MRSI, no rodape de toda pagina.
_EMAIL_INSTITUCIONAL = {"admin@mrsi.co.in", "info@mrsi.co.in",
                        "secretariat@mrsi.co.in", "mrsi@mrsi.co.in"}
_DOMINIO_IGNORADO = ("mrsi.co.in", "facebook.com", "linkedin.com", "twitter.com",
                     "x.com", "youtube.com", "instagram.com")

_ESPACOS = re.compile(r"\s+")
_VAZIOS = {"", "-", "--", "n/a", "na"}

_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _limpar(t: str | None) -> str:
    v = _ESPACOS.sub(" ", (t or "").replace("\xa0", " ")).strip()
    return "" if v.lower() in _VAZIOS else v


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)
_CANDIDATOS = ("utf-8", "cp1252", "latin-1")
_APELIDOS = {"utf8": "utf-8", "iso-8859-1": "latin-1", "windows-1252": "cp1252"}

_codificacoes_vistas: dict[str, int] = {}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """Texto e codificacao usada, validando em modo estrito antes de aceitar."""
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


# ---------------------------------------------------------------------- sessao

class Sessao:
    """
    Opener unico com cookies e o contexto TLS do sistema.

    A aplicacao devolve o diretorio so para quem ja tem JSESSIONID, entao
    listagem, paginacao e detalhe precisam correr sobre a mesma sessao.
    """

    def __init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies),
                                   HTTPSHandler(context=_CTX))
        self.opener.addheaders = [("User-Agent", UA),
                                  ("Accept-Language", "en-IN,en;q=0.9")]

    def _abrir(self, req: Request, timeout: int) -> str:
        with self.opener.open(req, timeout=timeout) as resp:
            bruto = resp.read(4_000_000)
            charset = resp.headers.get_content_charset()
        texto, usada = _decodificar(bruto, charset)
        _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
        return texto

    def obter(self, url: str, timeout: int = 30) -> str:
        if not robots_permitido(url, agente=UA):
            raise PermissionError(f"robots.txt proibe {url}")
        return self._abrir(Request(url), timeout)

    def enviar(self, url: str, campos: dict[str, str], *, referer: str,
               ajax: bool = False, timeout: int = 30) -> str:
        if not robots_permitido(url, agente=UA):
            raise PermissionError(f"robots.txt proibe {url}")
        cabecalhos = {"Referer": referer,
                      "Content-Type": "application/x-www-form-urlencoded"}
        if ajax:
            cabecalhos["X-Requested-With"] = "XMLHttpRequest"
        return self._abrir(
            Request(url, data=urllib.parse.urlencode(campos).encode(),
                    headers=cabecalhos), timeout)


def _preparar_robots() -> str:
    """
    Carrega o robots.txt com o contexto TLS certo antes de qualquer coleta.

    Sem isto o `robots.para()` falha no handshake, engole a excecao e o
    `permitido()` libera tudo por engano. Uma liberacao que na verdade e erro
    de rede e o pior desfecho possivel numa verificacao de conformidade.
    """
    from urllib.request import urlopen
    try:
        req = Request(f"{BASE}/robots.txt", headers={"User-Agent": UA})
        with urlopen(req, timeout=15, context=_CTX) as r:
            texto = r.read(500_000).decode("utf-8", errors="replace")
        regras = robots_mod.Robots(texto, UA)
        robots_mod._cache[BASE] = regras
        return f"robots.txt lido: {len(regras.proibir)} Disallow"
    except Exception as exc:
        robots_mod._cache[BASE] = None
        return f"sem robots.txt utilizavel ({type(exc).__name__}); padrao permitir"


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
    cidade: str = ""
    descricao: str = ""
    tipo_associacao: str = ""
    tipo_atividade: str = ""
    especialidades: str = ""
    industrias: str = ""
    servicos: str = ""
    contatos: str = ""
    codigo_membro: str = ""
    redes_sociais: list[str] = field(default_factory=list)
    coletado_em: str = ""
    erro: str = ""


# ------------------------------------------------------------------- listagem

_ID_MEMBRO = re.compile(r"viewMemberDetail\((\d+)\)")
# O contador vem como "Page&nbsp;1 of 15,&nbsp;(1 - 12 record(s) of 179)".
# `_ESPACOS` nao cobre a entidade HTML crua, entao normalizamos antes: sem
# isso o total de paginas sai zero e a coleta para na terceira pagina.
_ENTIDADE_ESPACO = re.compile(r"&nbsp;|&#160;|\xa0")
_TOTAL = re.compile(r"record\(s\)\s*of\s*([\d,]+)", re.I)
_PAGINAS = re.compile(r"Page\s*(\d+)\s*of\s*([\d,]+)", re.I)


def _cards(html: str) -> list[dict]:
    """(id, nome, categoria) dos cartoes de uma pagina da listagem."""
    sopa = BeautifulSoup(html, "html.parser")
    saida: list[dict] = []
    for gatilho in sopa.select("a[onclick*=viewMemberDetail]"):
        m = _ID_MEMBRO.search(gatilho.get("onclick") or "")
        if not m:
            continue
        # o cartao inteiro e o <li>; nome e categoria moram no <strong>
        cartao = gatilho.find_parent("li") or gatilho.parent
        forte = cartao.find("strong") if cartao else None
        rotulo = cartao.select_one("a.corp_tooltip[aria-label]") if cartao else None
        saida.append({
            "id": int(m.group(1)),
            "nome": _limpar(forte.get_text(" ") if forte else ""),
            "tipo_associacao": _limpar(rotulo.get("aria-label")) if rotulo else "",
        })
    return saida


def _totais(html: str) -> tuple[int, int]:
    """(registros declarados, paginas declaradas) segundo o proprio site."""
    texto = _ENTIDADE_ESPACO.sub(" ", html)
    total = _TOTAL.search(texto)
    paginas = _PAGINAS.search(texto)
    return (int(total.group(1).replace(",", "")) if total else 0,
            int(paginas.group(2).replace(",", "")) if paginas else 0)


def listar_empresas(sessao: Sessao, *, tipo: int = TIPO_CORPORATIVO,
                    delay: float = 1.6, verbose: bool = True) -> tuple[list[dict], int]:
    """
    Todas as associadas da aba `tipo`, sem repeticao, e o total declarado.

    A paginacao so para depois de DUAS paginas seguidas sem cartao novo: uma
    pagina vazia isolada costuma ser lentidao do JSP, e parar nela truncaria a
    lista sem erro nenhum aparente.
    """
    url_aba = LISTAGEM.format(tipo)
    primeira = sessao.obter(url_aba)
    declarado, paginas = _totais(primeira)
    if verbose:
        print(f"      o site declara {declarado} registros em {paginas} paginas")

    vistos: dict[int, dict] = {}
    for c in _cards(primeira):
        vistos.setdefault(c["id"], c)

    vazias = 0
    limite = max(paginas, 1)
    indice = 1  # a pagina 1 (doDirect=0) ja veio no GET acima
    while indice < limite + 2:  # folga: confirma o fim em vez de confiar nele
        time.sleep(delay)
        try:
            html = sessao.enviar(PAGINACAO, {
                "directory": "yes", "nextValue": str(indice), "next": "n",
                "type": str(tipo), "search": "", "doDirect": str(indice),
                "researchServices": "", "specialities": "", "industries": "",
                "type_advance": "0"}, referer=url_aba, ajax=True)
        except Exception as exc:
            # falha de rede nao e fim de lista: conta como pagina vazia e segue
            if verbose:
                print(f"      pagina {indice + 1}: {type(exc).__name__}")
            vazias += 1
            indice += 1
            if vazias >= 2:
                break
            continue

        novos = 0
        for c in _cards(html):
            if c["id"] not in vistos:
                vistos[c["id"]] = c
                novos += 1
        if verbose:
            print(f"      pagina {indice + 1}: +{novos} (acumulado {len(vistos)})")
        vazias = vazias + 1 if novos == 0 else 0
        if vazias >= 2:
            break
        indice += 1

    return sorted(vistos.values(), key=lambda c: c["id"]), declarado


# -------------------------------------------------------------------- extracao

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TELEFONE = re.compile(r"(?:\+91[\s-]?)?(?:\d[\d\s().-]{8,17}\d)")


def separar_email_do_endereco(endereco: str, email_atual: str) -> tuple[str, str]:
    """
    Tira e-mails colados no campo de endereco e devolve (endereco, email).

    Algumas associadas preencheram o cadastro do proprio site com e-mails
    dentro do endereco ("info@exemplo..., exemploinsight@gmail.com, Noida").
    Deixar isso no endereco suja a coluna, e jogar fora perderia contato de
    quem nao publicou e-mail em outro lugar. O e-mail so e adotado quando a
    coluna esta vazia; nunca substitui o que a ficha declarou como contato.
    """
    if not endereco:
        return endereco, email_atual
    achados = [a for a in _EMAIL.findall(endereco)
               if a.lower() not in _EMAIL_INSTITUCIONAL]
    if not achados:
        return endereco, email_atual
    limpo = _EMAIL.sub(" ", endereco)
    limpo = _limpar(re.sub(r"(?:\s*,\s*)+", ", ", limpo).strip(" ,"))
    return limpo, (email_atual or achados[0].lower())


def _lista_do_bloco(sopa: BeautifulSoup, titulo: str) -> str:
    """Itens do bloco de especializacao com o titulo dado."""
    for bloco in sopa.select("div.research-specialization"):
        cabeca = bloco.find(["h2", "h3"])
        if cabeca and _limpar(cabeca.get_text()).lower() == titulo.lower():
            itens = [_limpar(li.get_text(" ")) for li in bloco.select("li")]
            return " | ".join(i for i in itens if i)
    return ""


def extrair_empresa(html: str, cartao: dict, url_perfil: str) -> Empresa:
    reg = Empresa(url_perfil=url_perfil, nome=cartao.get("nome", ""),
                  tipo_associacao=cartao.get("tipo_associacao", ""),
                  codigo_membro=str(cartao.get("id", "")),
                  coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    titulo = sopa.select_one("div.div-banner h1")
    if titulo:
        reg.nome = _limpar(titulo.get_text()) or reg.nome
    reg.nome_latino = reg.nome  # o diretorio indiano ja publica em alfabeto latino

    cabecalho = sopa.select_one("div.research-title")
    if cabecalho:
        cidade = cabecalho.find("p")
        reg.cidade = _limpar(cidade.get_text() if cidade else "")
        if not reg.tipo_associacao:
            rotulo = cabecalho.select_one("a.corp_tooltip[aria-label]")
            reg.tipo_associacao = _limpar(rotulo.get("aria-label")) if rotulo else ""

    caixas = sopa.select("div.research-box-detail")
    if caixas:
        endereco = caixas[0].find("p")
        reg.endereco = _limpar(endereco.get_text(" ") if endereco else "")[:300]

    # a ficha traz um resumo curto e, mais abaixo, o texto institucional longo;
    # o maior descreve melhor a empresa
    paragrafos = [_limpar(p.get_text(" ")) for p in sopa.select("p.para-align")]
    if paragrafos:
        reg.descricao = max(paragrafos, key=len)[:800]

    for item in sopa.select("ul.detail-ul li"):
        rotulo = item.find("p")
        chave = _limpar(rotulo.get_text() if rotulo else "").lower()
        if chave.startswith("visit website"):
            link = item.find("a", href=True)
            alvo = link["href"] if link else ""
            if alvo.startswith("http") and not any(d in alvo for d in _DOMINIO_IGNORADO):
                reg.site = alvo.split("?")[0]
        elif chave.startswith("contact"):
            # o e-mail vem no texto e tambem no onclick do contador de cliques
            achado = _EMAIL.search(item.get_text(" ")) or _EMAIL.search(str(item))
            if achado and achado.group(0).lower() not in _EMAIL_INSTITUCIONAL:
                reg.email = achado.group(0).lower()
        elif chave.startswith("social"):
            reg.redes_sociais = [a["href"] for a in item.select("a[href^=http]")][:6]

    for info in sopa.select("div.research-box-info"):
        cabeca = info.find(["h2", "h3"])
        chave = _limpar(cabeca.get_text() if cabeca else "").rstrip(":").lower()
        valor = info.find("p")
        if chave == "activity type" and valor:
            reg.tipo_atividade = _limpar(valor.get_text(" "))[:200]

    reg.especialidades = _lista_do_bloco(sopa, "Specialities")[:400]
    reg.industrias = _lista_do_bloco(sopa, "Industries")[:400]
    reg.servicos = _lista_do_bloco(sopa, "Research Services")[:400]

    # Pessoas indicadas pela propria empresa no diretorio publico. Guardamos
    # nome e cargo, como a base Esomar faz, e nunca e-mail pessoal.
    contatos = []
    for tr in sopa.select("#detailsModal table tr"):
        celulas = [_limpar(td.get_text(" ")) for td in tr.find_all("td")]
        if len(celulas) >= 2 and celulas[0]:
            contatos.append(f"{celulas[0]} ({celulas[1]})" if celulas[1] else celulas[0])
    reg.contatos = " | ".join(contatos[:8])

    reg.endereco, reg.email = separar_email_do_endereco(reg.endereco, reg.email)

    corpo = sopa.get_text(" ")
    achado = _TELEFONE.search(corpo)
    if achado and reg.endereco:
        # so aceita telefone que nao seja parte do CEP colado no endereco
        candidato = _limpar(achado.group(0))
        if candidato not in reg.endereco:
            reg.telefone = candidato

    if not reg.nome:
        reg.erro = "sem nome na ficha"
    return reg


def coletar(sessao: Sessao, cartoes: list[dict], *, tipo: int = TIPO_CORPORATIVO,
            delay: float = 1.6, verbose: bool = True) -> list[Empresa]:
    url_aba = LISTAGEM.format(tipo)
    saida: list[Empresa] = []
    for i, cartao in enumerate(cartoes, 1):
        url = f"{ACAO}?doViewMember=yes&Id={cartao['id']}&type={tipo}"
        try:
            html = sessao.enviar(ACAO, {
                "type": str(tipo), "Id": str(cartao["id"]), "doViewMember": "yes",
                "alphaSearch": "", "advSearch": "", "type_advance": "0",
                "searchDir": "", "nextDel": "12", "totalpage": "15",
                "nextValue": "1"}, referer=url_aba)
            reg = extrair_empresa(html, cartao, url)
        except Exception as exc:
            reg = Empresa(url_perfil=url, nome=cartao.get("nome", ""),
                          tipo_associacao=cartao.get("tipo_associacao", ""),
                          codigo_membro=str(cartao["id"]),
                          erro=f"{type(exc).__name__}: {exc}"[:150],
                          coletado_em=datetime.now(timezone.utc).isoformat())
        saida.append(reg)
        if verbose:
            print(f"  [{i:>3}/{len(cartoes)}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:32]:32} | {reg.email[:30]:30} | {reg.cidade[:16]}")
        if i < len(cartoes):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "nome_latino", "email", "site", "pais", "telefone", "endereco",
           "cidade", "descricao", "tipo_associacao", "tipo_atividade",
           "especialidades", "industrias", "servicos", "contatos",
           "redes_sociais", "codigo_membro", "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "mrsi") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            d["redes_sociais"] = " | ".join(d.get("redes_sociais") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
