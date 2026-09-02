"""
Extrator das associadas do SEDEA, a associacao grega das empresas de
pesquisa de mercado e opiniao (Syndesmos Etaireion Dimoskopiseon kai
Ereunas Agoras, sedea.gr).

Por que SEDEA e nao PEDET: o dominio pedet.gr nao resolve (NXDOMAIN, nao
timeout nem 5xx). A entidade viva e o SEDEA, que publica o quadro de
associadas em duas paginas distintas do mesmo site:

  /αναλυτικα-στοιχεια-μελων/   tabela com telefone, e-mail, site,
                               representantes e certificacao
  /μέλη-σεδεα/                 cartoes com o endereco postal

A tabela e a fonte primaria; a pagina de cartoes entra so como
enriquecimento de endereco.

CASAMENTO ENTRE AS DUAS PAGINAS. As duas listam as mesmas empresas com
grafias diferentes: a tabela traz "ABACUS RESEARCH A.E" e o cartao traz
"ABACUS RESEARCH S.A.". Nome nao serve de chave. Posicao tambem nao: as
duas paginas foram editadas em epocas diferentes e nem sequer tem a mesma
quantidade de itens. O nome do arquivo do logo entao e o pior candidato de
todos, porque o SEDEA usa nomes genericos e reciclados (members-01.jpg,
members-03.jpg, members-42.jpg) que nao dizem nada sobre a empresa.
Casamos pelo E-MAIL, que aparece nas duas paginas e e unico por empresa;
chave que aponta para mais de uma empresa e descartada e o endereco fica
vazio, em vez de receber o endereco da vizinha.

CATEGORIA DE ASSOCIADA. A pagina tem dois titulos, ΤΑΚΤΙΚΑ ΜΕΛΗ (plenas) e
ΣΥΝΔΕΔΕΜΕΝΑ ΜΕΛΗ (associadas), cada um com sua tabela. Nao deduzimos a
categoria pela ordem das tabelas no documento: cada linha ja traz a coluna
ΚΑΤΗΓΟΡΙΑ ΜΕΛΟΥΣ, que e o dado da propria fonte. O titulo serve so de
conferencia, e divergencia entre os dois e registrada.

CODIFICACAO, o ponto critico aqui. O site responde utf-8, mas duas
armadilhas gregas continuam de pe:

1. iso-8859-7 e cp1253 aceitam qualquer byte sem levantar excecao. Se um
   dia o cabecalho declarar iso-8859-7 servindo utf-8, "ΑΘΗΝΑ" vira
   "Î‘Î˜Î—ÎÎ‘" em silencio. `_decodificar` roda um teste de mojibake antes
   de aceitar uma tabela de um byte.
2. O proprio cabecalho da tabela usa Ε-mail com EPSILON MAIUSCULO grego
   (U+0395), nao o E latino. Casar cabecalho por texto latino falharia. Por
   isso mapeamos as colunas pela classe column-N do TablePress, que e
   estavel, e usamos o texto do cabecalho apenas para conferir.
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

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://sedea.gr"
# As URLs sao gregas; o servidor aceita a forma percent-encoded.
PAGINA_TABELA = BASE + "/" + urllib.parse.quote("αναλυτικα-στοιχεια-μελων") + "/"
PAGINA_CARTOES = BASE + "/" + urllib.parse.quote("μέλη-σεδεα") + "/"

PAIS = "Greece"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# robots.txt do SEDEA proibe so /wp-admin/ e libera admin-ajax.php. Nao
# declara Crawl-delay, entao vale a pausa padrao do projeto.
PAUSA_PADRAO = 1.5

# Contatos do proprio SEDEA, no rodape de toda pagina.
_EMAIL_INSTITUCIONAL = {"info@sedea.gr", "sedea@sedea.gr"}
_TELEFONE_INSTITUCIONAL = {"2103390000", "2107259040"}

_ESPACOS = re.compile(r"[\s ​]+")
_VAZIOS = {"", "-", "--", "n/a", "να", "—"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", (texto or "")).strip()
    # NFC: o grego tem vogais acentuadas que existem composta e decomposta.
    # Sem normalizar, "Αθήνα" decomposto e "Αθήνα" composto viram cidades
    # diferentes na hora de agrupar.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)
_CANDIDATOS = ("utf-8", "cp1253", "iso-8859-7")
_APELIDOS = {"utf8": "utf-8", "windows-1253": "cp1253", "iso8859-7": "iso-8859-7",
             "greek": "iso-8859-7", "iso_8859-7": "iso-8859-7", "elot928": "iso-8859-7"}
_UM_BYTE = {"cp1253", "iso-8859-7", "latin-1", "iso-8859-1"}

# utf-8 lido como tabela de um byte: em grego o prefixo tipico e 0xCE/0xCF,
# que em cp1253 viram "Î"/"Ï" seguidos de um byte de continuacao.
_MOJIBAKE = re.compile(r"[ÎÏÂÃ][-¿ŒœŽž’€]")

_codificacoes_vistas: dict[str, int] = {}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """
    Texto e nome da codificacao efetivamente usada.

    Ordem: cabecalho HTTP, meta charset, depois os candidatos do idioma.
    Quando o vencedor e uma tabela de um byte, conferimos o resultado contra
    a assinatura de mojibake antes de aceitar, porque essas tabelas nunca
    falham e um nome grego corrompido nao levanta excecao nenhuma.
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


