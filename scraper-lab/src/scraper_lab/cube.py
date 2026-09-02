"""
Extrator dos membros da CUBE (Consumer and Customer Understanding Belgium).

DESCOBERTA DE ENDERECO. O alvo pedido foi a FEBELMAR. Ela nao existe mais
sozinha: em 2017 a FEBELMAR e a BAQMaR se fundiram na CUBE. O dominio antigo
tambem nao serve de fonte:

    febelmar.be  -> nao completa conexao nem em 80 nem em 443, com 60s de
                    espera; o DNS resolve para 178.208.46.54 e o host nao
                    responde. Idem baqmar.be.
    consumerunderstanding.be -> redireciona para cubelgium.be.

O SITE DA CUBE ESTA QUEBRADO, E ISSO MUDA A ESTRATEGIA. Toda URL de
cubelgium.be devolve HTTP 200 com a pagina "The page you are looking for is not
found", inclusive a home e a lista de membros. Nao e bloqueio nem paywall: o
tema/plugin da pagina parou de renderizar. O conteudo continua no banco e a API
REST do WordPress responde normalmente, entao a coleta e feita por ela:

    /wp-json/wp/v2/pages -> 34 paginas, entre elas as fichas de membro e as
                            duas versoes da lista de membros.

CONFORMIDADE. cubelgium.be NAO TEM robots.txt de verdade: /robots.txt responde
HTTP 200 com o mesmo HTML de 62 KB da pagina de erro, ou seja um soft 404. O
verificador do projeto interpreta esse HTML como arquivo de regras, nao acha
diretiva nenhuma e libera tudo, com situacao `lido`. Reportamos essa nuance:
o robots foi obtido, mas o que veio nao e um robots.txt, e portanto o site nao
declara nenhuma restricao nem Crawl-delay. Toda URL ainda passa por
`permitido()` antes da requisicao.

ARMADILHAS DESTA FONTE:

  a) A lista de membros existe em duas versoes, `members` (19 itens, mais nova)
     e `cube-members-2` (29 itens, mais antiga e mais completa em links
     externos). Ficar so com a nova perderia membro; ficar so com a antiga
     traria empresa que ja saiu. As duas sao lidas e a origem de cada nome fica
     na coluna `listado_em`.

  b) Varios links da lista apontam para paginas que nao existem mais
     (/dedicated, /dynata, /helion, /indiville, /ivox, /researchplus). Isso e
     link quebrado no site quebrado, nao membro fantasma: o registro entra com
     nome e site, sem inventar contato.

  c) O link do site da egerie esta embrulhado num redirecionador do Outlook
     (eur04.safelinks.protection.outlook.com/?url=...). Gravar esse endereco
     como site da empresa quebraria o casamento por dominio; `_desembrulhar`
     devolve a URL original.

  d) A lista antiga tem um link para research.gov, o orgao de pesquisa
     cientifica dos Estados Unidos. Nao e membro belga, e erro de edicao da
     propria pagina. `util()` descarta, e o motivo aparece no relatorio, em vez
     de o registro entrar calado na base.
"""

from __future__ import annotations

import csv
import html as _html
import json
import re
import time
import unicodedata
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido
from scraper_lab.robots import situacao as robots_situacao

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://cubelgium.be"
API_PAGINAS = f"{BASE}/wp-json/wp/v2/pages"
# Slugs das duas versoes da lista de membros publicadas pela CUBE.
LISTAS = ("members", "cube-members-2")

PAIS = "Belgium"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Sem robots com regras, nao ha Crawl-delay declarado: pausa padrao do projeto.
DELAY_PADRAO = 1.5

# Dominios da propria associacao e do escritorio que a administra
# (marketing.be aparece no e-mail de privacidade e no safelinks da egerie).
_DOMINIO_ASSOCIACAO = ("cubelgium.be", "febelmar.be", "baqmar.be",
                       "consumerunderstanding.be", "marketing.be",
                       "safelinks.protection.outlook.com", "esomar.org")

# Dominio que nao pode pertencer a um membro belga de pesquisa de mercado. Vem
# de link errado na propria pagina da CUBE.
_DOMINIO_IMPOSSIVEL = re.compile(r"(^|\.)(gov|mil)(\.[a-z]{2})?$", re.I)

