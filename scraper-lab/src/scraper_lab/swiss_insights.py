"""
Extrator dos Corporate Member da SWISS INSIGHTS (Suica).

DESCOBERTA DE ENDERECO. O alvo pedido foi o vsms / asms (Verband Schweizer
Markt- und Sozialforschung). O dominio vsms-asms.ch nao serve mais de fonte:

    vsms-asms.ch  -> HTTP 200 com 91 bytes, "Wegen Wartungsarbeiten kurzzeitig
                     unerreichbar", pagina cujo Last-Modified e de 2018; o
                     certificado TLS que ele apresenta e o de weblotion.ch, a
                     agencia que hospedava o site.

A associacao se renomeou para SWISS INSIGHTS (Swiss Data Insights Association)
e o diretorio vivo esta em swiss-insights.ch/corporate-member-si/.

CONFORMIDADE. O robots.txt de swiss-insights.ch NAO pode ser lido: o servidor
responde 302 apontando para http://127.0.0.1, e a conexao com esse destino
falha. O verificador do projeto classifica isso como `falhou` (diferente de
`ausente`, que seria um 404 honesto) e segue com a convencao da web de
permitir, avisando uma vez. Registramos a situacao no relatorio justamente
porque falha de leitura NAO e prova de que o acesso e livre.

Duas observacoes sobre esse mesmo defeito de configuracao:

  - Qualquer URL inexistente tambem devolve 302 para 127.0.0.1 em vez de 404.
    Um redirecionamento para localhost e portanto o sinal de "pagina nao
    existe" neste site, e o codigo trata assim.
  - A API REST do WordPress esta atras do mesmo redirecionamento, entao nao da
    para ler o titulo dos anexos por ali. Isso importa para o nome da empresa,
    explicado abaixo.

ARMADILHA PRINCIPAL: O NOME DA EMPRESA NAO E TEXTO. A pagina e um layout
Elementor em que a identificacao de cada membro e a IMAGEM do logotipo, com
`alt` vazio. Nao ha ficha individual. Por isso o nome e resolvido em cascata,
e a origem fica gravada em `nome_origem` para que a etapa de uniao saiba o quanto
confiar em cada linha:

    1. texto        nome escrito no bloco (ex.: "Pulse Partners SàRL",
                    "amrein+heller Marktforschungs Treuhand AG")
    2. portrait     nome do PDF de portrait ("2026-Portrait-Intervista.pdf")
    3. dominio      dominio do site da empresa, sem www e sem TLD
    4. arquivo      nome do arquivo do logotipo, ultimo recurso

O `site` e o `dominio` sao gravados sempre, e sao o casamento confiavel contra
Esomar e Greenbook; o nome derivado serve de rotulo legivel, nao de chave.

OUTRA ARMADILHA: O LINK DO BOTAO "PORTRAIT" APONTA PARA kepanyne.cyon.site, que
e o HOSPEDEIRO do site, nao a empresa. Varrer qualquer link externo do bloco
traria esse dominio como se fosse o site de vinte membros. O site da empresa e
lido so do widget de contato, e links para .pdf sao descartados.
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://swiss-insights.ch"
LISTAGEM = f"{BASE}/corporate-member-si/"

PAIS = "Switzerland"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Sem robots legivel nao ha Crawl-delay declarado. Como o site ja demonstrou
# configuracao fragil, usamos a pausa padrao do projeto e uma unica pagina.
DELAY_PADRAO = 1.5

# Dominios da propria associacao e do hospedeiro dela. cyon.site aparece nos
# botoes de Portrait e nao pertence a nenhuma empresa listada.
_DOMINIO_ASSOCIACAO = ("swiss-insights.ch", "vsms-asms.ch", "weblotion.ch",
                       "cyon.site", "esomar.org", "efamro.eu")

# Imagens que sao selo da associacao, nao logotipo de empresa. Sem esta lista o
# selo "Market and Social Research" viraria o logotipo de 31 dos 39 membros.
_SELOS = {
    "si_msr_label_cmyk_4c.jpg": "Market and Social Research by Swiss Insights",
    "si_df_label_cmyk_4c.jpg": "Data Fairness by Swiss Insights",
    "data-fairness-logo.png": "Data Fairness by Swiss Insights",
    "si_logo_corporate_member_cmyk_4c.jpg": "Corporate Member",
}

_ESPACOS = re.compile(r"[ \t   ]+")
_VAZIOS = {"", "-", "--", "n/a", "na", "/", "&nbsp;"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_TEXTO = re.compile(r"(?<![@\w.])((?:https?://|www\.)?[A-Za-z0-9-]+"
                        r"(?:\.[A-Za-z0-9-]+)+(?:/\S*)?)")
# NPA suico: quatro digitos. Aparece na mesma linha da cidade ("6010 Kriens")
# ou sozinho numa linha, com a cidade na seguinte (NielsenIQ, DemoSCOPE).
_NPA_CIDADE = re.compile(r"^(\d{4})[,\s]+(.+)$")
_SO_NPA = re.compile(r"^(\d{4})$")
# Sufixo de logradouro em alemao e frances, para separar rua de nome de empresa.
_LOGRADOURO = re.compile(
    r"(stra(ss|ß)e|str\.|weg|platz|allee|ring|damm|gasse|ufer|hof|"
    r"rue|chemin|avenue|route|pont|quai|technopark|\bch\.\b|\d)", re.I)
_PROTOCOLO = re.compile(r"^https?://", re.I)

# Ruido comum em nome de arquivo de logotipo: nada disso e nome de empresa.
_RUIDO_ARQUIVO = re.compile(
    r"^(logo|logos|si|sponsor|rgb|cmyk|web|primary|positiv|negativ|quer|klein|"
    r"gross|full|master|dpi|px|v\d+|\d+|\d+x\d+|horizontal|vertical|color|"
    r"colour|navy|red|blue|bright|lettering|pos|\dv|part|of)$", re.I)


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", (texto or "").replace("​", "").replace("­", ""))
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    # NFC para que "ü" composto e decomposto nao virem duas empresas na hora de
    # cruzar com Esomar e Greenbook.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


def _decodificar(bruto: bytes, ctype: str) -> tuple[str, str]:
    """
    Cabecalho HTTP, depois meta charset, depois utf-8 e latin-1.

    Motivo: a pagina mistura alemao e frances ("Zürich", "Kägiswil",
    "Le Lignon, Genève", "SàRL", "Bessières"). Ler UTF-8 como latin-1 nao
    levanta erro, so troca o caractere, e a cidade corrompida vai calada para o
    CSV.
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


