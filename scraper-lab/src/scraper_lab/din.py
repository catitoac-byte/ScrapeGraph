"""
Extrator do Ledenoverzicht do Data & Insights Network (Holanda).

DESCOBERTA DE ENDERECO. O alvo pedido foi a MOA (Center for Information Based
Decision Making). A MOA nao existe mais com esse nome: em fevereiro de 2023 ela
se renomeou para Data & Insights Network. Os dominios antigos confirmam o
abandono, e por isso nao servem de fonte:

    moaweb.nl e moa.nl  -> respondem HTTP 200 com a pagina padrao do Apache2
                           ("Apache2 Ubuntu Default Page"), e o certificado TLS
                           que apresentam e o de dailydatabytes.nl, ou seja o
                           dominio virou apontamento residual de outro site.

O diretorio vivo esta em datainsightsnetwork.nl/dutch-researchers/.

CONFORMIDADE. O robots.txt do site e lido normalmente e proibe /wp-admin/,
tres pastas do WooCommerce e as URLs com `?add-to-cart=`. Duas consequencias
praticas:

  1. A ficha detalhada de cada empresa vem de wp-admin/admin-ajax.php, que o
     proprio robots libera com um `Allow:` mais especifico que o `Disallow:
     /wp-admin/`. Quem casa por prefixo literal (urllib.robotparser) bloqueia
     essa URL por engano; o verificador do projeto aplica a regra mais longa e
     devolve permitido para o admin-ajax.php e proibido para /wp-admin/.
  2. Nenhuma outra URL tocada aqui cai nas regras, e mesmo assim toda
     requisicao passa por `permitido()` antes de sair.

O robots nao declara Crawl-delay, entao vale a pausa padrao do projeto.

ARMADILHAS DESTA FONTE:

  a) A lista distingue Agency, Company e Supplier. "Company" e departamento de
     marketing/insights de quem COMPRA pesquisa (a.s.r., ABN AMRO, A.S. Watson),
     nao fornecedor. A distincao vem da propria fonte e e preservada na coluna
     `tipo_membro`; nao cabe a este extrator decidir quem entra na base final.

  b) O site guarda texto com codificacao dupla no proprio banco. A ficha da
     ZorgfocuZ traz os bytes C3 83 C2 A9 onde deveria haver "e" acentuado, ou
     seja UTF-8 lido como cp1252 e gravado de novo em UTF-8; seis fichas trazem
     tambem as aspas e apostrofes tortos da mesma origem. Decodificar certo nao
     resolve, porque o defeito ja esta no banco do site: e preciso desfazer a
     volta extra. `_reparar_mojibake` faz isso, trecho a trecho, e so quando a
     conversao fecha sem erro.

  c) Nao ha e-mail em lugar nenhum do diretorio, nem no cartao nem na ficha. O
     que a fonte da de novo em relacao as bases globais e cobertura (306
     empresas contra 86 holandesas ja existentes), telefone, endereco, porte em
     FTE, certificacoes e descricao.
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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://datainsightsnetwork.nl"
LISTAGEM = f"{BASE}/dutch-researchers/"
AJAX = f"{BASE}/wp-admin/admin-ajax.php"

PAIS = "Netherlands"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Sem Crawl-delay declarado no robots, vale a pausa padrao do projeto.
DELAY_PADRAO = 1.5

# Contatos da propria associacao, presentes no rodape de toda pagina. A
# extracao ja e restrita ao cartao e a ficha, mas o filtro fica como rede de
# seguranca contra mudanca de template.
_DOMINIO_ASSOCIACAO = ("datainsightsnetwork.nl", "moaweb.nl", "moa.nl",
                       "dailydatabytes.nl", "cloutoday.nl")

_ESPACOS = re.compile(r"[ \t   ]+")
_VAZIOS = {"", "-", "--", "n/a", "na", "nvt", "n.v.t.", "onbekend", "/"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# CEP holandes: quatro digitos e duas letras, com ou sem espaco ("1705 NG",
# "9728NP"), seguido da cidade. O separador opcional e obrigatorio de tratar:
# metade das fichas digita colado.
_CEP_CIDADE = re.compile(r"^(\d{4})\s*([A-Za-z]{2})\s+(.+)$")

# Telefone holandes na linha solta do cartao: comeca com 0 ou +31, e o resto e
# digito, espaco, hifen ou parentese. Exigir 8 digitos evita capturar um numero
# de porta ou um ano perdido no endereco.
_TELEFONE = re.compile(r"^\+?[\d][\d\s().+-]{7,}$")

_PROTOCOLO = re.compile(r"^https?://", re.I)


def _limpar(texto: str | None) -> str:
    """Normaliza espacos e acentuacao; devolve vazio para placeholder."""
    t = _ESPACOS.sub(" ", (texto or "").replace("​", "").replace("­", ""))
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    # NFC para que "e" com acento composto e decomposto nao virem duas empresas
    # diferentes na hora de deduplicar contra Esomar e Greenbook.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


_SUSPEITA_MOJIBAKE = re.compile(r"Ã[\x80-\xbfŒœŠšŸŽž"
                                r"ƒˆ˜–—‘-„†-•"
                                r"…‰‹›€™]"
                                r"|Â[\x80-\xbf]|â€|Ã¯Â¿Â½")

def _para_bytes(t: str) -> bytes:
    """
    Refaz os bytes que o site leu errado.

    cp1252 nao define os codigos 0x80 a 0x9F, mas o texto do site tem exatamente
    esses caracteres quando a aspa curva foi mal lida (a sequencia "\u00e2\u20ac\u009d"
    termina em U+009D). Sem deixar esses codigos passarem por latin-1, o trecho
    inteiro era considerado nao conversivel e a aspa quebrada ficava no CSV.
    """
    saida = bytearray()
    for c in t:
        try:
            saida += c.encode("cp1252")
        except UnicodeEncodeError:
            if "\x80" <= c <= "\x9f":
                saida += c.encode("latin-1")
            else:
                raise
    return bytes(saida)


def _conversivel(c: str) -> bool:
    try:
        _para_bytes(c)
        return True
    except UnicodeEncodeError:
        return False


def _reparar_trecho(t: str) -> str:
    """Desfaz uma volta de codificacao, ou devolve o trecho intacto."""
    for gerar in (_para_bytes, lambda s: s.encode("latin-1")):
        try:
            corrigido = gerar(t).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        # Sobrando marca, houve tripla codificacao; a volta a mais so e feita
        # quando ela tambem fecha.
        if _SUSPEITA_MOJIBAKE.search(corrigido):
            try:
                corrigido = _para_bytes(corrigido).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return corrigido
    return t


# Sequencia isolada de mojibake, usada quando o trecho inteiro nao converte.
_SEQ_MOJIBAKE = re.compile(r"[\u00c2\u00c3\u00e2][\u0080-\uffff]{1,3}")


def _reparar_mojibake(t: str) -> str:
    """
    Desfaz codificacao dupla gravada na origem.

    O site guarda parte dos textos com o UTF-8 ja lido como cp1252 e regravado
    em UTF-8; nesse caso chegam os bytes C3 83 C2 A9 no lugar de C3 A9, e a
    decodificacao correta produz "\u00c3\u00a9" onde deveria haver "e" acentuado.
    Nao adianta escolher outro codec na leitura: a volta extra esta no banco do
    site, nao no transporte.

    cp1252 vem antes de latin-1 porque "\u00e2\u20ac\u2122" so existe nele: os bytes E2 80 99
    viram "\u00e2", "\u20ac" e "\u2122" em cp1252, enquanto em latin-1 o 0x80 seria um
    caractere de controle invisivel. So com latin-1 todas as aspas e apostrofes
    tortos das descricoes ficavam sem conserto.

    O conserto e feito por TRECHO, nao na frase inteira, porque a frase mistura
    parte gravada com codificacao dupla e parte gravada certa, com caracteres
    que nao existem em cp1252. Converter tudo de uma vez levantava
    UnicodeEncodeError por causa desses caracteres e a funcao devolvia o texto
    sem consertar nada. Quando nem o trecho converte, ainda se tenta cada
    sequencia isolada.

    Uma conversao so e aceita quando a ida e volta fecha sem erro, o que impede
    que um "\u00c2" ou um "\u00c3" legitimo do nome de uma empresa seja estragado.
    """
    if not t or not _SUSPEITA_MOJIBAKE.search(t):
        return t

    saida: list[str] = []
    bloco: list[str] = []
    atual_conversivel: bool | None = None
    for c in t:
        conv = _conversivel(c)
        if atual_conversivel is None:
            atual_conversivel = conv
        elif conv != atual_conversivel:
            trecho = "".join(bloco)
            saida.append(_reparar_trecho(trecho) if atual_conversivel else trecho)
            bloco, atual_conversivel = [], conv
        bloco.append(c)
    trecho = "".join(bloco)
    saida.append(_reparar_trecho(trecho) if atual_conversivel else trecho)
    resultado = "".join(saida)

    # Trecho longo e misto nao converte inteiro; ai vale tentar sequencia por
    # sequencia, que e curta e converte sozinha.
    if _SUSPEITA_MOJIBAKE.search(resultado):
        resultado = _SEQ_MOJIBAKE.sub(lambda m: _reparar_trecho(m.group(0)), resultado)
    return resultado


def _texto(no) -> str:
    return _reparar_mojibake(_limpar(no.get_text(" ", strip=True) if no else ""))


def _decodificar(bruto: bytes, ctype: str) -> tuple[str, str]:
    """
    Escolhe a codificacao pelo cabecalho, depois pela meta tag, e so entao
    tenta utf-8 e latin-1. Devolve (texto, codec usado).

    Motivo: nomes holandeses usam trema e ligadura ("Bureau Fris", "Ruigrok",
    nomes com ij e com e-trema). Ler UTF-8 como latin-1 nao levanta excecao
    nenhuma, so troca o caractere, e o erro so aparece no CSV final.
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