_ESPACOS = re.compile(r"[ \t   ]+")
_VAZIOS = {"", "-", "--", "n/a", "na", "/"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_TEXTO = re.compile(r"(?<![@\w.])((?:https?://|www\.)[A-Za-z0-9-]+"
                        r"(?:\.[A-Za-z0-9-]+)+(?:/\S*)?)", re.I)
# Telefone belga: +32 seguido de digitos e separadores.
_TELEFONE = re.compile(r"^\+?\d[\d\s().\/+-]{7,}$")
_PROTOCOLO = re.compile(r"^https?://", re.I)
# Titulos que abrem o bloco de contato nas fichas.
_MARCO_CONTATO = re.compile(r"more information|get in touch|contact", re.I)
# O mesmo marco quando ele ocupa a linha inteira. A pontuacao final e livre
# porque o site escreve "More information:" numa ficha e "GET IN TOUCH..." em
# outra; sem tolerar isso, o proprio titulo da secao entrava como nome da
# pessoa de contato.
_MARCO_SOZINHO = re.compile(r"(more information|get in touch|contact)[\s:.\u2026-]*$", re.I)
# Dominio escrito sem protocolo e sem www ("data-synergy.be"). Precisa ser
# reconhecido para nao virar nome de pessoa.
_DOMINIO_NU = re.compile(
    r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:be|com|eu|nl|fr|org|net|io|ai|de|uk)$", re.I)


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", (texto or "").replace("​", "").replace("­", ""))
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    # NFC para que "é" de "égérie" nao gere duas empresas ao cruzar com Esomar.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


CODIFICACAO_DETECTADA = ""

_ESPERA_RETENTATIVA = (0, 3, 8, 15)


def _baixar_json(url: str, *, timeout: int = 45) -> tuple[object, dict]:
    """
    GET na API REST, devolvendo (dados, cabecalhos).

    A codificacao e lida do cabecalho antes de qualquer suposicao. A API
    declara UTF-8, mas os nomes belgas passam por "égérie research" e
    "B²Sense": um dia de configuracao errada no servidor trocaria os
    caracteres sem levantar excecao nenhuma.
    """
    global CODIFICACAO_DETECTADA
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    cabecalhos = {"User-Agent": UA, "Accept": "application/json",
                  "Accept-Language": "nl-BE,nl;q=0.9,fr;q=0.7,en;q=0.6"}
    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, headers=cabecalhos), timeout=timeout) as r:
                bruto = r.read(12_000_000)
                ctype = r.headers.get("Content-Type", "")
                cabecalhos_resposta = dict(r.headers)
            m = re.search(r"charset=([\w-]+)", ctype, re.I)
            codec = m.group(1) if m else "utf-8"
            try:
                texto = bruto.decode(codec)
            except (UnicodeDecodeError, LookupError):
                texto, codec = bruto.decode("utf-8", errors="replace"), "utf-8/replace"
            CODIFICACAO_DETECTADA = codec.lower()
            return json.loads(texto), cabecalhos_resposta
        except HTTPError as exc:
            ultimo = exc
            if exc.code in (404, 410):
                break
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            ultimo = exc
    raise ultimo if ultimo else RuntimeError("falha desconhecida")


@dataclass
class Membro:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    dominio: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    cidade: str = ""
    descricao: str = ""
    tipo_membro: str = "Member"
    fornecedor_pesquisa: str = "indefinido"
    contato: str = ""            # pessoa e cargo, como a ficha publica
    contato_nome: str = ""
    contato_cargo: str = ""
    listado_em: str = ""         # em qual(is) lista(s) de membros aparece
    nome_origem: str = ""        # cms / rotulo / dominio / slug
    tem_ficha: str = "nao"
    coletado_em: str = ""
    erro: str = ""


def _sem_letra(t: str) -> bool:
    """Linha so com pontuacao ou espaco rigido, residuo do editor visual."""
    return not re.search(r"[A-Za-z\u00c0-\u024f0-9]", t or "")


def _dominio_de(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url if _PROTOCOLO.match(url) else "https://" + url).netloc
    return re.sub(r"^www\.", "", host, flags=re.I).lower()


def _proprio_da_associacao(url: str) -> bool:
    return any(d in (url or "").lower() for d in _DOMINIO_ASSOCIACAO)