_GREGO = re.compile(r"[Ͱ-Ͽἀ-῿]")


def tem_letras_gregas(texto: str) -> bool:
    """Prova viva de que a codificacao resistiu ao trajeto."""
    return bool(_GREGO.search(texto or ""))


def _e_latino(texto: str) -> bool:
    """
    True quando a maioria das letras do texto e do alfabeto latino.

    Serve para decidir se o titulo comercial vale como `nome_latino`: o
    SEDEA usa a coluna para os dois alfabetos, e gravar um nome grego na
    coluna latina esvazia o proposito dela.
    """
    letras = [c for c in (texto or "") if c.isalpha()]
    if not letras:
        return False
    latinas = sum(1 for c in letras if "LATIN" in unicodedata.name(c, ""))
    return latinas >= len(letras) * 0.7


# ------------------------------------------------------------------- download

def _tentar(func, *, tentativas: int = 3, base_espera: float = 2.0):
    """
    Repete com espera crescente. Timeout ou 403 esporadico nao e ausencia de
    dado: sem retentativa a pagina inteira sumiria da coleta em silencio.
    """
    ultimo: Exception | None = None
    for i in range(tentativas):
        try:
            return func()
        except Exception as exc:
            ultimo = exc
            if i < tentativas - 1:
                time.sleep(base_espera * (i + 1))
    raise ultimo  # type: ignore[misc]


def situacao_robots() -> str:
    return robots_situacao(BASE + "/", agente=UA)


def _baixar(url: str, timeout: int = 40) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")

    def uma_vez() -> str:
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept-Language": "el,en;q=0.7"})
        with urlopen(req, timeout=timeout) as r:
            bruto = r.read(8_000_000)
            charset = r.headers.get_content_charset()
        texto, usada = _decodificar(bruto, charset)
        _codificacoes_vistas[usada] = _codificacoes_vistas.get(usada, 0) + 1
        return texto

    return _tentar(uma_vez)


# -------------------------------------------------------------------- registro