_ESPERA_RETENTATIVA = (0, 3, 8, 15)

CODIFICACAO_DETECTADA = ""


def _baixar(url: str, *, timeout: int = 45) -> str:
    global CODIFICACAO_DETECTADA
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    cabecalhos = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-CH,de;q=0.9,fr;q=0.7,en;q=0.5",
    }
    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, headers=cabecalhos), timeout=timeout) as r:
                # Redirecionamento para localhost e o "404" deste site.
                if urlparse(r.url).hostname in ("127.0.0.1", "localhost"):
                    raise HTTPError(url, 404, "redirecionado para localhost: pagina inexistente",
                                    r.headers, None)
                texto, codec = _decodificar(r.read(8_000_000),
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
class Membro:
    url_perfil: str
    nome: str = ""
    nome_origem: str = ""       # texto / portrait / dominio / arquivo
    email: str = ""
    site: str = ""
    dominio: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    npa: str = ""
    cidade: str = ""
    descricao: str = ""
    tipo_membro: str = "Corporate Member"
    fornecedor_pesquisa: str = "indefinido"
    selos: str = ""             # rotulos de qualidade da SWISS INSIGHTS
    portrait_pdf: str = ""
    publicacoes: str = ""       # artigos do membro nas Swiss Insights News
    logo: str = ""
    coletado_em: str = ""
    erro: str = ""
    emails_extras: list[str] = field(default_factory=list)


def _proprio_da_associacao(url: str) -> bool:
    return any(d in (url or "").lower() for d in _DOMINIO_ASSOCIACAO)


def _linhas(no) -> list[str]:
    """
    Linhas de um widget, respeitando <br>.

    Separador vazio no get_text de proposito: com "\\n" o parser quebraria
    tambem entre <a> irmaos, e "www.x.ch" e "info@x.ch" que moram no mesmo
    paragrafo virariam linhas ja separadas do resto do endereco.
    """
    if no is None:
        return []
    copia = BeautifulSoup(str(no), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    for tag in copia.find_all(["p", "div", "li"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    return [l for l in (_limpar(x) for x in copia.get_text("").split("\n")) if l]


def _arquivo(img) -> str:
    src = (img.get("data-lazy-src") or img.get("src") or "")
    return src.split("?")[0].split("/")[-1]


def _nome_de_arquivo(arquivo: str) -> str:
    """
    Extrai um nome plausivel do nome de arquivo do logotipo.

    Ultimo recurso da cascata: os arquivos misturam nome de empresa com jargao
    de arte-final ("Polyquest_RGB_100X100_Textergaenzt", "NIQ-logo-bright-blue-web").
    Tokens de ruido saem, o resto vira o nome com a grafia original preservada,
    porque "DemoSCOPE" e "NielsenIQ" perderiam identidade se fossem
    normalizados.
    """
    base = re.sub(r"\.[a-z0-9]{2,4}$", "", arquivo, flags=re.I)
    tokens = [t for t in re.split(r"[-_.\s]+", base) if t]
    uteis = [t for t in tokens if not _RUIDO_ARQUIVO.match(t)]
    return _limpar(" ".join(uteis))[:60]


def _nome_de_portrait(href: str) -> str:
    """Nome do PDF de portrait: "2026-Portrait-Constant-Dialog.pdf" -> "Constant Dialog"."""
    base = re.sub(r"\.pdf$", "", href.split("?")[0].split("/")[-1], flags=re.I)
    base = re.sub(r"^\d{4}[-_]*", "", base)
    base = re.sub(r"portrait", "", base, flags=re.I)
    # Sufixo de versao do arquivo: "-1", "-V2", "-2025". Sem isso a DemoSCOPE
    # entrava na base como "Demo Scope 1".
    base = re.sub(r"[-_]+(?:v\d+|\d{1,4})$", "", base, flags=re.I)
    return _limpar(re.sub(r"[-_]+", " ", base).strip(" -_"))[:60]


def _nome_de_dominio(site: str) -> str:
    """Dominio sem www e sem TLD: "https://www.mistrend.ch/" -> "mistrend"."""
    host = urlparse(site if _PROTOCOLO.match(site) else "https://" + site).netloc
    host = re.sub(r"^www\.", "", host, flags=re.I)
    partes = host.split(".")
    return partes[0] if partes else ""


def _dominio_de(site: str) -> str:
    host = urlparse(site if _PROTOCOLO.match(site) else "https://" + site).netloc
    return re.sub(r"^www\.", "", host, flags=re.I).lower()


def _aplicar_endereco(reg: Membro, linhas: list[str]) -> None:
    """
    Distribui as linhas do bloco de endereco.

    O NPA aparece de duas formas: junto da cidade ("6010 Kriens") ou sozinho
    numa linha, com a cidade na linha seguinte (NielsenIQ, DemoSCOPE). Tratar
    so o primeiro caso deixaria essas fichas sem cidade nenhuma.
    """
    logradouro: list[str] = []
    esperando_cidade = False
    for linha in linhas:
        if esperando_cidade:
            reg.cidade = linha
            esperando_cidade = False
            continue
        if _SO_NPA.match(linha):
            reg.npa = linha
            esperando_cidade = True
            continue
        m = _NPA_CIDADE.match(linha)
        if m and not reg.npa:
            reg.npa, reg.cidade = m.group(1), _limpar(m.group(2))
            continue
        logradouro.append(linha)
    reg.endereco = ", ".join(dict.fromkeys(logradouro))[:300]


def _nome_explicito(linhas: list[str]) -> tuple[str, list[str]]:
    """
    Separa o nome escrito da primeira linha do bloco de endereco.

    Alguns membros nao tem logotipo e o site escreve o nome como primeira linha
    do endereco ("Pulse Partners SàRL", "Post Advertising", "swiss made
    software GmbH"). A linha so e tratada como nome quando NAO parece
    logradouro: sem numero, sem sufixo de rua em alemao ou frances e sem NPA.
    """
    if not linhas:
        return "", linhas
    primeira = linhas[0]
    if _SO_NPA.match(primeira) or _NPA_CIDADE.match(primeira):
        return "", linhas
    if _LOGRADOURO.search(primeira):
        return "", linhas
    return primeira, linhas[1:]


# Dominio escrito como texto puro, sem virar link. A Swiss Data Alliance
# publica so "www.swissdataalliance.ch" desse jeito; exigir <a> a excluia da
# coleta em silencio, e ela e membro como qualquer outro.
_DOMINIO_TEXTO = re.compile(
    r"\b(?:www\.[a-z0-9-]+\.[a-z]{2,}"
    r"|[a-z0-9-]+\.(?:ch|swiss|com|io|org|net|eu|de|at|fr|be|nl))\b", re.I)


def _e_bloco_de_membro(secao) -> bool:
    """
    Diz se uma secao Elementor e a de um membro.

    Sao DUAS condicoes ao mesmo tempo: um canal de contato (e-mail, link de
    site ou dominio escrito como texto) e um endereco com NPA suico. Exigir as
    duas e o que separa o membro dos blocos institucionais da pagina, que
    tambem citam e-mail da associacao e links de tarifa.
    """
    tem_contato = False
    tem_npa = False
    for widget in secao.select('.elementor-widget[data-widget_type^="text-editor"]'):
        texto = widget.get_text(" ", strip=True)
        if _EMAIL.search(texto):
            tem_contato = True
        elif any(not _proprio_da_associacao(a["href"])
                 for a in widget.select('a[href^="http"]')):
            tem_contato = True
        else:
            achado = _DOMINIO_TEXTO.search(texto)
            if achado and not _proprio_da_associacao(achado.group(0)):
                tem_contato = True
        for linha in _linhas(widget):
            if _SO_NPA.match(linha) or _NPA_CIDADE.match(linha):
                tem_npa = True
                break
    return tem_contato and tem_npa


def extrair_membro(secao) -> Membro:
    reg = Membro(url_perfil=LISTAGEM,
                 coletado_em=datetime.now(timezone.utc).isoformat())

    # Selos e logotipo. Selos sao imagens compartilhadas por varios membros; o
    # que sobra e o logotipo da empresa.
    selos: list[str] = []
    for img in secao.select("img"):
        arquivo = _arquivo(img)
        if arquivo in _SELOS:
            selos.append(_SELOS[arquivo])
        elif not reg.logo and arquivo:
            reg.logo = (img.get("data-lazy-src") or img.get("src") or "").strip()
    reg.selos = " | ".join(dict.fromkeys(selos))

    # A SWISS INSIGHTS nao rotula membro como fornecedor ou cliente. O unico
    # sinal declarado pela propria associacao e o selo "Market and Social
    # Research", que ela so concede a quem PRESTA servico de pesquisa sob as
    # diretrizes dela. Quem nao tem o selo fica "indefinido": a SBB e a
    # Swisscom obviamente compram pesquisa em vez de vender, mas essa e leitura
    # nossa, e leitura nossa nao vira dado.
    if any("Market and Social Research" in s for s in selos):
        reg.fornecedor_pesquisa = "sim"

    for a in secao.select('a.elementor-button[href]'):
        if a["href"].lower().endswith(".pdf"):
            reg.portrait_pdf = a["href"].strip()
            break

    # Widgets de texto: o que tem link de contato e o bloco de canais; o que
    # vem antes dele e o endereco.
    widgets = secao.select('.elementor-widget[data-widget_type^="text-editor"]')
    contato = None
    for w in widgets:
        texto = w.get_text(" ", strip=True)
        tem_link = any(not _proprio_da_associacao(a["href"])
                       for a in w.select('a[href^="http"]'))
        achado = _DOMINIO_TEXTO.search(texto)
        # O widget de canais pode trazer o dominio como texto puro; exigir <a>
        # deixava a Swiss Data Alliance sem site e sem bloco de contato.
        tem_texto = bool(achado) and not _proprio_da_associacao(achado.group(0))
        if _EMAIL.search(texto) or tem_link or tem_texto:
            contato = w
            break

    endereco_widget = None
    for w in widgets:
        if w is contato:
            break
        endereco_widget = w

    if contato is not None:
        emails: list[str] = []
        for a in contato.select('a[href^="mailto:"]'):
            valor = _limpar(a["href"][7:].split("?")[0]).lower()
            if valor and not _proprio_da_associacao(valor) and valor not in emails:
                emails.append(valor)
        for valor in _EMAIL.findall(contato.get_text(" ", strip=True)):
            valor = valor.lower()
            if not _proprio_da_associacao(valor) and valor not in emails:
                emails.append(valor)
        if emails:
            reg.email, reg.emails_extras = emails[0], emails[1:4]

        # Site: so links do widget de contato, e nunca .pdf, que e o portrait
        # hospedado em dominio de terceiro.
        for a in contato.select('a[href^="http"]'):
            href = a["href"].strip()
            if href.lower().endswith(".pdf") or _proprio_da_associacao(href):
                continue
            reg.site = href
            break
        if not reg.site:
            # Alguns membros digitam o endereco sem virar link ("outlierlab.io").
            for linha in _linhas(contato):
                if _EMAIL.search(linha):
                    continue
                m = _URL_TEXTO.search(linha)
                if m and not _proprio_da_associacao(m.group(1)):
                    reg.site = m.group(1)
                    break

    linhas = _linhas(endereco_widget)
    nome_texto, linhas = _nome_explicito(linhas)
    _aplicar_endereco(reg, linhas)

    if reg.site:
        if not _PROTOCOLO.match(reg.site):
            reg.site = "https://" + reg.site.lstrip("/")
        reg.dominio = _dominio_de(reg.site)

    # Cascata do nome, da fonte mais confiavel para a menos confiavel.
    if nome_texto:
        reg.nome, reg.nome_origem = nome_texto, "texto"
    elif reg.portrait_pdf and _nome_de_portrait(reg.portrait_pdf):
        reg.nome, reg.nome_origem = _nome_de_portrait(reg.portrait_pdf), "portrait"
    elif reg.site and _nome_de_dominio(reg.site):
        reg.nome, reg.nome_origem = _nome_de_dominio(reg.site), "dominio"
    elif reg.logo and _nome_de_arquivo(_arquivo_de_url(reg.logo)):
        reg.nome, reg.nome_origem = _nome_de_arquivo(_arquivo_de_url(reg.logo)), "arquivo"

    noticias = []
    for coluna in secao.select(".elementor-column"):
        texto = coluna.get_text(" ", strip=True)
        if "Swiss Insights News" in texto:
            noticias += [t for li in _linhas(coluna)
                         if (t := li) and "Swiss Insights News" not in t]
    reg.publicacoes = " | ".join(dict.fromkeys(noticias))[:400]

    if not reg.nome:
        reg.erro = "sem nome recuperavel (bloco sem texto, portrait, site nem logo)"
    return reg


def _arquivo_de_url(url: str) -> str:
    return url.split("?")[0].split("/")[-1]


def coletar(*, verbose: bool = True) -> tuple[list[Membro], str]:
    """
    Le a pagina de Corporate Member inteira.

    Uma unica requisicao: a pagina nao pagina, nao rola e nao tem ficha
    individual. A contagem e feita sobre blocos UNICOS de membro, checando o
    site como chave, para que um bloco repetido no layout nao vire dois
    registros.

    A SWISS INSIGHTS nao publica o total de membros nesta pagina, entao nao ha
    numero declarado para conferir. Isso e registrado no relatorio como
    ausencia de conferencia, nao como conferencia bem sucedida.
    """
    sit = robots_situacao(LISTAGEM, agente=UA)
    if verbose:
        print(f"      robots.txt: {sit}"
              f"{'  (302 para 127.0.0.1: nao ha como ler as regras)' if sit == 'falhou' else ''}")

    sopa = BeautifulSoup(_baixar(LISTAGEM), "html.parser")
    for t in sopa(["script", "style", "noscript"]):
        t.decompose()

    membros: list[Membro] = []
    vistos: set[str] = set()
    for secao in sopa.select("section.elementor-top-section"):
        if not _e_bloco_de_membro(secao):
            continue
        reg = extrair_membro(secao)
        chave = (reg.dominio or reg.nome or reg.email).lower()
        if chave and chave in vistos:
            continue
        if chave:
            vistos.add(chave)
        membros.append(reg)
        if verbose:
            print(f"  [{len(membros):>3}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:26]:26} | {reg.nome_origem:8} | "
                  f"{reg.email[:30]:30} | {reg.cidade[:14]}")
    return membros, sit


COLUNAS = ["nome", "nome_origem", "email", "emails_extras", "site", "dominio", "pais",
           "telefone", "endereco", "npa", "cidade", "tipo_membro",
           "fornecedor_pesquisa", "selos", "publicacoes", "portrait_pdf",
           "descricao", "logo", "url_perfil", "erro"]


def exportar(membros: list[Membro], nome: str = "swiss_insights") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(m) for m in membros], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig porque o Excel em maquina suica abre utf-8 sem BOM como latin-1
    # e transforma "Zürich" e "Genève" em lixo.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for m in membros:
            d = asdict(m)
            d["emails_extras"] = " | ".join(d.get("emails_extras") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