def _desembrulhar(url: str) -> str:
    """
    Devolve a URL real quando ela vem dentro de um redirecionador.

    A ficha da egerie publica o site por dentro do safelinks do Outlook. Gravar
    o endereco do redirecionador como site da empresa quebraria o casamento por
    dominio, que e justamente como a etapa de uniao herda e-mail entre fontes.
    """
    if "safelinks.protection.outlook.com" not in (url or "").lower():
        return url
    alvo = parse_qs(urlparse(url).query).get("url", [""])[0]
    return urllib.parse.unquote(alvo) or url


def _paginas() -> tuple[list[dict], int | None]:
    """
    Todas as paginas do WordPress da CUBE.

    A paginacao segue a regra do projeto: so paramos depois de DUAS respostas
    vazias seguidas. O X-WP-Total do proprio CMS entra como contagem declarada
    para conferencia; divergencia vira aviso, nao silencio.
    """
    paginas: list[dict] = []
    vistos: set[int] = set()
    total: int | None = None
    vazias = 0
    pagina = 1
    while vazias < 2 and pagina <= 40:
        url = (f"{API_PAGINAS}?per_page=100&page={pagina}"
               f"&_fields=id,slug,link,title,content")
        try:
            dados, cabecalhos = _baixar_json(url)
        except HTTPError as exc:
            # A API responde 400 quando a pagina passa do fim; isso conta como
            # resposta vazia, nao como erro de coleta.
            if exc.code in (400, 404):
                dados, cabecalhos = [], {}
            else:
                raise
        if total is None:
            bruto = cabecalhos.get("X-WP-Total") or cabecalhos.get("x-wp-total")
            total = int(bruto) if bruto and str(bruto).isdigit() else None
        novos = [p for p in (dados or []) if p.get("id") not in vistos]
        for p in novos:
            vistos.add(p["id"])
        paginas += novos
        vazias = vazias + 1 if not novos else 0
        pagina += 1
        time.sleep(DELAY_PADRAO)
    return paginas, total


def _sopa(pagina: dict) -> BeautifulSoup:
    """
    HTML util de uma pagina do CMS.

    O conteudo vem misturado com shortcodes do WPBakery ([vc_row ...]), porque
    o plugin que os renderiza esta quebrado. Os shortcodes sao removidos antes
    de qualquer leitura: alguns carregam atributos com aspas tipograficas que o
    parser interpretaria como texto da pagina.
    """
    bruto = _html.unescape(pagina.get("content", {}).get("rendered", ""))
    return BeautifulSoup(re.sub(r"\[[^\]\[]*\]", " ", bruto), "html.parser")


def _links_da_lista(pagina: dict) -> list[tuple[str, str]]:
    """
    Pares (destino, rotulo) de uma pagina de lista de membros.

    Os itens sao imagens de logotipo com `link="/slug"` dentro do shortcode do
    WPBakery, e nao <a>. Por isso a leitura e feita no texto do shortcode, e
    nao pelo parser de HTML.
    """
    bruto = _html.unescape(pagina.get("content", {}).get("rendered", ""))
    # O WordPress converte as aspas retas do shortcode em aspas tipograficas.
    normalizado = bruto.replace("”", '"').replace("“", '"').replace("″", '"')
    achados: list[tuple[str, str]] = []
    for destino in re.findall(r'link="([^"]+)"', normalizado):
        achados.append((destino.strip(), ""))
    sopa = BeautifulSoup(re.sub(r"\[[^\]\[]*\]", " ", normalizado), "html.parser")
    for a in sopa.select("a[href]"):
        achados.append((a["href"].strip(), _limpar(a.get_text(" ", strip=True))))
    return achados


def _botao_descobrir(sopa: BeautifulSoup):
    """
    Botao "Discover X" que fecha toda ficha de membro.

    E a assinatura do modelo de ficha e o link EXPLICITO para o site da
    empresa. Usar esse botao em vez de varrer os links da pagina e o que evita
    trazer o redirecionador do Outlook e o dominio da propria associacao como
    se fossem o site do membro.
    """
    for a in sopa.select("a[href]"):
        classes = " ".join(a.get("class") or [])
        texto = _limpar(a.get_text(" ", strip=True))
        if "qbutton" not in classes or not re.match(r"discover\b", texto, re.I):
            continue
        destino = _desembrulhar(a.get("href", "").strip())
        # O botao so identifica membro quando aponta para FORA da associacao. A
        # home e a pagina Community tambem tem botao "Discover ...", mas levam
        # de volta para cubelgium.be; sem esta checagem as duas entravam na
        # base como se fossem empresas.
        if not _PROTOCOLO.match(destino) or _proprio_da_associacao(destino):
            continue
        return a
    return None