@dataclass
class Empresa:
    nome: str = ""                 # ΕΠΩΝΥΜΙΑ, razao social (grego)
    nome_latino: str = ""          # ΔΙΑΚΡΙΤΙΚΟΣ ΤΙΤΛΟΣ quando em alfabeto latino
    nome_comercial: str = ""       # ΔΙΑΚΡΙΤΙΚΟΣ ΤΙΤΛΟΣ como publicado
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    cidade: str = ""               # Περιοχή
    descricao: str = ""
    tipo_associacao: str = ""      # ΚΑΤΗΓΟΡΙΑ ΜΕΛΟΥΣ, ja canonizada
    tipo_associacao_fonte: str = ""  # como o SEDEA publicou, sem retoque
    secao_pagina: str = ""         # titulo acima da tabela, para conferencia
    certificacao_pess: str = ""    # Πιστοποίηση ΠΕΣΣ
    representantes: str = ""       # ΕΚΠΡΟΣΩΠΟΙ ΣΤΟ ΣΕΔΕΑ, pessoas
    pessoas: list[str] = field(default_factory=list)
    url_perfil: str = ""
    coletado_em: str = ""
    erro: str = ""


# -------------------------------------------------------------------- tabela

# Mapa por classe column-N do TablePress. Numero de coluna e estavel; o
# texto do cabecalho nao e (ver o epsilon grego em "Ε-mail").
_COLUNAS = {
    "column-1": "nome_comercial",
    "column-2": "nome",
    "column-3": "tipo_associacao",
    "column-4": "certificacao_pess",
    "column-5": "representantes",
    "column-6": "cidade",
    "column-7": "telefone",
    "column-8": "email",
    "column-9": "site",
}
# Cabecalhos esperados, ja normalizados. Servem so para avisar se o SEDEA
# reordenar as colunas um dia; nunca para localizar a coluna.
_CABECALHO_ESPERADO = {
    "column-1": "ΔΙΑΚΡΙΤΙΚΟΣ ΤΙΤΛΟΣ", "column-2": "ΕΠΩΝΥΜΙΑ",
    "column-3": "ΚΑΤΗΓΟΡΙΑ ΜΕΛΟΥΣ", "column-4": "ΠΙΣΤΟΠΟΙΗΣΗ ΠΕΣΣ",
    "column-5": "ΕΚΠΡΟΣΩΠΟΙ ΣΤΟ ΣΕΔΕΑ", "column-6": "ΠΕΡΙΟΧΗ",
    "column-7": "ΤΗΛΕΦΩΝΟ", "column-8": "Ε-MAIL", "column-9": "WEBSITE",
}


def _texto_com_quebras(no) -> str:
    for br in no.find_all("br"):
        br.replace_with("\n")
    return no.get_text()


def _titulo_da_tabela(tabela) -> str:
    """
    Titulo (ΤΑΚΤΙΚΑ / ΣΥΝΔΕΔΕΜΕΝΑ ΜΕΛΗ) que precede a tabela no documento.

    Usado apenas como conferencia contra a coluna ΚΑΤΗΓΟΡΙΑ ΜΕΛΟΥΣ de cada
    linha, que e o dado real.
    """
    for anterior in tabela.find_all_previous(["h1", "h2", "h3", "h4", "h5"]):
        texto = _limpar(anterior.get_text())
        if "ΜΕΛΗ" in texto.upper():
            return texto
    return ""


# Marcador exclusivo para <br>. Nao pode ser "\n": o HTML do SEDEA escreve
# "<br/>\n", entao um unico <br> ja produz duas quebras no texto e contar
# quebras confundiria uma quebra de linha com uma troca de pessoa.
_MARCA_BR = "\x00"
_SEPARA_PESSOA = re.compile(r"\x00\s*\x00")


