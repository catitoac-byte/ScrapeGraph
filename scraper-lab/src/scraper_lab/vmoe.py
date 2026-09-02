"""
Extrator do diretorio de institutos do VMÖ (Verband der Marktforschung
Österreich), em vmoe.at.

CONFORMIDADE. O robots.txt de www.vmoe.at e lido sem problema e tem um unico
grupo:

    User-Agent: *
    Allow: /

Ou seja, nada proibido e nenhum Crawl-delay declarado; vale a pausa padrao do
projeto. Ainda assim toda URL passa por `permitido()` antes da requisicao.

Paginas renderizadas no servidor: HTTP puro basta, sem navegador.

ARMADILHAS DESTA FONTE:

  a) A pagina /institute/ tem QUATRO secoes com naturezas diferentes:
     institutos austriacos, agencias de midia, prestadores de servico e
     institutos internacionais (quase todos alemaes, marcados com "(D)" no
     proprio rotulo). Jogar tudo como "empresa de pesquisa austriaca" sujaria a
     base em dois eixos ao mesmo tempo, tipo e pais. Cada registro carrega a
     secao literal em `secao`, o pais deduzido do marcador e um campo
     `fornecedor_pesquisa` que so afirma o que a fonte permite afirmar.

  b) Nem todo item tem ficha. Institutos tem pagina propria em vmoe.at;
     agencias e institutos internacionais aparecem so como link para o site
     deles. Esses registros ficam com nome e site, sem inventar contato.

  c) Os caminhos das fichas sao inconsistentes: /institute/, /institut/,
     /institue/ (com erro de digitacao no proprio site) e ate caminho na raiz
     (/bohmann, /matzka). Por isso o vinculo nome-ficha vem SEMPRE do href da
     listagem, nunca de slug montado a partir do nome.

  d) O bloco de contato e uma tabela de duas colunas onde a coluna esquerda
     empilha os rotulos e a direita empilha os valores, pareados por POSICAO.
     Quando o site quebra um rotulo em duas linhas ("Geschäftsführer/" +
     "Ansprechpartner:") o alinhamento sai do lugar. O tratamento esta em
     `_pares_da_linha`: rotulo terminado em "/" e juncao do seguinte, e quando
     mesmo assim as contagens nao batem os valores nao sao distribuidos no
     chute; vao inteiros para o primeiro campo e o registro fica marcado como
     `alinhamento_tabela = ambiguo`. Independente disso, e-mail, site e
     telefone tambem sao procurados por formato no bloco todo, entao o dado que
     mais interessa nunca depende do alinhamento da tabela.
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.vmoe.at"
LISTAGEM = f"{BASE}/institute/"

PAIS = "Austria"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Sem Crawl-delay no robots, vale a pausa padrao do projeto.
DELAY_PADRAO = 1.5

# Contatos do proprio VMÖ, que aparecem no rodape de toda pagina. A extracao ja
# e restrita ao bloco #content, mas o filtro fica como rede de seguranca.
_DOMINIO_ASSOCIACAO = ("vmoe.at", "esomar.org", "efamro.eu")

_ESPACOS = re.compile(r"[ \t   ]+")
_VAZIOS = {"", "-", "--", "n/a", "na", "k.a.", "keine", "/", ":"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_TEXTO = re.compile(r"(?<![@\w.])((?:https?://|www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
                        r"(?:/\S*)?)", re.I)
# Endereco austriaco: rua, virgula, CEP de 4 digitos e cidade ("1010 Wien").
_CEP_CIDADE = re.compile(r"(\d{4})\s+([^\d,;]{2,40})\s*$")
_TELEFONE = re.compile(r"^[+\d][\d\s()./+-]{6,}$")
_PROTOCOLO = re.compile(r"^https?://", re.I)

# Marcador de pais que o proprio VMÖ coloca no rotulo do item internacional.
_MARCA_PAIS = {"D": "Germany", "A": "Austria", "CH": "Switzerland"}


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", (texto or "").replace("​", "").replace("­", ""))
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    # NFC evita que "ö" decomposto e "ö" composto virem duas empresas distintas
    # ao deduplicar contra Esomar e Greenbook.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


def _decodificar(bruto: bytes, ctype: str) -> tuple[str, str]:
    """
    Cabecalho HTTP, depois meta charset, depois utf-8 e latin-1.

    Motivo: o alemao austriaco usa umlaut e ss ("Bösendorferstraße",
    "Weißmann", "Marktforschung Österreichs"). Ler UTF-8 como latin-1 nao
    levanta excecao, so troca o caractere, e o nome corrompido segue para o CSV
    sem nenhum aviso.
    """
    candidatos: list[str] = []
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        candidatos.append(m.group(1))
    m = re.search(rb'charset=["\']?([\w-]+)', bruto[:4096], re.I)
    if m:
        candidatos.append(m.group(1).decode("ascii", "ignore"))
    candidatos += ["utf-8", "latin-1"]
    for enc in candidatos:
        try:
            return bruto.decode(enc), enc.lower()
        except (UnicodeDecodeError, LookupError):
            continue
    return bruto.decode("utf-8", errors="replace"), "utf-8/replace"


# Timeout e 5xx esporadico sao recusa de momento, nao ausencia de ficha.
_ESPERA_RETENTATIVA = (0, 3, 8, 15)

CODIFICACAO_DETECTADA = ""


def _baixar(url: str, *, timeout: int = 45) -> str:
    global CODIFICACAO_DETECTADA
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    cabecalhos = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-AT,de;q=0.9,en;q=0.6",
    }
    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, headers=cabecalhos), timeout=timeout) as r:
                texto, codec = _decodificar(r.read(6_000_000),
                                            r.headers.get("Content-Type", ""))
                CODIFICACAO_DETECTADA = codec
                return texto
        except HTTPError as exc:
            ultimo = exc
            if exc.code in (404, 410):
                break
        except (URLError, TimeoutError, OSError) as exc:
            ultimo = exc
    raise ultimo if ultimo else RuntimeError("falha desconhecida")


@dataclass
class Instituto:
    url_perfil: str
    nome: str = ""
    razao_social: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    cep: str = ""
    cidade: str = ""
    descricao: str = ""
    secao: str = ""             # rotulo literal da secao na pagina do VMÖ
    tipo_membro: str = ""       # instituto / agencia / prestador / internacional
    fornecedor_pesquisa: str = ""
    ano_fundacao: str = ""
    direcao: str = ""           # Geschäftsführung
    contato: str = ""           # Ansprechpartner
    membros_vmoe: str = ""      # pessoas fisicas filiadas ao VMÖ
    especializacoes: str = ""
    alinhamento_tabela: str = ""
    coletado_em: str = ""
    erro: str = ""


# Classificacao das quatro secoes da pagina. O rotulo do site e longo e muda de
# redacao; o casamento e por palavra-chave, e o texto original fica em `secao`.
_SECOES = (
    (re.compile(r"internationale", re.I),
     ("internacional", "sim")),
    (re.compile(r"agentur", re.I),
     # Agencia de midia nao e instituto de pesquisa nem comprador declarado;
     # afirmar qualquer um dos dois seria invencao nossa.
     ("agencia", "indefinido")),
    (re.compile(r"dienstleister", re.I),
     ("prestador", "sim")),
)
_SECAO_PADRAO = ("instituto", "sim")


def _classificar(secao: str) -> tuple[str, str]:
    for padrao, resultado in _SECOES:
        if padrao.search(secao):
            return resultado
    return _SECAO_PADRAO


# Sufixo de pais que o VMÖ escreve no rotulo do item, ex.: "Bilendi GmbH (D)".
_SUFIXO_PAIS = re.compile(r"\s*\(([A-Z]{1,2})\)\s*$")


@dataclass
class Alvo:
    url: str
    nome: str
    secao: str
    interno: bool


def listar_institutos(*, verbose: bool = True) -> tuple[list[Alvo], str]:
    """
    Itens da pagina /institute/, com a secao a que pertencem.

    A pagina nao pagina: e uma sequencia de <h3>/<p><strong> seguidos de <ul>.
    Percorremos o bloco de conteudo em ordem de documento, guardando o ultimo
    titulo visto, porque a secao de um item so pode ser deduzida da posicao
    dele no texto.
    """
    sit = robots_situacao(LISTAGEM, agente=UA)
    sopa = BeautifulSoup(_baixar(LISTAGEM), "html.parser")
    conteudo = sopa.select_one("#content")
    if conteudo is None:
        raise RuntimeError("pagina /institute/ sem bloco #content")

    alvos: list[Alvo] = []
    vistos: set[str] = set()
    secao = ""
    for el in conteudo.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        if el.name in ("h1", "h2", "h3", "h4") or (el.name == "p" and el.find("strong")):
            titulo = _limpar(el.get_text(" ", strip=True))
            # A abertura da pagina e uma frase longa em <h3>; so titulo curto
            # vale como cabecalho de secao.
            if titulo and len(titulo) <= 120:
                secao = titulo
            continue
        if el.name != "li":
            continue
        a = el.find("a", href=True)
        if a is None:
            continue
        href = urljoin(LISTAGEM, a["href"].strip())
        if href in vistos:
            continue
        vistos.add(href)
        interno = urlparse(href).netloc.endswith("vmoe.at")
        alvos.append(Alvo(url=href, nome=_limpar(a.get_text(" ", strip=True)),
                          secao=secao, interno=interno))

    if verbose:
        print(f"      robots.txt: {sit}")
        print(f"      {len(alvos)} itens unicos na pagina")
        por_secao: dict[str, int] = {}
        for alvo in alvos:
            por_secao[alvo.secao] = por_secao.get(alvo.secao, 0) + 1
        for nome, n in por_secao.items():
            print(f"        {n:>3}  {nome[:70]}")
        print(f"      {sum(1 for a in alvos if a.interno)} com ficha em vmoe.at, "
              f"{sum(1 for a in alvos if not a.interno)} so com link externo")
    return alvos, sit


def _linhas_da_celula(td) -> list[str]:
    """
    Linhas visiveis de uma celula, respeitando <br> e <p>.

    O separador de get_text e VAZIO de proposito. Usar "\\n" quebraria tambem
    entre elementos inline, e a linha "www.comrecon.com, www.zeichen-blog.at"
    (dois <a> e uma virgula solta) viraria tres linhas. Como o pareamento com
    os rotulos e por posicao, essas duas linhas extras deslocavam todos os
    campos da ficha.
    """
    copia = BeautifulSoup(str(td), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    for tag in copia.find_all(["p", "div", "li"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    return [l for l in (_limpar(x) for x in copia.get_text("").split("\n")) if l]


def _juntar_rotulos(rotulos: list[str]) -> list[str]:
    """
    Junta rotulo quebrado em duas linhas.

    O site escreve "Geschäftsführer/" numa linha e "Ansprechpartner:" na
    seguinte, o que faz a coluna de rotulos ter uma linha a mais que a de
    valores e desalinha o pareamento por posicao.
    """
    saida: list[str] = []
    for r in rotulos:
        if saida and saida[-1].endswith("/"):
            saida[-1] = saida[-1] + r
        else:
            saida.append(r)
    return saida


# rotulo (minusculo, sem acento irrelevante) -> campo do registro
_CAMPOS = (
    (re.compile(r"adress", re.I), "endereco"),
    (re.compile(r"\btel\b|phone|telefon", re.I), "telefone"),
    (re.compile(r"mail", re.I), "email"),
    (re.compile(r"internet|website|homepage", re.I), "site"),
    (re.compile(r"gründungsjahr|grundungsjahr", re.I), "ano_fundacao"),
    (re.compile(r"geschäftsführ|geschaftsfuhr|geschäftsfüher", re.I), "direcao"),
    (re.compile(r"ansprechpartner", re.I), "contato"),
    (re.compile(r"vmö.?mitglied|vmo.?mitglied", re.I), "membros_vmoe"),
)


_TEXTUAIS = ("p", "li", "h2", "h3", "h4")


def _fatiar(conteudo, marco) -> tuple[list, list]:
    """
    Divide os elementos textuais do bloco em (antes do marco, depois do marco).

    A varredura e por `descendants`, que anda em ordem de documento e nunca sai
    do bloco. Sair dele era o defeito de `find_all_next`: numa ficha sem texto
    proprio a busca continuava pelo documento e trazia o menu do rodape como se
    fosse a descricao da empresa.
    """
    antes: list = []
    depois: list = []
    passou = False
    for el in conteudo.descendants:
        if el is marco:
            passou = True
            continue
        if getattr(el, "name", None) not in _TEXTUAIS:
            continue
        if el.find_parent("table") is not None:
            continue
        (depois if passou else antes).append(el)
    return antes, depois


def _campo_de(rotulo: str) -> str:
    for padrao, campo in _CAMPOS:
        if padrao.search(rotulo):
            return campo
    return ""


def _pares_da_linha(rotulos: list[str], valores: list[str]) -> tuple[dict[str, str], bool]:
    """
    Pareia rotulos e valores de uma linha da tabela.

    Devolve (campos, ambiguo). Quando as contagens batem, o pareamento e
    posicional. Quando nao batem, NAO chutamos a distribuicao: todos os valores
    vao para o campo do primeiro rotulo e o chamador marca o registro como
    ambiguo. Melhor um campo com informacao a mais e um aviso do que tres
    campos com atribuicao errada e ar de certeza.
    """
    rotulos = _juntar_rotulos(rotulos)
    campos: dict[str, str] = {}
    if not rotulos or not valores:
        return campos, False
    if len(rotulos) == len(valores):
        for rotulo, valor in zip(rotulos, valores):
            campo = _campo_de(rotulo)
            if campo and valor:
                campos[campo] = valor
        return campos, False
    campo = _campo_de(rotulos[0])
    if campo:
        campos[campo] = " | ".join(valores)
    return campos, True


# E-mail ofuscado contra robo de spam. A ficha da Context-Research publica
# "emanuel.maxl(at)context-research.at"; sem desfazer isso o instituto entra na
# base sem e-mail nenhum, que e justamente o dado que a fonte nacional tem e a
# global nao.
_OFUSCADO = re.compile(r"\s*[\(\[\{]\s*(at|arobase)\s*[\)\]\}]\s*", re.I)
_OFUSCADO_PONTO = re.compile(r"\s*[\(\[\{]\s*(dot|punkt)\s*[\)\]\}]\s*", re.I)


def _desofuscar(texto: str) -> str:
    return _OFUSCADO_PONTO.sub(".", _OFUSCADO.sub("@", texto or ""))


# Rotulo seguido de dois pontos, no comeco da linha. Usado so nas fichas que
# nao tem tabela.
_ROTULO_LINHA = re.compile(r"^([A-Za-zÄÖÜäöüß&/ .-]{3,60}?)\s*:\s*(.*)$")


def _pares_de_texto(conteudo) -> dict[str, str]:
    """
    Le "Rotulo: valor" de ficha escrita em paragrafos, sem tabela.

    Duas das 69 fichas (Context-Research e Creativ Research) publicam os mesmos
    campos como texto corrido. Sem este caminho elas entrariam na base so com o
    nome, perdendo e-mail, endereco, fundacao e nome do responsavel, que e
    exatamente o que a associacao nacional acrescenta as bases globais.

    O valor as vezes fica na linha seguinte ao rotulo ("Web:" numa linha,
    "www.context-research.at" na outra), entao o rotulo sem valor fica
    pendente ate a proxima linha util.
    """
    campos: dict[str, str] = {}
    pendente = ""
    for el in conteudo.find_all(["p", "li", "div"]):
        for linha in _linhas_da_celula(el):
            m = _ROTULO_LINHA.match(linha)
            if m:
                campo = _campo_de(m.group(1))
                valor = _limpar(m.group(2))
                pendente = ""
                if not campo:
                    continue
                if valor:
                    campos.setdefault(campo, valor)
                else:
                    pendente = campo
                continue
            if pendente:
                campos.setdefault(pendente, linha)
                pendente = ""
    return campos


def extrair_instituto(html: str, alvo: Alvo) -> Instituto:
    reg = Instituto(url_perfil=alvo.url, nome=alvo.nome, secao=alvo.secao,
                    coletado_em=datetime.now(timezone.utc).isoformat())
    reg.tipo_membro, reg.fornecedor_pesquisa = _classificar(alvo.secao)

    sopa = BeautifulSoup(html, "html.parser")
    conteudo = sopa.select_one("#content")
    if conteudo is None:
        reg.erro = "ficha sem bloco #content"
        return reg
    for t in conteudo(["script", "style", "noscript"]):
        t.decompose()

    ambiguo = False
    tabela = conteudo.find("table")
    if tabela is not None:
        antes, depois = _fatiar(conteudo, tabela)
    else:
        # Sem tabela, a apresentacao se mistura aos pares rotulo/valor. Ficam
        # de fora as linhas que sao rotulo, para a descricao nao virar copia
        # dos campos ja extraidos.
        antes = []
        depois = [el for el in conteudo.find_all(_TEXTUAIS)
                  if not _ROTULO_LINHA.match(_limpar(el.get_text(" ", strip=True)))]
    if tabela is not None:
        for tr in tabela.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            campos, amb = _pares_da_linha(_linhas_da_celula(tds[0]),
                                          _linhas_da_celula(tds[1]))
            ambiguo = ambiguo or amb
            for campo, valor in campos.items():
                if not getattr(reg, campo, ""):
                    setattr(reg, campo, valor)
        # A razao social abre a ficha, antes da tabela. Pegamos o PRIMEIRO
        # paragrafo do bloco, nao o mais proximo da tabela: varias fichas
        # colocam um subtitulo de posicionamento logo acima dela ("Spezialist
        # für Lebensmittel- und Agrarmarktforschung"), que nao e razao social.
        for el in antes:
            legal = _limpar(el.get_text(" ", strip=True))
            if legal and len(legal) <= 120:
                reg.razao_social = legal
                break
    else:
        # Ficha sem tabela nao e ficha vazia: duas delas escrevem os mesmos
        # campos em paragrafos.
        for campo, valor in _pares_de_texto(conteudo).items():
            if not getattr(reg, campo, ""):
                setattr(reg, campo, valor)
        primeiro = conteudo.find(["p", "h1", "h2"])
        if primeiro is not None:
            legal = _limpar(primeiro.get_text(" ", strip=True))
            if legal and len(legal) <= 120:
                reg.razao_social = legal
        if not (reg.email or reg.endereco or reg.telefone):
            reg.erro = "ficha sem tabela e sem pares rotulo/valor"
    reg.alinhamento_tabela = "ambiguo" if ambiguo else "ok"

    # Rede de seguranca por formato: o e-mail e o site sao o dado que mais
    # interessa e nao podem depender do alinhamento da tabela.
    texto = _desofuscar(conteudo.get_text(" ", strip=True))
    reg.email = _desofuscar(reg.email)
    if not _EMAIL.fullmatch(reg.email or "x"):
        reg.email = ""
    if not reg.email:
        link = conteudo.find("a", href=re.compile(r"^mailto:", re.I))
        if link is not None:
            reg.email = _limpar(link["href"][7:].split("?")[0])
        else:
            achado = [e for e in _EMAIL.findall(texto)
                      if not any(d in e.lower() for d in _DOMINIO_ASSOCIACAO)]
            reg.email = achado[0] if achado else ""
    if reg.email and any(d in reg.email.lower() for d in _DOMINIO_ASSOCIACAO):
        reg.email = ""

    if not reg.site:
        for a in conteudo.select('a[href^="http"]'):
            href = a["href"].strip()
            if not any(d in href.lower() for d in _DOMINIO_ASSOCIACAO):
                reg.site = href
                break
    if not reg.site:
        m = _URL_TEXTO.search(texto)
        if m and not any(d in m.group(1).lower() for d in _DOMINIO_ASSOCIACAO):
            reg.site = m.group(1)
    # Varias fichas listam dois enderecos no mesmo campo ("www.comrecon.com,
    # www.zeichen-blog.at"). O institucional e o primeiro; o segundo e blog ou
    # marca secundaria, e gravar os dois juntos quebraria o casamento por
    # dominio na etapa de uniao.
    if reg.site:
        m = _URL_TEXTO.search(reg.site)
        reg.site = _limpar(m.group(1) if m else reg.site.split(",")[0])
    if reg.site and not _PROTOCOLO.match(reg.site):
        reg.site = "https://" + reg.site.lstrip("/")

    if reg.telefone and not _TELEFONE.match(reg.telefone):
        reg.telefone = ""

    if reg.endereco:
        m = _CEP_CIDADE.search(reg.endereco)
        if m:
            reg.cep, reg.cidade = m.group(1), _limpar(m.group(2))

    # A apresentacao ("Credo", "Leistungsangebot") vem depois da tabela. A
    # varredura fica PRESA ao bloco #content: `find_all_next` sai do bloco e
    # segue pelo documento, e a ficha da MAKAM, que nao tem texto proprio,
    # acabava com o menu do rodape ("Home | Impressum | Datenschutz") no lugar
    # da descricao.
    partes: list[str] = []
    for el in depois:
        t = _limpar(el.get_text(" ", strip=True))
        if t and t not in partes:
            partes.append(t)
    reg.descricao = " | ".join(partes)[:1200]
    # As linhas de "Leistungsangebot" descrevem especialidades; guardamos as
    # primeiras separadas, que e o que a etapa de uniao consome.
    reg.especializacoes = " | ".join(partes[1:9])[:600]

    if not reg.nome:
        reg.nome = reg.razao_social
    if not reg.nome and not reg.erro:
        reg.erro = "ficha sem nome"
    return reg


def _sem_ficha(alvo: Alvo) -> Instituto:
    """
    Registro de item que so tem link externo.

    Agencias e institutos internacionais nao tem pagina no VMÖ. Guardamos nome,
    site e secao; o pais vem do marcador que o proprio VMÖ escreve no rotulo
    ("Bilendi GmbH (D)"), e nao de suposicao nossa.
    """
    nome = alvo.nome
    pais = PAIS
    m = _SUFIXO_PAIS.search(nome)
    if m:
        nome = _limpar(nome[:m.start()])
        pais = _MARCA_PAIS.get(m.group(1).upper(), "")
    reg = Instituto(url_perfil="", nome=nome, site=alvo.url, pais=pais,
                    secao=alvo.secao,
                    coletado_em=datetime.now(timezone.utc).isoformat())
    reg.tipo_membro, reg.fornecedor_pesquisa = _classificar(alvo.secao)
    if not pais:
        reg.erro = "pais nao declarado pela fonte"
    return reg


def coletar(alvos: list[Alvo], *, delay: float = DELAY_PADRAO,
            verbose: bool = True) -> list[Instituto]:
    institutos: list[Instituto] = []
    total = len(alvos)
    pediu = 0
    for i, alvo in enumerate(alvos, 1):
        if not alvo.interno:
            reg = _sem_ficha(alvo)
        else:
            pediu += 1
            if pediu > 1:
                time.sleep(delay)
            try:
                reg = extrair_instituto(_baixar(alvo.url), alvo)
            except Exception as exc:
                reg = Instituto(url_perfil=alvo.url, nome=alvo.nome, secao=alvo.secao,
                                erro=f"{type(exc).__name__}: {exc}"[:150],
                                coletado_em=datetime.now(timezone.utc).isoformat())
                reg.tipo_membro, reg.fornecedor_pesquisa = _classificar(alvo.secao)
        institutos.append(reg)
        if verbose:
            print(f"  [{i:>3}/{total}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:34]:34} | {reg.email[:28]:28} | {reg.cidade[:14]}")
    return institutos


COLUNAS = ["nome", "razao_social", "email", "site", "pais", "telefone", "endereco",
           "cep", "cidade", "secao", "tipo_membro", "fornecedor_pesquisa",
           "ano_fundacao", "direcao", "contato", "membros_vmoe", "especializacoes",
           "descricao", "alinhamento_tabela", "url_perfil", "erro"]


def exportar(institutos: list[Instituto], nome: str = "vmoe_austria") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(i) for i in institutos], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig porque o Excel em maquina alema ou austriaca abre utf-8 sem BOM
    # como latin-1 e transforma "Weißmann" e "Österreich" em lixo.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for i in institutos:
            d = asdict(i)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