def _eh_ficha(sopa: BeautifulSoup) -> bool:
    """
    Diz se a pagina e ficha de membro.

    Criterio de forma, nao de nome: ficha de membro tem o botao "Discover X" ou
    um titulo "About X". Assim as fichas continuam sendo achadas mesmo sem link
    nas listas, que e o caso da Accurat depois que o site quebrou, e a pagina de
    politica de privacidade para de ser confundida com membro so porque a
    palavra "contact" aparece no texto dela.
    """
    if _botao_descobrir(sopa) is not None:
        return True
    for h in sopa.find_all(["h1", "h2", "h3", "h4", "h5"]):
        if re.match(r"about\s+\S", _limpar(h.get_text(" ", strip=True)), re.I):
            return True
    return False


def _linhas(no) -> list[str]:
    copia = BeautifulSoup(str(no), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    for tag in copia.find_all(["p", "div", "li"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    return [l for l in (_limpar(x) for x in copia.get_text("").split("\n")) if l]


def extrair_ficha(pagina: dict) -> Membro:
    reg = Membro(url_perfil=pagina.get("link", ""), tem_ficha="sim",
                 coletado_em=datetime.now(timezone.utc).isoformat())
    # O titulo da pagina no CMS e o nome mais limpo que a fonte oferece; o
    # cabecalho "About X" repete o nome sem sufixo societario e o botao
    # "Discover X" e so um rotulo de interface.
    reg.nome = _limpar(_html.unescape(pagina.get("title", {}).get("rendered", "")))
    reg.nome_origem = "cms" if reg.nome else ""

    sopa = _sopa(pagina)
    for t in sopa(["script", "style"]):
        t.decompose()

    botao = _botao_descobrir(sopa)
    rotulo_botao = _limpar(botao.get_text(" ", strip=True)) if botao is not None else ""

    # SITE: o link explicito do botao "Discover X" vem primeiro. Depois o texto
    # visivel de um link que pareca dominio, que e mais confiavel que o href
    # quando o href esta embrulhado em redirecionador. Por ultimo o dominio
    # escrito como texto puro, que e como a akkanto publica.
    candidatos: list[str] = []
    if botao is not None:
        candidatos.append(_desembrulhar(botao["href"].strip()))
    for a in sopa.select("a[href]"):
        if a is botao:
            continue
        visivel = _limpar(a.get_text(" ", strip=True))
        if visivel and _URL_TEXTO.fullmatch(visivel):
            candidatos.append(visivel)
        candidatos.append(_desembrulhar(a["href"].strip()))
    candidatos += [m.group(1) for m in _URL_TEXTO.finditer(sopa.get_text(" ", strip=True))]
    for candidato in candidatos:
        if not candidato or candidato.lower().startswith("mailto:"):
            continue
        if _proprio_da_associacao(candidato):
            continue
        dominio = _dominio_de(candidato)
        if not dominio or "." not in dominio:
            continue
        reg.site = (candidato if _PROTOCOLO.match(candidato)
                    else "https://" + candidato.lstrip("/"))
        reg.dominio = dominio
        break

    # E-MAIL: link mailto primeiro, texto solto depois. A busca varre a ficha
    # inteira porque nem toda ficha tem o titulo "More information": a
    # Datasynergy publica o e-mail sem marco nenhum, e amarrar a extracao ao
    # titulo a deixava sem contato.
    for a in sopa.select('a[href^="mailto:"]'):
        valor = _limpar(a["href"][7:].split("?")[0]).lower()
        if valor and not _proprio_da_associacao(valor):
            reg.email = valor
            break
    if not reg.email:
        for valor in _EMAIL.findall(sopa.get_text(" ", strip=True)):
            if not _proprio_da_associacao(valor):
                reg.email = valor.lower()
                break

    blocos = sopa.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li"])

    # Onde comeca o bloco de contato. Primeiro procuramos um marco curto
    # ("More information", "GET IN TOUCH..."). Sem marco, o corte cai um pouco
    # antes do paragrafo do e-mail: a Datasynergy nao escreve marco nenhum, e
    # cortar exatamente no e-mail deixaria de fora nome e cargo, que moram nos
    # paragrafos anteriores.
    corte = len(blocos)
    for i, el in enumerate(blocos):
        texto_el = _limpar(el.get_text(" ", strip=True))
        if not texto_el:
            continue
        if len(texto_el) <= 60 and _MARCO_CONTATO.search(texto_el):
            corte = i
            break
    if corte == len(blocos) and reg.email:
        for i, el in enumerate(blocos):
            if reg.email in el.get_text(" ", strip=True).lower():
                corte = max(0, i - 2)
                break

    # PESSOA E CARGO: linhas curtas do bloco de contato que nao sao e-mail,
    # telefone, endereco de site nem rotulo de botao. Restringir ao bloco de
    # contato e o que impede o texto de apresentacao de virar nome de gente.
    pessoa: list[str] = []
    for el in blocos[corte:]:
        for linha in _linhas(el):
            # O botao "Discover X" e inline e cola no fim da linha anterior. Na
            # ficha da Accurat isso grudava "Discover Accurat" no telefone, que
            # deixava de ser reconhecido como telefone e virava nome de pessoa.
            if rotulo_botao:
                linha = _limpar(linha.replace(rotulo_botao, " "))
            if not linha:
                continue
            if _EMAIL.search(linha) or _URL_TEXTO.search(linha):
                continue
            if _TELEFONE.match(linha):
                reg.telefone = reg.telefone or linha
                continue
            if linha == rotulo_botao or _MARCO_SOZINHO.match(linha):
                continue
            if _DOMINIO_NU.match(linha):
                continue
            # Nome de pessoa e cargo sao curtos; frase longa e apresentacao.
            if len(linha) > 60 or _sem_letra(linha):
                continue
            if linha not in pessoa:
                pessoa.append(linha)
    if pessoa:
        reg.contato_nome = pessoa[0]
        reg.contato_cargo = pessoa[1] if len(pessoa) > 1 else ""
        reg.contato = " | ".join(pessoa[:3])

    # DESCRICAO: tudo que vem antes do bloco de contato.
    descricao: list[str] = []
    for el in blocos[:corte]:
        t = _limpar(el.get_text(" ", strip=True))
        # O cabecalho institucional se repete em toda ficha e nao descreve a
        # empresa.
        if not t or re.fullmatch(
                r"CUBE Community|Consumer and Customer understanding Belgium", t, re.I):
            continue
        if re.fullmatch(r"About\s+.{1,60}", t, re.I):
            continue
        if t == rotulo_botao or _sem_letra(t):
            continue
        if t not in descricao:
            descricao.append(t)
    reg.descricao = " | ".join(descricao)[:1500]

    if not reg.nome:
        reg.erro = "ficha sem titulo no CMS"
    return reg


def _chave_nome(nome: str) -> str:
    """
    Nome reduzido a letras e digitos minusculos, sem acento.

    Serve so para casar registros duplicados. "Egérie Research" e "égérie
    research" viram a mesma chave, e "iVOX" casa com "ivox" vindo do slug.
    """
    sem_acento = unicodedata.normalize("NFKD", nome or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _mesmo(a: str, b: str) -> bool:
    """
    Diz se duas chaves de nome apontam para a mesma empresa.

    Prefixo conta, porque a lista escreve o apelido e o site escreve o nome
    inteiro: /helion contra helionresearch.com, /synapses contra
    synapsesquali, "GFK" contra "GFK Belgium". O prefixo so vale a partir de
    quatro caracteres, senao "gfk" casaria com qualquer coisa comecada em g.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    menor, maior = (a, b) if len(a) <= len(b) else (b, a)
    return len(menor) >= 4 and maior.startswith(menor)


# Confiabilidade da origem do nome, do melhor para o pior.
_QUALIDADE_NOME = {"cms": 3, "rotulo": 2, "dominio": 1, "slug": 0}

_AVISO_LINK_MORTO = "link interno sem ficha correspondente no CMS"


def _prefixo_de_slug(reg: "Membro", chave_dominio: str) -> bool:
    """Registro que e slug orfao e prefixo do dominio do candidato."""
    chave_reg = _chave_nome(reg.nome)
    return bool(reg.nome_origem == "slug" and not reg.dominio and chave_dominio
                and len(chave_reg) >= 4 and chave_dominio.startswith(chave_reg))


def _prefixo_de_slug_do_novo(chave: str, chave_reg_dominio: str,
                             nome_origem_novo: str) -> bool:
    """Candidato que e slug orfao e prefixo do dominio de um registro."""
    return bool(nome_origem_novo == "slug" and chave_reg_dominio and len(chave) >= 4
                and chave_reg_dominio.startswith(chave))


def _da_lista(destino: str, rotulo: str, lista: str) -> Membro:
    """Registro de item que so aparece na lista, sem ficha propria."""
    alvo = _desembrulhar(destino)
    reg = Membro(url_perfil="", nome=rotulo, listado_em=lista,
                 nome_origem="rotulo" if rotulo else "",
                 coletado_em=datetime.now(timezone.utc).isoformat())
    if _PROTOCOLO.match(alvo):
        reg.site, reg.dominio = alvo, _dominio_de(alvo)
        if not reg.nome:
            # Sem rotulo no link, o dominio e o unico nome que a fonte da.
            reg.nome = (reg.dominio.split(".")[0] or "").strip()
            reg.nome_origem = "dominio"
    else:
        # Link interno para ficha que nao existe mais. Guardamos o slug como
        # nome porque e a unica identificacao publicada, e marcamos a origem
        # para que ninguem confunda slug com razao social.
        reg.nome = rotulo or alvo.strip("/").split("/")[-1]
        reg.nome_origem = reg.nome_origem or "slug"
        reg.erro = _AVISO_LINK_MORTO
    return reg


def _fundir(base: Membro, extra: Membro) -> None:
    """
    Traz para o registro ja existente o que so o novo tem.

    Nunca sobrescreve: o registro que veio da ficha e sempre mais completo que
    o que veio do link da lista, e a ordem de leitura nao pode mudar o
    resultado.
    """
    for campo in ("email", "site", "dominio", "telefone", "endereco", "cidade",
                  "descricao", "contato", "contato_nome", "contato_cargo"):
        if not getattr(base, campo) and getattr(extra, campo):
            setattr(base, campo, getattr(extra, campo))
    if extra.listado_em:
        base.listado_em = " + ".join(
            dict.fromkeys(filter(None, base.listado_em.split(" + ") + [extra.listado_em])))
    # O nome fica com a origem mais confiavel das duas. Um slug de URL
    # ("researchplus") e a pior identificacao possivel e nao pode prevalecer
    # sobre o rotulo publicado na lista ("Research Plus").
    if _QUALIDADE_NOME.get(extra.nome_origem, 0) > _QUALIDADE_NOME.get(base.nome_origem, 0):
        base.nome, base.nome_origem = extra.nome, extra.nome_origem
    # O aviso de link quebrado deixa de valer quando a outra lista trouxe o
    # site da empresa: o link interno continua quebrado, mas a empresa foi
    # identificada, e manter o aviso sugeriria um problema que nao existe mais.
    if base.erro == _AVISO_LINK_MORTO and base.site:
        base.erro = ""


def coletar(*, verbose: bool = True) -> tuple[list[Membro], dict]:
    """
    Le as fichas de membro e as duas listas de membros, e junta tudo.

    A juncao usa duas chaves, nessa ordem: dominio do site e nome normalizado.
    So dominio nao basta porque a mesma empresa aparece com dominio global numa
    lista e local na outra (kantar.com contra kantar.be, gfk.com contra
    onlinegfk.be). So nome tambem nao basta, porque metade dos links nao tem
    rotulo nenhum.
    """
    sit = robots_situacao(BASE, agente=UA)
    paginas, total_declarado = _paginas()
    if verbose:
        print(f"      robots.txt: {sit} "
              f"(soft 404: o servidor devolve HTML da pagina de erro, sem regras)")
        print(f"      {len(paginas)} paginas no CMS"
              + (f", CMS declara {total_declarado}" if total_declarado else ""))

    por_slug = {p.get("slug", ""): p for p in paginas}

    membros: list[Membro] = []
    fichas_por_slug: dict[str, Membro] = {}
    for pagina in paginas:
        if pagina.get("slug") in LISTAS:
            continue
        if not _eh_ficha(_sopa(pagina)):
            continue
        reg = extrair_ficha(pagina)
        membros.append(reg)
        fichas_por_slug[(pagina.get("slug") or "").lower()] = reg
    if verbose:
        print(f"      {len(membros)} fichas de membro identificadas por forma")

    def procurar(dominio: str, nome: str, nome_origem_novo: str = "") -> Membro | None:
        """Registro ja existente que seja a mesma empresa do candidato."""
        chave = _chave_nome(nome)
        chave_dominio = _chave_nome(dominio.split(".")[0]) if dominio else ""
        for reg in membros:
            if dominio and reg.dominio and reg.dominio == dominio:
                return reg
            chave_reg = _chave_nome(reg.nome)
            chave_reg_dominio = (_chave_nome(reg.dominio.split(".")[0])
                                 if reg.dominio else "")
            if _mesmo(chave, chave_reg):
                return reg
            # Slug de link quebrado contra dominio de link externo: /helion e
            # helionresearch.com sao a mesma empresa. O casamento so vale numa
            # direcao, com o SLUG sendo prefixo do dominio. Aceitar o contrario
            # fundia /researchplus com research.gov, que nao tem nada a ver, e
            # o membro belga sumia junto com o link errado.
            if _prefixo_de_slug(reg, chave_dominio) or _prefixo_de_slug_do_novo(
                    chave, chave_reg_dominio, nome_origem_novo):
                return reg
        return None

    for lista in LISTAS:
        pagina = por_slug.get(lista)
        if pagina is None:
            continue
        vistos_na_lista: set[str] = set()
        for destino, rotulo in _links_da_lista(pagina):
            if not destino or destino.startswith("#") or destino.startswith("mailto:"):
                continue
            if destino.lower() in vistos_na_lista:
                continue
            vistos_na_lista.add(destino.lower())

            alvo = _desembrulhar(destino)
            if _PROTOCOLO.match(alvo):
                if _proprio_da_associacao(alvo):
                    continue
                dominio, slug = _dominio_de(alvo), ""
            else:
                dominio = ""
                slug = alvo.strip("/").split("/")[-1].lower()
                # Link interno para uma pagina que EXISTE e nao e ficha de
                # membro e navegacao ("/contact", "/membership"), nao empresa.
                # Sem esta checagem o botao "Get in touch" virava um membro.
                if slug in por_slug and slug not in fichas_por_slug:
                    continue

            novo = _da_lista(destino, rotulo, lista)
            existente = (fichas_por_slug.get(slug) if slug else None)
            if existente is None:
                for s, reg in fichas_por_slug.items():
                    if slug and _mesmo(s, slug):
                        existente = reg
                        break
            if existente is None:
                existente = procurar(dominio, novo.nome, novo.nome_origem)

            if existente is not None:
                _fundir(existente, novo)
                continue
            membros.append(novo)

    for reg in membros:
        if not reg.listado_em and reg.tem_ficha == "sim":
            # Ficha viva sem link nas listas. Depois que o front-end quebrou, a
            # lista deixou de ser a unica prova de filiacao.
            reg.listado_em = "so ficha"

    if verbose:
        for i, reg in enumerate(membros, 1):
            print(f"  [{i:>3}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:26]:26} | {reg.nome_origem:7} | {reg.email[:28]:28} | "
                  f"{reg.contato_nome[:18]:18} | {reg.listado_em}")

    resumo = {"situacao_robots": sit, "paginas_cms": len(paginas),
              "total_declarado": total_declarado}
    return membros, resumo


def util(reg: Membro) -> tuple[bool, str]:
    """
    Diz se o registro pode entrar na base, e por que nao quando nao pode.

    Descartamos so o que comprovadamente nao e membro: registro sem nome e o
    link para research.gov, orgao publico dos Estados Unidos que entrou na
    lista antiga por erro de edicao. Nada e descartado por "parecer" pouco
    relevante; essa decisao nao e deste extrator.
    """
    if not reg.nome:
        return False, "sem nome"
    if reg.dominio and _DOMINIO_IMPOSSIVEL.search(reg.dominio.split(":")[0]):
        return False, f"dominio impossivel para membro belga: {reg.dominio}"
    return True, ""


COLUNAS = ["nome", "email", "site", "dominio", "pais", "telefone", "endereco",
           "cidade", "tipo_membro", "fornecedor_pesquisa", "contato",
           "contato_nome", "contato_cargo", "descricao", "listado_em",
           "tem_ficha", "url_perfil", "erro"]


def exportar(membros: list[Membro], nome: str = "cube_belgica") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(m) for m in membros], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig porque o Excel abre utf-8 sem BOM como latin-1 e "égérie
    # research" e "B²Sense" viram lixo.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for m in membros:
            d = asdict(m)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