# Espera crescente entre tentativas. Timeout e 403 esporadico sao recusa de
# momento, nao ausencia de dado; parar na primeira falha perderia empresa em
# silencio.
_ESPERA_RETENTATIVA = (0, 3, 8, 15)

# Ultima codificacao detectada, para o relatorio de coleta.
CODIFICACAO_DETECTADA = ""


def _baixar(url: str, *, dados: bytes | None = None, timeout: int = 45) -> str:
    """Requisicao unica do modulo. Toda URL passa pelo verificador de robots."""
    global CODIFICACAO_DETECTADA
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")

    cabecalhos = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.6",
    }
    if dados is not None:
        cabecalhos["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        cabecalhos["X-Requested-With"] = "XMLHttpRequest"
        cabecalhos["Referer"] = LISTAGEM

    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, data=dados, headers=cabecalhos), timeout=timeout) as r:
                texto, codec = _decodificar(r.read(8_000_000),
                                            r.headers.get("Content-Type", ""))
                CODIFICACAO_DETECTADA = codec
                return texto
        except HTTPError as exc:
            ultimo = exc
            if exc.code in (404, 410):   # ausencia real, insistir nao ajuda
                break
        except (URLError, TimeoutError, OSError) as exc:
            ultimo = exc
    raise ultimo if ultimo else RuntimeError("falha desconhecida")