def _texto_com_marcadores(no) -> str:
    """Texto do bloco com cada <br> substituido por um marcador contavel."""
    copia = BeautifulSoup(str(no), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with(_MARCA_BR)
    return copia.get_text()


def _dividir_pessoas(celula) -> list[str]:
    """
    Nomes de pessoa da coluna ΕΚΠΡΟΣΩΠΟΙ, um por entrada.

    A celula usa os dois numeros de <br> com sentidos diferentes:

      <br><br>   separa uma pessoa da seguinte
      <br>       so quebra a linha DENTRO da mesma pessoa, entre o nome e o
                 cargo ("Πέτρος Ιωαννίδης," / "Πρόεδρος & Διευθύνων Σύμβουλος")

    Quebrar em toda linha transformaria cada cargo solto num "representante"
    e inflaria a contagem de pessoas: as 27 empresas passariam de 63 para
    quase 90 contatos, um terco deles cargos sem dono.

    Nome e cargo ficam juntos de proposito. Separar por virgula erraria nos
    nomes que trazem virgula por outro motivo, e ha linhas em que o cargo
    vem separado por tabulacao, nao por pontuacao nenhuma.
    """
    bruto = _texto_com_marcadores(celula)
    pessoas: list[str] = []
    for bloco in _SEPARA_PESSOA.split(bruto):
        junto = _limpar(bloco.replace(_MARCA_BR, " ")).strip(" ,;|")
        if junto and len(junto) > 2:
            pessoas.append(junto)
    return pessoas


# Maiusculas latinas que sao indistinguiveis das gregas na tela. Uma linha
# da tabela do SEDEA foi digitada com elas: "TAKTIKO Μέλος", em latim, no
# meio de 24 "ΤΑΚΤΙΚΟ Μέλος" em grego. A olho nu sao a mesma palavra; para
# o `groupby` sao duas categorias, e o quadro de associadas passa a mostrar
# uma categoria fantasma com uma empresa dentro.
_HOMOGLIFOS = str.maketrans({
    "A": "Α", "B": "Β", "E": "Ε", "Z": "Ζ", "H": "Η", "I": "Ι", "K": "Κ",
    "M": "Μ", "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "X": "Χ", "Y": "Υ",
})

_CATEGORIAS_CONHECIDAS = {"ΤΑΚΤΙΚΟ", "ΣΥΝΔΕΔΕΜΕΝΟ"}

_homoglifos_corrigidos: list[str] = []


def homoglifos_corrigidos() -> list[str]:
    return list(_homoglifos_corrigidos)


def _canonizar_categoria(bruto: str) -> tuple[str, bool]:
    """
    Devolve (categoria canonica, houve correcao de homoglifo).

    A troca latino->grego so e aplicada ao vocabulario FECHADO da coluna de
    categoria, e so quando a forma original nao e reconhecida e a convertida
    e. Aplicar a mesma troca aos nomes das empresas seria destrutivo:
    "ABACUS", "OPINION POLL" e "MARC AE" sao latinos de verdade e virariam
    grego falso.
    """
    texto = _limpar(bruto)
    if not texto:
        return "", False
    primeira = texto.split()[0].upper()
    if primeira in _CATEGORIAS_CONHECIDAS:
        return texto, False
    convertida = primeira.translate(_HOMOGLIFOS)
    if convertida in _CATEGORIAS_CONHECIDAS:
        resto = texto[len(texto.split()[0]):]
        return convertida + resto, True
    return texto, False


def _sem_acento_grego(texto: str) -> str:
    """
    Maiusculas gregas sem sinal diacritico.

    `str.upper()` em grego preserva o acento ("Πιστοποίηση" vira
    "ΠΙΣΤΟΠΟΊΗΣΗ"), enquanto a ortografia grega o descarta em caixa alta.
    Sem tirar o acento, a conferencia de cabecalho acusaria diferenca em
    toda coluna acentuada e viraria ruido que ninguem le.
    """
    decomposto = unicodedata.normalize("NFD", (texto or "").upper())
    return unicodedata.normalize(
        "NFC", "".join(c for c in decomposto if not unicodedata.combining(c)))


def _normalizar_site(bruto: str) -> str:
    s = _limpar(bruto)
    if not s:
        return ""
    if not s.startswith(("http://", "https://")):
        s = "https://" + s.lstrip("/")
    return s.split("?")[0][:200]


def extrair_tabela(html: str, *, verbose: bool = True) -> list[Empresa]:
    """Uma Empresa por linha das tabelas TablePress da pagina analitica."""
    sopa = BeautifulSoup(html, "html.parser")
    tabelas = sopa.select("table.tablepress")
    if not tabelas:
        raise RuntimeError("nenhuma tabela de associadas na pagina analitica")

    agora = datetime.now(timezone.utc).isoformat()
    empresas: list[Empresa] = []
    for tabela in tabelas:
        secao = _titulo_da_tabela(tabela)

        # Conferencia de layout: se o SEDEA trocar a ordem das colunas, o
        # aviso aparece antes de a base ser contaminada.
        if verbose:
            for th in tabela.select("thead th"):
                classe = next((c for c in th.get("class", [])
                               if c.startswith("column-")), "")
                visto = _sem_acento_grego(_limpar(th.get_text(" ")))
                esperado = _sem_acento_grego(_CABECALHO_ESPERADO.get(classe, ""))
                if esperado and visto and visto != esperado:
                    print(f"      [aviso] {classe}: cabecalho '{visto}' "
                          f"difere do esperado '{esperado}'")

        for tr in tabela.select("tbody tr"):
            reg = Empresa(url_perfil=PAGINA_TABELA, coletado_em=agora,
                          secao_pagina=secao)
            for td in tr.select("td"):
                classe = next((c for c in td.get("class", [])
                               if c.startswith("column-")), "")
                campo = _COLUNAS.get(classe)
                if not campo:
                    continue
                # `representantes` le a celula ANTES de qualquer outra coisa:
                # `_texto_com_quebras` troca os <br> por "\n" na propria
                # arvore, e depois disso nao da mais para contar quantos <br>
                # separavam uma pessoa da seguinte.
                if campo == "representantes":
                    reg.pessoas = _dividir_pessoas(td)
                    reg.representantes = " | ".join(reg.pessoas)
                    continue

                valor = _texto_com_quebras(td)
                if campo == "email":
                    achado = _EMAIL.search(_limpar(valor).lower())
                    if achado and achado.group(0) not in _EMAIL_INSTITUCIONAL:
                        reg.email = achado.group(0)
                elif campo == "site":
                    reg.site = _normalizar_site(valor)
                elif campo == "telefone":
                    tel = _limpar(valor.replace("\n", ", "))
                    if re.sub(r"\D", "", tel) not in _TELEFONE_INSTITUCIONAL:
                        reg.telefone = tel[:80]
                elif campo == "tipo_associacao":
                    reg.tipo_associacao_fonte = _limpar(valor.replace("\n", " "))
                    reg.tipo_associacao, corrigido = _canonizar_categoria(valor)
                    if corrigido:
                        _homoglifos_corrigidos.append(reg.tipo_associacao_fonte)
                else:
                    setattr(reg, campo, _limpar(valor.replace("\n", " "))[:300])

            if not (reg.nome or reg.nome_comercial):
                continue
            # O titulo comercial so vira `nome_latino` se for mesmo latino.
            if _e_latino(reg.nome_comercial):
                reg.nome_latino = reg.nome_comercial
            if not reg.nome:
                reg.nome = reg.nome_comercial
            # Conferencia titulo x coluna. A coluna manda; a divergencia fica
            # registrada em vez de silenciada.
            if secao and reg.tipo_associacao:
                raiz = reg.tipo_associacao.split()[0].upper().rstrip("Ο")
                if raiz and raiz not in secao.upper():
                    reg.erro = (f"categoria '{reg.tipo_associacao}' sob o "
                                f"titulo '{secao}'")
            empresas.append(reg)
    return empresas


# ------------------------------------------------------------------- cartoes

def extrair_cartoes(html: str) -> list[dict]:
    """
    Endereco postal por cartao da pagina /μέλη-σεδεα/.

    Cada cartao e um bloco `div.image_with_text` com <h3> do nome e, em
    seguida, linhas soltas de endereco, telefone, e-mail e site. Nao ha
    marcacao semantica: separamos por conteudo, nao por posicao.
    """
    sopa = BeautifulSoup(html, "html.parser")
    cartoes: list[dict] = []
    for bloco in sopa.select("div.image_with_text"):
        titulo = bloco.find("h3")
        nome = _limpar(titulo.get_text()) if titulo else ""
        # O <h3> tem de sair da arvore ANTES de extrair o texto. O tema nao
        # poe separador entre o titulo e a primeira linha do endereco, entao
        # get_text() devolve "ABACUS RESEARCH S.A.Φειδιππίδου 2" grudado, e
        # filtrar a linha igual ao nome nao pega esse caso.
        if titulo:
            titulo.extract()
        texto = _texto_com_quebras(bloco)
        linhas = [_limpar(x) for x in texto.split("\n")]
        linhas = [x for x in linhas if x and x != nome]

        email = ""
        endereco: list[str] = []
        for linha in linhas:
            achado = _EMAIL.search(linha.lower())
            if achado:
                if not email and achado.group(0) not in _EMAIL_INSTITUCIONAL:
                    email = achado.group(0)
                continue
            if re.match(r"^(T\.|Τ[:.]|F\.|Φ[:.]|Tel|Τηλ|Fax)", linha, re.I):
                continue
            if linha.lower().startswith("www.") or linha.startswith("http"):
                continue
            endereco.append(linha)
        cartoes.append({"nome": nome, "email": email,
                        "endereco": ", ".join(endereco)[:300]})
    return cartoes


def anexar_enderecos(empresas: list[Empresa], cartoes: list[dict], *,
                     verbose: bool = True) -> tuple[int, int]:
    """
    Preenche `endereco` casando pelo e-mail.

    Chave que aponta para mais de um cartao com endereco diferente e
    descartada: preencher com um dos dois seria adivinhar, e um endereco
    errado nao se distingue de um certo depois que entra na base.

    Devolve (casados, chaves_ambiguas_descartadas).
    """
    por_email: dict[str, set[str]] = {}
    for c in cartoes:
        if c["email"] and c["endereco"]:
            por_email.setdefault(c["email"], set()).add(c["endereco"])

    unicos = {k: next(iter(v)) for k, v in por_email.items() if len(v) == 1}
    ambiguos = len(por_email) - len(unicos)

    casados = 0
    for e in empresas:
        if e.email and e.email in unicos:
            e.endereco = unicos[e.email]
            casados += 1
    if verbose and ambiguos:
        print(f"      {ambiguos} e-mail(s) com enderecos divergentes, descartados")
    return casados, ambiguos


def coletar(*, delay: float = PAUSA_PADRAO,
            verbose: bool = True) -> tuple[list[Empresa], dict]:
    """Coleta as duas paginas e devolve (empresas, resumo da conferencia)."""
    if verbose:
        print("      baixando a tabela analitica")
    empresas = extrair_tabela(_baixar(PAGINA_TABELA), verbose=verbose)
    time.sleep(delay)

    if verbose:
        print("      baixando os cartoes de endereco")
    cartoes = extrair_cartoes(_baixar(PAGINA_CARTOES))
    casados, ambiguos = anexar_enderecos(empresas, cartoes, verbose=verbose)

    resumo = {
        "linhas_tabela": len(empresas),
        "cartoes": len(cartoes),
        "cartoes_com_email": sum(1 for c in cartoes if c["email"]),
        "enderecos_casados": casados,
        "chaves_ambiguas": ambiguos,
    }
    return empresas, resumo


COLUNAS = ["nome", "nome_latino", "nome_comercial", "email", "site", "pais",
           "telefone", "endereco", "cidade", "descricao", "tipo_associacao",
           "tipo_associacao_fonte", "secao_pagina", "certificacao_pess",
           "representantes", "url_perfil", "coletado_em", "erro"]


def exportar(empresas: list[Empresa], nome: str = "sedea") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas],
                             ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig: sem BOM o Excel grego le o CSV como cp1253 e transforma
    # todo nome em alfabeto grego numa fileira de simbolos.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