@dataclass
class Membro:
    url_perfil: str
    id_fonte: str = ""
    nome: str = ""
    email: str = ""            # a fonte nao publica e-mail; fica vazio de proposito
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    cep: str = ""
    cidade: str = ""
    descricao: str = ""
    tipo_membro: str = ""      # Agency / Company / Supplier, como a fonte declara
    fornecedor_pesquisa: str = ""   # sim / nao / indefinido, derivado do tipo
    funcionarios: str = ""     # FTE declarado na ficha
    certificacoes: str = ""
    logo: str = ""
    coletado_em: str = ""
    erro: str = ""
    listas_extras: dict[str, str] = field(default_factory=dict)


# A fonte separa fornecedor de comprador de pesquisa. Traduzimos o rotulo dela
# em uma coluna auxiliar, sem descartar ninguem: quem decide o corte e a etapa
# de uniao, que enxerga a base inteira.
_FORNECEDOR = {"agency": "sim", "supplier": "sim", "company": "nao"}


def _absoluto(url: str) -> str:
    """Completa endereco de site digitado sem protocolo ("www.x.nl")."""
    url = (url or "").strip()
    if not url:
        return ""
    return url if _PROTOCOLO.match(url) else "https://" + url.lstrip("/")


def _proprio_da_associacao(url: str) -> bool:
    alvo = (url or "").lower()
    return any(d in alvo for d in _DOMINIO_ASSOCIACAO)


def _linhas(no) -> list[str]:
    """Texto de um no com <br> virando quebra de linha."""
    if no is None:
        return []
    copia = BeautifulSoup(str(no), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    return [l for l in (_limpar(x) for x in copia.get_text("\n").split("\n")) if l]


def _aplicar_endereco(reg: Membro, linhas: list[str]) -> None:
    """
    Distribui as linhas do bloco de endereco entre logradouro, CEP, cidade e
    telefone.

    A ordem das linhas nao e garantida (ha fichas sem telefone, outras com duas
    linhas de logradouro), entao cada linha e classificada pelo formato, nunca
    pela posicao.
    """
    logradouro: list[str] = []
    for linha in linhas:
        m = _CEP_CIDADE.match(linha)
        if m:
            reg.cep = f"{m.group(1)} {m.group(2).upper()}"
            reg.cidade = _limpar(m.group(3))
            continue
        if not reg.telefone and _TELEFONE.match(linha) and sum(c.isdigit() for c in linha) >= 8:
            reg.telefone = linha
            continue
        logradouro.append(linha)
    reg.endereco = ", ".join(dict.fromkeys(logradouro))[:300]


def extrair_cartao(cartao) -> Membro:
    """Le um `article.dutch-researcher-tile` da listagem."""
    reg = Membro(url_perfil=LISTAGEM,
                 id_fonte=(cartao.get("data-id") or "").strip(),
                 coletado_em=datetime.now(timezone.utc).isoformat())
    reg.nome = _texto(cartao.find("h2"))
    reg.tipo_membro = _texto(cartao.select_one(".dutch-researcher-tile-type"))
    reg.fornecedor_pesquisa = _FORNECEDOR.get(reg.tipo_membro.lower(), "indefinido")

    _aplicar_endereco(reg, _linhas(cartao.select_one(".dutch-researcher-tile-address")))

    site = _texto(cartao.select_one(".dutch-researcher-tile-website"))
    if site and not _proprio_da_associacao(site):
        reg.site = _absoluto(site)

    img = cartao.select_one(".dutch-researcher-tile-logo img")
    if img is not None:
        reg.logo = (img.get("src") or "").strip()

    if not reg.nome:
        reg.erro = "cartao sem nome"
    return reg


@dataclass
class Listagem:
    membros: list[Membro]
    nonce: str
    total_declarado: int | None
    situacao_robots: str


_CONTAGEM = re.compile(r"(\d+)\s*</span>\s*bedrijven", re.I)


def listar_membros(*, verbose: bool = True) -> Listagem:
    """
    Le a pagina do Ledenoverzicht inteira.

    A pagina nao pagina nem rola: os 306 cartoes vem no HTML de uma vez, e o
    proprio site imprime o total ("306 bedrijven gevonden") logo acima da
    grade. A conferencia contra esse numero e obrigatoria, porque um filtro
    aplicado por engano ou um template alterado apareceriam como divergencia em
    vez de passarem como coleta completa.

    A contagem e feita sobre `data-id` UNICO, nao sobre elementos do DOM: cada
    cartao tem logo, titulo e botao, e contar nos levaria a um numero inflado.
    """
    sit = robots_situacao(LISTAGEM, agente=UA)
    html = _baixar(LISTAGEM)
    sopa = BeautifulSoup(html, "html.parser")

    vistos: set[str] = set()
    membros: list[Membro] = []
    for cartao in sopa.select("article.dutch-researcher-tile"):
        reg = extrair_cartao(cartao)
        # Chave de unicidade: id da fonte quando existe, senao nome mais cidade.
        chave = reg.id_fonte or f"{reg.nome}|{reg.cidade}".lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        membros.append(reg)

    m = _CONTAGEM.search(html)
    total = int(m.group(1)) if m else None

    # O nonce e de sessao e expira; e lido a cada execucao, junto da listagem,
    # nunca fixado no codigo.
    m = re.search(r'"ajax_nonce"\s*:\s*"([A-Za-z0-9]+)"', html)
    nonce = m.group(1) if m else ""

    if verbose:
        print(f"      robots.txt: {sit}")
        print(f"      {len(membros)} empresas unicas na grade")
        if total is not None:
            print(f"      site declara {total} bedrijven"
                  f"{'  (confere)' if total == len(membros) else '  <-- DIVERGENCIA'}")
        print(f"      nonce da ficha: {'obtido' if nonce else 'AUSENTE, fichas serao puladas'}")

    return Listagem(membros=membros, nonce=nonce, total_declarado=total,
                    situacao_robots=sit)


def _enriquecer_com_ficha(reg: Membro, html: str) -> None:
    """
    Completa o registro com o que so existe na ficha detalhada.

    A ficha nao repete tudo: ela acrescenta porte em FTE, texto de apresentacao
    e certificacoes. Campos que ja vieram do cartao nao sao sobrescritos, para
    que uma ficha truncada nunca apague dado bom.
    """
    sopa = BeautifulSoup(html, "html.parser")

    titulo = _texto(sopa.select_one(".dr-popup-logo-title h2"))
    if titulo and not reg.nome:
        reg.nome = titulo

    for div in sopa.select(".popup-inline-data > div"):
        valor = _texto(div)
        if not valor:
            continue
        if re.fullmatch(r"[\d.,]+\s*FTE", valor, re.I):
            reg.funcionarios = valor
        elif not reg.tipo_membro:
            reg.tipo_membro = valor
            reg.fornecedor_pesquisa = _FORNECEDOR.get(valor.lower(), "indefinido")

    for coluna in sopa.select(".dr-popup-information-column"):
        # O site da empresa e o unico link http do bloco; buscar qualquer link
        # externo da pagina traria CDN, hospedagem e redes sociais.
        for a in coluna.select('a[href^="http"]'):
            href = a["href"].strip()
            if not reg.site and not _proprio_da_associacao(href):
                reg.site = href
        linhas = [l for l in _linhas(coluna) if not _EMAIL.fullmatch(l)]
        # A coluna com link ja teve o site lido; o resto dela e telefone.
        _aplicar_endereco_complementar(reg, linhas)

    texto = _texto(sopa.select_one(".popup-text"))
    if texto:
        reg.descricao = texto[:1200]

    certificacoes: list[str] = []
    for lista in sopa.select(".popup-check-list"):
        rotulo = _texto(lista.find(["h3", "h4"]))
        itens = [i for li in lista.select("li") if (i := _texto(li))]
        if not itens:
            continue
        chave = rotulo or "outros"
        reg.listas_extras[chave] = " | ".join(dict.fromkeys(itens))
        if re.search(r"certific", chave, re.I):
            certificacoes += itens
    if certificacoes:
        reg.certificacoes = " | ".join(dict.fromkeys(certificacoes))


def _aplicar_endereco_complementar(reg: Membro, linhas: list[str]) -> None:
    """Preenche apenas o que o cartao nao trouxe."""
    for linha in linhas:
        m = _CEP_CIDADE.match(linha)
        if m and not reg.cep:
            reg.cep = f"{m.group(1)} {m.group(2).upper()}"
            reg.cidade = reg.cidade or _limpar(m.group(3))
            continue
        if m:
            continue
        if not reg.telefone and _TELEFONE.match(linha) \
                and sum(c.isdigit() for c in linha) >= 8:
            reg.telefone = linha
            continue
        if not reg.endereco and not _PROTOCOLO.match(linha) and "www." not in linha:
            reg.endereco = linha[:300]


def coletar(listagem: Listagem, *, delay: float = DELAY_PADRAO,
            verbose: bool = True) -> list[Membro]:
    """
    Visita a ficha detalhada de cada empresa.

    Sem nonce nao ha ficha; nesse caso devolvemos o que a listagem ja deu, com
    o motivo registrado, em vez de fingir que as empresas nao tem dado extra.
    """
    membros = listagem.membros
    if not listagem.nonce:
        for reg in membros:
            reg.erro = reg.erro or "nonce ausente: ficha detalhada nao consultada"
        return membros

    # Guarda mais rigida que a convencao do projeto, e de proposito. A ficha
    # mora sob /wp-admin/, caminho que o robots deste site proibe em bloco e
    # libera so para o admin-ajax.php. Se o robots NAO pode ser lido, nao temos
    # como saber se essa excecao continua valendo, e "seguir permitindo" seria
    # apostar justamente no caminho mais sensivel do site. Nesse caso a coleta
    # entrega o que a listagem publica deu e registra o motivo.
    if listagem.situacao_robots != "lido":
        for reg in membros:
            reg.erro = reg.erro or (
                f"robots.txt {listagem.situacao_robots}: ficha sob /wp-admin/ "
                f"nao consultada por precaucao")
        if verbose:
            print(f"      robots.txt {listagem.situacao_robots}: as fichas ficam de fora, "
                  f"porque a permissao do /wp-admin/admin-ajax.php nao pode ser confirmada")
        return membros

    total = len(membros)
    for i, reg in enumerate(membros, 1):
        if reg.id_fonte:
            dados = urllib.parse.urlencode({
                "action": "din_set_dutch_researcher_popup",
                "dutch_researcher_id": reg.id_fonte,
                "nonce": listagem.nonce,
            }).encode()
            try:
                _enriquecer_com_ficha(reg, _baixar(AJAX, dados=dados))
            except Exception as exc:
                # Falha na ficha nao invalida o cartao: o registro continua
                # valido com o que a listagem trouxe.
                reg.erro = f"ficha: {type(exc).__name__}: {exc}"[:150]
        if verbose:
            print(f"  [{i:>3}/{total}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:34]:34} | {reg.tipo_membro[:8]:8} | "
                  f"{reg.cidade[:16]:16} | {reg.telefone[:14]}")
        if i < total:
            time.sleep(delay)
    return membros


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "cep", "cidade",
           "tipo_membro", "fornecedor_pesquisa", "funcionarios", "certificacoes",
           "descricao", "listas_extras", "id_fonte", "logo", "url_perfil", "erro"]


def exportar(membros: list[Membro], nome: str = "din_holanda") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(m) for m in membros], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig porque o Excel abre utf-8 sem BOM como latin-1 e transforma
    # "Ruigrok NetPanel" e os nomes com trema em lixo silencioso.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for m in membros:
            d = asdict(m)
            d["listas_extras"] = " || ".join(f"{k}: {v}"
                                             for k, v in (d.get("listas_extras") or {}).items())
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
