"""
Expositores e patrocinadores dos congressos de pesquisa de mercado.

Por que esta fonte existe: diretorio de associacao diz quem e filiado, o que
e um estado permanente e barato de manter. Lista de expositor e patrocinador
diz quem assinou contrato e pagou por estande neste ano. E a diferenca entre
"existe" e "tem orcamento aprovado agora". O nivel do patrocinio (title,
platinum, gold, kiosk) e a melhor proxy publica do tamanho desse orcamento,
entao ele e preservado cru, sem normalizacao, em `nivel_patrocinio`.

Seis eventos entraram: Quirk's, IIeX, MRMW, TMRE, IA CRC e MRS Annual
Conference. A Esomar ficou de fora porque a lista de expositores dela so
existe atras de /graphql, caminho que o proprio robots.txt da Esomar proibe;
o site espelho esomar-congress.com, por sua vez, declara `Disallow: /` para
o ClaudeBot. Entregar essa lista exigiria furar uma das duas regras.

Sobre o robots.txt da Greenbook: ele proibe `/iiex/`, e o briefing deste
squad avisava disso. Na pratica o conteudo do IIeX mudou de lugar e hoje mora
em `/events/iiex-*`, que o mesmo robots.txt libera. Nenhuma URL sob `/iiex/`
e tocada aqui, e a checagem passa pelo verificador proprio do projeto porque
o urllib.robotparser ignora curinga e devolveria True para caminho proibido.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

# Varios sites de evento usam cadeia de certificados que o bundle do Python
# nao valida. truststore delega ao keychain do sistema, o mesmo caminho que
# o usaspending.py ja adota neste projeto.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # ambiente sem truststore segue com o padrao
    pass

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

PAUSA = 1.5  # minimo entre duas requisicoes ao MESMO dominio

_ESPACOS = re.compile(r"\s+")
_ultimo_acesso: dict[str, float] = {}


def permitido(url: str) -> bool:
    """Portao unico de robots.txt. Nenhum download acontece sem passar aqui."""
    return robots_permitido(url, agente=UA)


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


# Respostas que significam "o servidor tropecou", nao "a empresa nao existe".
# A Cloudflare devolve 502/503/504/520/522/524 quando a origem demora, e o
# Quirk's fez isso em um perfil no meio de 422. Aceitar isso como ausencia
# apagaria uma empresa da base sem deixar rastro no total.
_TRANSITORIOS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}


def _baixar(url: str, timeout: int = 30, tentativas: int = 3) -> str:
    """
    Baixa respeitando robots e a pausa por dominio, com nova tentativa.

    A pausa e contada por host e nao por iteracao do laco: os coletores
    alternam entre dominios (thequirksevent, greenbook, informaconnect) e
    dormir 1,5s entre requisicoes a hosts diferentes so desperdicaria tempo
    sem proteger ninguem.
    """
    if not permitido(url):
        raise PermissionError(f"robots.txt proibe: {url}")
    host = urlparse(url).netloc
    ultimo: Exception | None = None
    for n in range(tentativas):
        espera = PAUSA - (time.monotonic() - _ultimo_acesso.get(host, 0.0))
        if espera > 0:
            time.sleep(espera)
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept-Language": "en-US,en;q=0.9"})
        try:
            with urlopen(req, timeout=timeout) as r:
                html = r.read(6_000_000).decode("utf-8", errors="replace")
                _baixar.ultima_url = r.url  # type: ignore[attr-defined]
                return html
        except HTTPError as exc:
            ultimo = exc
            if exc.code not in _TRANSITORIOS:
                raise
        except (URLError, TimeoutError, OSError) as exc:
            ultimo = exc
        finally:
            _ultimo_acesso[host] = time.monotonic()
        # espera crescente: 3s, 6s. O host ja esta com problema, insistir
        # no mesmo ritmo so piora.
        time.sleep(3 * (n + 1))
    raise ultimo if ultimo else RuntimeError(f"falha ao baixar {url}")


@dataclass
class Participante:
    """Uma empresa numa edicao de um evento. A chave logica e (evento, edicao, nome)."""

    nome: str = ""
    site: str = ""
    tipo_participacao: str = ""   # expositor / patrocinador / ambos / parceiro
    nivel_patrocinio: str = ""    # rotulo cru do site: Title, Platinum, Kiosk...
    evento: str = ""
    edicao: str = ""              # cidade ou regiao da edicao
    ano: str = ""
    cidade: str = ""
    pais: str = ""
    email: str = ""
    descricao: str = ""
    estande: str = ""
    url_perfil: str = ""
    url_fonte: str = ""           # pagina de listagem de onde saiu o registro
    fonte: str = ""
    coletado_em: str = ""
    erro: str = ""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Filtros de qualidade
# --------------------------------------------------------------------------

# Quem organiza o evento aparece na propria lista de patrocinadores ("Presented
# By: Greenbook"). Nao e prospeccao: e o vendedor. Mesma logica para veiculo de
# midia e associacao setorial, que expoem sem ter orcamento de compra de
# pesquisa. Ficam marcados em vez de descartados, porque a decisao de usar ou
# nao e do time comercial, mas nao contam como empresa no resumo.
_ORGANIZADORAS = {
    "greenbook", "quirk", "quirk's", "quirks", "quirk's media", "merlien",
    "merlien institute", "informa", "informa connect", "insights association",
    "esomar",
}

_MIDIA_E_ASSOCIACAO = {
    "market research council", "women in research", "woman in research",
    "women in research (wire)", "the research club", "qrca",
    "association for qualitative research", "mrii", "insights association",
    "university of georgia | market research institute international",
    "mrii | university of georgia", "university of georgia",
    "the insights exchange", "research world", "greenbook",
    "professional insights collaborative", "40+ double dutch club",
    "insight management academy", "mrba", "market research benevolent association",
    "richmond events",
}

# Rotulos de nivel que dizem "isto nao e patrocinio comercial de fornecedor".
# "Client Sponsor" e "Brand Partner" sao o lado comprador (Unilever, PepsiCo)
# patrocinando o evento: sao marcas que contratam pesquisa, nao empresas que
# vendem pesquisa, e por isso nao pertencem a esta base.
_NIVEIS_NAO_COMERCIAIS = {
    "presented by", "media partner", "media partners", "association partner",
    "learning partner", "brand partner", "partner", "partners",
    "client sponsor", "mrs is proud to support",
}

# Hospedeiros que aparecem no lugar do site da empresa: agenda de reuniao,
# formulario e encurtador. Guardar isso como "site" quebra o enriquecimento
# por dominio la na frente, entao o campo fica vazio de proposito.
_NAO_E_SITE = (
    "cal.com", "calendly.com", "eventbrite.", "docs.google.com", "forms.gle",
    "linktr.ee", "bit.ly", "hubspot.com", "zoom.us", "lu.ma",
)


def _site_valido(url: str) -> bool:
    return bool(url) and not any(d in url.lower() for d in _NAO_E_SITE)


def _normalizar_nome(nome: str) -> str:
    n = _limpar(nome).lower()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"\s+(inc|llc|ltd|limited|gmbh|bv|b\.v\.|sa|s\.a\.|co)$", "", n)
    return n.strip()


def eh_organizadora(p: Participante) -> bool:
    return _normalizar_nome(p.nome) in _ORGANIZADORAS


def eh_comercial(p: Participante) -> bool:
    """
    True quando o registro representa uma empresa com verba propria no evento.

    Descarta organizadora, veiculo de midia e associacao setorial. Tambem
    descarta quem so aparece como palestrante: presenca em palco nao implica
    contrato de estande, e misturar os dois inflaria a base com marcas
    compradoras (PepsiCo, T-Mobile) que nao sao alvo desta coleta.
    """
    if not p.nome or p.erro:
        return False
    nome = _normalizar_nome(p.nome)
    if nome in _ORGANIZADORAS or nome in _MIDIA_E_ASSOCIACAO:
        return False
    if _limpar(p.nivel_patrocinio).lower() in _NIVEIS_NAO_COMERCIAIS:
        return False
    return p.tipo_participacao in ("expositor", "patrocinador", "expositor e patrocinador")


# --------------------------------------------------------------------------
# 1. Quirk's Event  (thequirksevent.com)
# --------------------------------------------------------------------------
#
# Melhor fonte das quatro. Renderiza no servidor, tem pagina /expo/ com o
# nivel de patrocinio explicito e um perfil por empresa com a string de
# participacao ja escrita pelo organizador ("Exhibitor, Presenter, Bronze
# Sponsor"). Nao precisamos inferir nada.

QUIRKS = "https://thequirksevent.com"

# So as edicoes que o sitemap do proprio site declara. Testar 2025 devolve
# HTTP 200, mas a URL final vira https://thequirksevent.com/expo/, uma pagina
# generica de 23 logos que nao pertence a edicao nenhuma. Sem conferir a URL
# final, essas 23 empresas entrariam cinco vezes com o ano errado.
QUIRKS_EDICOES = {
    "dallas-2026": ("Dallas", "2026", "United States"),
    "chicago-2026": ("Chicago", "2026", "United States"),
    "london-2026": ("London", "2026", "United Kingdom"),
    "new-york-2026": ("New York", "2026", "United States"),
    "virtual-global-2026": ("Virtual Global", "2026", ""),
}

_QUIRKS_SLUG = re.compile(r"/company/([a-z0-9][a-z0-9\-]*)/?")


def listar_quirks(edicao: str, *, verbose: bool = True) -> list[str]:
    """
    Slugs de empresa da pagina /expo/ da edicao, sem repeticao.

    Conta slug e nao elemento do DOM: a mesma empresa aparece no grid de
    patrocinadores e de novo na faixa de logos do rodape, e contar ancoras
    dava numero inflado.
    """
    fonte = f"{QUIRKS}/{edicao}/expo/"
    html = _baixar(fonte)
    final = getattr(_baixar, "ultima_url", fonte)
    if f"/{edicao}/" not in final:
        # redirecionou para a pagina generica: a edicao nao existe mais
        raise RuntimeError(f"{edicao}: redirecionou para {final}, edicao inexistente")
    slugs = sorted(set(_QUIRKS_SLUG.findall(html)))
    if verbose:
        print(f"      {edicao}: {len(slugs)} empresas unicas em /expo/")
    return [f"{QUIRKS}/{edicao}/company/{s}/" for s in slugs]


# "Exhibitor, Presenter, Bronze Sponsor" -> tipo + nivel
_NIVEL_QUIRKS = re.compile(
    r"\b(Title|Platinum|Titanium|Gold|Silver|Bronze|Diamond|Founding)\b[^,]*Sponsor",
    re.I)


def _classificar_quirks(participacao: str) -> tuple[str, str]:
    p = participacao.lower()
    expoe = "exhibitor" in p
    patrocina = "sponsor" in p
    m = _NIVEL_QUIRKS.search(participacao)
    nivel = _limpar(m.group(1)).title() if m else ("Sponsor" if patrocina else "")
    if expoe and patrocina:
        return "expositor e patrocinador", nivel
    if expoe:
        return "expositor", nivel
    if patrocina:
        return "patrocinador", nivel
    if "partner" in p:
        return "parceiro", ""
    return "outro", ""     # normalmente "Presenter": palestrante sem estande


def extrair_quirks(html: str, url: str, edicao: str) -> Participante:
    cidade, ano, pais = QUIRKS_EDICOES.get(edicao, ("", "", ""))
    p = Participante(evento="Quirk's Event", edicao=cidade, ano=ano, cidade=cidade,
                     pais=pais, url_perfil=url, url_fonte=f"{QUIRKS}/{edicao}/expo/",
                     fonte="thequirksevent.com", coletado_em=_agora())
    s = BeautifulSoup(html, "html.parser")

    titulo = _limpar(s.title.get_text()) if s.title else ""
    p.nome = titulo.split(" - The Quirks Event")[0].strip()

    rotulo = s.select_one("p.icon_sponsor")
    participacao = _limpar(rotulo.get_text()) if rotulo else ""
    p.tipo_participacao, p.nivel_patrocinio = _classificar_quirks(participacao)

    # O link do site vem de p.company_url. Varrer link externo qualquer traria
    # eadn-wc02-11236441.nxedge.io, o CDN que hospeda os logos do evento.
    site = s.select_one("p.company_url a[href]")
    if site and site.get("href", "").startswith("http"):
        alvo = site["href"].split("?")[0]
        p.site = alvo if _site_valido(alvo) else ""

    estande = s.select_one("a.icon_pin span")
    if estande:
        p.estande = _limpar(estande.get_text())

    bloco = s.select_one("div.col-sm-9.content")
    if bloco:
        for par in bloco.find_all("p", recursive=False):
            if par.get("class") or par.find("a"):
                continue
            texto = _limpar(par.get_text())
            if len(texto) > 60:
                p.descricao = texto[:600]
                break

    correio = s.select_one('a[href^="mailto:"]')
    if correio:
        p.email = correio["href"][7:].split("?")[0]

    if not p.nome:
        p.erro = "sem nome no perfil"
    return p


def coletar_quirks(edicoes: list[str] | None = None, *,
                   verbose: bool = True) -> list[Participante]:
    saida: list[Participante] = []
    for edicao in (edicoes or list(QUIRKS_EDICOES)):
        if verbose:
            print(f"  Quirk's {edicao}")
        try:
            urls = listar_quirks(edicao, verbose=verbose)
        except Exception as exc:
            print(f"      falhou: {type(exc).__name__}: {exc}")
            continue
        for i, url in enumerate(urls, 1):
            try:
                p = extrair_quirks(_baixar(url), url, edicao)
            except Exception as exc:
                p = Participante(evento="Quirk's Event", edicao=edicao, url_perfil=url,
                                 fonte="thequirksevent.com", coletado_em=_agora(),
                                 erro=f"{type(exc).__name__}: {exc}"[:120])
            saida.append(p)
            if verbose and (i % 20 == 0 or i == len(urls)):
                print(f"      [{i:>3}/{len(urls)}] {p.nome[:30]:30} | "
                      f"{p.tipo_participacao:24} | {p.nivel_patrocinio}")
    return saida


# --------------------------------------------------------------------------
# 2. IIeX  (greenbook.org/events/iiex-*)
# --------------------------------------------------------------------------
#
# A pagina /partners de cada edicao ja traz nome, nivel e o site da empresa
# num unico cartao, entao nao ha perfil a visitar: uma requisicao por edicao
# resolve. Isso tambem evita qualquer chance de esbarrar em /iiex/.

GREENBOOK = "https://www.greenbook.org"

IIEX_EDICOES = {
    "iiex-north-america": ("IIeX North America", "United States"),
    "iiex-europe": ("IIeX Europe", "Netherlands"),
    "iiex-asia-pacific": ("IIeX Asia Pacific", ""),
    "iiex-latam": ("IIeX Latin America", ""),
    "iiex-ai": ("IIeX AI", "United States"),
    "iiex-west": ("IIeX West", "United States"),
}

# Rotulos que a Greenbook usa para presenca fisica no salao.
_IIEX_EXPOSITOR = {"exhibit", "exhibit+", "kiosk", "tech demo", "startup"}


def extrair_iiex(html: str, url: str, chave: str) -> list[Participante]:
    nome_evento, pais = IIEX_EDICOES.get(chave, (chave, ""))
    s = BeautifulSoup(html, "html.parser")

    # O ano esta no h1 ("2026 IIEX North America Partners"). Ler do titulo em
    # vez de fixar no codigo evita que a base envelheca em silencio quando a
    # Greenbook virar a pagina para a edicao seguinte. Quando o h1 nao traz
    # ano, o rotulo do menu ("2026 Partners") serve de segunda fonte.
    #
    # A pagina da LatAm nao tem nenhum dos dois e cita 2025 e 2026 no corpo.
    # Nesse caso o campo fica vazio: escolher um dos dois seria chutar, e um
    # ano errado num sinal de "orcamento deste ano" e pior que ano nenhum.
    h1 = s.find("h1")
    m = re.search(r"(20\d{2})", _limpar(h1.get_text()) if h1 else "")
    if not m:
        for a in s.select("a[href]"):
            m = re.match(r"(20\d{2})\s+Partners", _limpar(a.get_text()))
            if m:
                break
    ano = m.group(1) if m else ""

    # Classes sao CSS modules com hash no meio ("Partner-module-scss-module__
    # xzPd9a__partner"). Casar por trecho estavel das pontas sobrevive a um
    # rebuild do site, que troca so o hash.
    cartoes = s.select('div[class*="Partner-module"][class*="__partner"]')
    saida: list[Participante] = []
    for c in cartoes:
        tag = c.select_one('[class*="__tag"]')
        nome = c.select_one('[class*="__name"]')
        img = c.find("img")
        # North America e West escrevem o nome num <p>; Europe, LatAm e AI
        # mostram so o logo e guardam o nome no alt. Sem esse plano B as tres
        # edicoes saiam com nome vazio e a deduplicacao as colapsava em uma
        # linha so, o que passa despercebido porque nao levanta erro nenhum.
        texto_nome = _limpar(nome.get_text()) if nome else _limpar(
            img.get("alt") if img else "")
        nivel = _limpar(tag.get_text()) if tag else ""
        p = Participante(
            nome=texto_nome,
            nivel_patrocinio=nivel, evento=nome_evento, edicao=nome_evento,
            ano=ano, pais=pais, url_fonte=url, fonte="greenbook.org/events",
            coletado_em=_agora())

        # Primeiro link do cartao e o site da empresa; o segundo, quando
        # existe, aponta para o perfil dela no diretorio da Greenbook.
        for a in c.select("a[href]"):
            href = a.get("href", "")
            if "greenbook.org" in href:
                p.url_perfil = p.url_perfil or href
            elif href.startswith("http") and not p.site:
                alvo = href.split("?")[0]
                p.site = alvo if _site_valido(alvo) else ""

        baixo = nivel.lower()
        if baixo in _IIEX_EXPOSITOR:
            p.tipo_participacao = "expositor"
        elif baixo in _NIVEIS_NAO_COMERCIAIS:
            p.tipo_participacao = "parceiro"
        else:
            p.tipo_participacao = "patrocinador"
        saida.append(p)
    return saida


def coletar_iiex(edicoes: list[str] | None = None, *,
                 verbose: bool = True) -> list[Participante]:
    saida: list[Participante] = []
    for chave in (edicoes or list(IIEX_EDICOES)):
        url = f"{GREENBOOK}/events/{chave}/partners"
        try:
            regs = extrair_iiex(_baixar(url), url, chave)
        except Exception as exc:
            print(f"  IIeX {chave}: falhou {type(exc).__name__}: {exc}")
            continue
        if verbose:
            niveis = sorted({r.nivel_patrocinio for r in regs})
            print(f"  IIeX {chave:20} {len(regs):3} empresas | niveis: {', '.join(niveis)}")
        saida.extend(regs)
    return saida


# --------------------------------------------------------------------------
# 3. MRMW  (eu / apac / mena / na .mrmw.net)
# --------------------------------------------------------------------------

MRMW_REGIOES = {
    "eu": ("MRMW Europe", "sponsorship", "Germany"),
    "apac": ("MRMW Asia Pacific", "sponsorship", ""),
    "mena": ("MRMW MENA", "sponsors", "United Arab Emirates"),
    "na": ("MRMW North America", "sponsorship", "United States"),
}


def extrair_mrmw(html: str, url: str, regiao: str) -> list[Participante]:
    nome_evento, _, pais = MRMW_REGIOES.get(regiao, (regiao, "", ""))
    s = BeautifulSoup(html, "html.parser")

    # O titulo do bloco diz o ano ("Our 2026 Sponsors and Partners"). Quando
    # diz "Our Past Sponsors" o ano fica vazio de proposito: registrar um ano
    # inventado seria pior do que registrar nenhum.
    m = re.search(r"Our\s+(20\d{2})", _limpar(s.get_text(" ", strip=True)))
    ano = m.group(1) if m else ""

    saida: list[Participante] = []
    for card in s.select("div.sponsor-card"):
        tipo = card.select_one(".sponsor-type")
        nome = card.select_one(".sponsor-name")
        img = card.find("img")
        # .sponsor-name some em alguns cards; o alt do logo e o reserva.
        texto_nome = _limpar(nome.get_text()) if nome else _limpar(img.get("alt") if img else "")
        nivel = _limpar(tipo.get_text()) if tipo else ""
        link = card.find("a", href=True)
        p = Participante(
            nome=texto_nome, nivel_patrocinio=nivel, evento=nome_evento,
            edicao=nome_evento, ano=ano, pais=pais, url_fonte=url,
            fonte="mrmw.net", coletado_em=_agora())
        alvo = link["href"].split("?")[0] if link else ""
        if alvo.startswith("http") and "mrmw.net" not in alvo and _site_valido(alvo):
            p.site = alvo
        p.tipo_participacao = ("parceiro" if "partner" in nivel.lower()
                               else "patrocinador")
        saida.append(p)
    return saida


def coletar_mrmw(regioes: list[str] | None = None, *,
                 verbose: bool = True) -> list[Participante]:
    saida: list[Participante] = []
    for regiao in (regioes or list(MRMW_REGIOES)):
        nome_evento, caminho, _ = MRMW_REGIOES[regiao]
        url = f"https://{regiao}.mrmw.net/{caminho}/"
        try:
            regs = extrair_mrmw(_baixar(url), url, regiao)
        except Exception as exc:
            print(f"  MRMW {regiao}: falhou {type(exc).__name__}: {exc}")
            continue
        if verbose:
            anos = {r.ano for r in regs if r.ano}
            print(f"  MRMW {nome_evento:22} {len(regs):2} registros | ano {anos or '?'}")
        saida.extend(regs)
    return saida


# --------------------------------------------------------------------------
# 4. TMRE  (informaconnect.com/tmre)
# --------------------------------------------------------------------------
#
# React renderizado no servidor: o HTML cru ja tem a lista inteira. A pagina
# de listagem agrupa por nivel; o perfil de cada empresa traz site e
# descricao. Vale as duas voltas porque o perfil e a unica fonte do site.

TMRE = "https://informaconnect.com"
TMRE_LISTA = f"{TMRE}/tmre/sponsor-exhibitor-list/"

_TMRE_NIVEL = re.compile(
    r"^(Platinum|Gold|Silver|Bronze|Copper|Diamond|Title|Premier|Media|Learning|"
    r"Association|Exhibitor)s?\b.*(Sponsor|Partner|Exhibitor)s?$", re.I)


def listar_tmre(*, verbose: bool = True) -> dict[str, str]:
    """
    URL de perfil -> nivel, lido da pagina de listagem.

    O nivel vem do cabecalho da secao onde o link aparece, entao a leitura e
    sequencial: cada <h*> de nivel passa a valer para os links seguintes.
    """
    html = _baixar(TMRE_LISTA)
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style", "nav", "header", "footer"]):
        t.decompose()

    nivel_atual = ""
    perfis: dict[str, str] = {}
    for el in s.find_all(["h1", "h2", "h3", "h4", "h5", "p", "a", "span", "div"]):
        if el.name == "a":
            href = el.get("href", "")
            if "/tmre/sponsors/" in href:
                perfis.setdefault(urljoin(TMRE, href.split("?")[0]), nivel_atual)
            continue
        # so o texto proprio do elemento, senao um <div> pai devolveria a
        # pagina inteira e todo link herdaria o primeiro nivel encontrado
        proprio = _limpar("".join(el.find_all(string=True, recursive=False)))
        if proprio and _TMRE_NIVEL.match(proprio):
            nivel_atual = proprio
    if verbose:
        print(f"      {len(perfis)} perfis unicos na lista TMRE")
    return perfis


def extrair_tmre(html: str, url: str, nivel: str) -> Participante:
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style", "nav", "header", "footer"]):
        t.decompose()

    p = Participante(nivel_patrocinio=nivel, evento="TMRE", edicao="Denver",
                     cidade="Denver", pais="United States", url_perfil=url,
                     url_fonte=TMRE_LISTA, fonte="informaconnect.com/tmre",
                     coletado_em=_agora())

    # Precisa ser a classe semantica e nao "o primeiro h2": o primeiro h2 da
    # pagina e o texto institucional da Informa, que entrava como nome em
    # todos os 66 registros e virava um unico patrocinador na deduplicacao.
    cab = s.select_one("h2.c-person-header-section__company")
    p.nome = _limpar(cab.get_text()) if cab else ""
    if not p.nome and s.title:
        p.nome = _limpar(s.title.get_text()).split("|")[0]

    texto = s.get_text("\n", strip=True)
    m = re.search(r"(20\d{2})", texto)
    p.ano = m.group(1) if m else ""
    m2 = re.search(r"Profile\n(.{60,900}?)(?:\nRegister Now|\nView Agenda|\Z)", texto, re.S)
    if m2:
        p.descricao = _limpar(m2.group(1))[:600]

    # O link do site tem o dominio como rotulo ("aytm.com"). Preferir esse
    # padrao evita capturar informa.com e os links de registro do evento.
    for a in s.select("a[href^=http]"):
        href = a["href"].split("?")[0]
        if "informa" in href or "themarketresearchevent" in href:
            continue
        rotulo = _limpar(a.get_text())
        if rotulo and re.match(r"^[\w.-]+\.[a-z]{2,}$", rotulo, re.I) \
                and _site_valido(href):
            p.site = href
            break

    baixo = nivel.lower()
    if "exhibitor" in baixo and "sponsor" not in baixo:
        p.tipo_participacao = "expositor"
    elif "media" in baixo or "learning" in baixo or "association" in baixo:
        p.tipo_participacao = "parceiro"
    else:
        p.tipo_participacao = "patrocinador"
    if not p.nome:
        p.erro = "sem nome no perfil"
    return p


def coletar_tmre(*, verbose: bool = True) -> list[Participante]:
    try:
        perfis = listar_tmre(verbose=verbose)
    except Exception as exc:
        print(f"  TMRE: falhou a listagem {type(exc).__name__}: {exc}")
        return []
    saida: list[Participante] = []
    itens = sorted(perfis.items())
    for i, (url, nivel) in enumerate(itens, 1):
        try:
            p = extrair_tmre(_baixar(url), url, nivel)
        except Exception as exc:
            p = Participante(evento="TMRE", url_perfil=url, nivel_patrocinio=nivel,
                             fonte="informaconnect.com/tmre", coletado_em=_agora(),
                             erro=f"{type(exc).__name__}: {exc}"[:120])
        saida.append(p)
        if verbose and (i % 20 == 0 or i == len(itens)):
            print(f"      [{i:>3}/{len(itens)}] {p.nome[:30]:30} | {p.nivel_patrocinio}")
    return saida


# --------------------------------------------------------------------------
# 5. Insights Association CRC  (insightsassociation.org)
# --------------------------------------------------------------------------

IA_CRC = ("https://www.insightsassociation.org/Events/"
          "CRC-September-15-17-Chicago/Exhibitors-Sponsors")


def extrair_ia(html: str, url: str) -> list[Participante]:
    s = BeautifulSoup(html, "html.parser")
    saida: list[Participante] = []
    for rotulo in s.select("h4.logoTag"):
        nivel = _limpar(rotulo.get_text())
        # as linhas de logo vem depois do cabecalho, ate o proximo cabecalho
        for irmao in rotulo.find_parent("div", class_="row").find_next_siblings("div"):
            if irmao.select_one("h4.logoTag"):
                break
            for a in irmao.select("a[href]"):
                # O alt das imagens desta pagina esta trocado em varios casos
                # (dois logos diferentes com alt="Full Circle"). O atributo
                # title acompanha o href e e o unico consistente, entao ele
                # manda e o alt entra so como reserva.
                img = a.find("img")
                nome = _limpar(a.get("title") or (img.get("alt") if img else ""))
                href = a.get("href", "").split("?")[0]
                if not nome:
                    continue
                p = Participante(
                    nome=nome, nivel_patrocinio=nivel,
                    tipo_participacao=("expositor" if "exhibitor" in nivel.lower()
                                       else "patrocinador"),
                    evento="IA Corporate Researchers Conference (CRC)",
                    edicao="Chicago", ano="2026", cidade="Chicago",
                    pais="United States", url_fonte=url,
                    fonte="insightsassociation.org", coletado_em=_agora())
                if href.startswith("http") and "insightsassociation.org" not in href \
                        and _site_valido(href):
                    p.site = href
                saida.append(p)
    return saida


def coletar_ia(*, verbose: bool = True) -> list[Participante]:
    try:
        regs = extrair_ia(_baixar(IA_CRC), IA_CRC)
    except Exception as exc:
        print(f"  IA CRC: falhou {type(exc).__name__}: {exc}")
        return []
    if verbose:
        print(f"  IA CRC Chicago 2026: {len(regs)} registros")
    return regs


# --------------------------------------------------------------------------
# 6. MRS Annual Conference  (mrsannualconference.com)
# --------------------------------------------------------------------------
#
# Congresso da Market Research Society, o unico da lista sediado no Reino
# Unido. Vale a pena porque quase nao repete a base americana: os
# patrocinadores sao agencias e paineis europeus.

MRS_CONF = "https://www.mrsannualconference.com"
MRS_SPONSORS = f"{MRS_CONF}/sponsors"


def listar_mrs(*, verbose: bool = True) -> dict[str, str]:
    """URL de perfil -> nivel, lido dos <h3> que separam as faixas de logo."""
    html = _baixar(MRS_SPONSORS)
    s = BeautifulSoup(html, "html.parser")
    bloco = s.select_one("div.main_content.sponsors") or s
    nivel = ""
    perfis: dict[str, str] = {}
    for el in bloco.children:
        if getattr(el, "name", None) == "h3":
            nivel = _limpar(el.get_text())
        elif getattr(el, "name", None) == "div":
            a = el.find("a", href=True)
            if a and "/sponsor/id/" in a["href"]:
                perfis.setdefault(urljoin(MRS_CONF, a["href"]), nivel)
    if verbose:
        print(f"      {len(perfis)} perfis unicos na lista MRS")
    return perfis


def extrair_mrs(html: str, url: str, nivel: str) -> Participante:
    s = BeautifulSoup(html, "html.parser")
    p = Participante(nivel_patrocinio=nivel, evento="MRS Annual Conference",
                     edicao="London", ano="2026", cidade="London",
                     pais="United Kingdom", url_perfil=url,
                     url_fonte=MRS_SPONSORS, fonte="mrsannualconference.com",
                     coletado_em=_agora())

    h = s.select_one("div.main_content h1, div.main_content h2, h1")
    p.nome = _limpar(h.get_text()) if h else ""
    if not p.nome and s.title:
        p.nome = _limpar(s.title.get_text()).split("|")[0]

    # O site vem do link cujo rotulo e a propria URL. Pegar link externo
    # qualquer traria mrs.org.uk e as redes sociais do organizador.
    for a in s.select("a[href^=http]"):
        href = a["href"].split("?")[0]
        rotulo = _limpar(a.get_text())
        if rotulo.startswith("http") and "mrs.org.uk" not in href \
                and "mrsannualconference" not in href and _site_valido(href):
            p.site = href
            break

    corpo = s.select_one("div.main_content")
    if corpo:
        texto = _limpar(corpo.get_text(" ", strip=True))
        texto = re.sub(r"^.*?Programme\s*", "", texto)
        p.descricao = texto[:600]

    p.tipo_participacao = ("expositor" if "exhibitor" in nivel.lower()
                           else "patrocinador")
    if not p.nome:
        p.erro = "sem nome no perfil"
    return p


def coletar_mrs(*, verbose: bool = True) -> list[Participante]:
    try:
        perfis = listar_mrs(verbose=verbose)
    except Exception as exc:
        print(f"  MRS: falhou a listagem {type(exc).__name__}: {exc}")
        return []
    saida: list[Participante] = []
    itens = sorted(perfis.items())
    for i, (url, nivel) in enumerate(itens, 1):
        try:
            p = extrair_mrs(_baixar(url), url, nivel)
        except Exception as exc:
            p = Participante(evento="MRS Annual Conference", url_perfil=url,
                             nivel_patrocinio=nivel, fonte="mrsannualconference.com",
                             coletado_em=_agora(),
                             erro=f"{type(exc).__name__}: {exc}"[:120])
        saida.append(p)
        if verbose and (i % 10 == 0 or i == len(itens)):
            print(f"      [{i:>3}/{len(itens)}] {p.nome[:30]:30} | {p.nivel_patrocinio}")
    return saida


# --------------------------------------------------------------------------
# Consolidacao e exportacao
# --------------------------------------------------------------------------

COLUNAS = [
    "nome", "site", "email", "tipo_participacao", "nivel_patrocinio",
    "evento", "edicao", "ano", "cidade", "pais", "estande", "descricao",
    "url_perfil", "url_fonte", "fonte", "coletado_em", "erro",
]


def deduplicar(regs: list[Participante]) -> list[Participante]:
    """
    Uma linha por (evento, edicao, empresa).

    Nao deduplica entre eventos de proposito: a mesma empresa patrocinando
    Quirk's, IIeX e TMRE no mesmo ano e o sinal mais forte da base, e colapsar
    isso numa linha destruiria justamente essa leitura.
    """
    vistos: dict[tuple[str, str, str], Participante] = {}
    for i, p in enumerate(regs):
        # Registro sem nome recebe chave propria. Agrupar todos os vazios sob
        # a mesma chave transforma uma falha de extracao em "1 patrocinador",
        # que e um numero plausivel e por isso nao chama atencao no resumo.
        alvo = _normalizar_nome(p.nome) or f"__sem_nome_{i}"
        chave = (p.evento, p.edicao, alvo)
        anterior = vistos.get(chave)
        if anterior is None:
            vistos[chave] = p
            continue
        # mantem o registro mais completo; nivel de patrocinio tem prioridade
        if (len(anterior.nivel_patrocinio), bool(anterior.site)) < \
           (len(p.nivel_patrocinio), bool(p.site)):
            vistos[chave] = p
    return list(vistos.values())


def exportar(regs: list[Participante], nome: str = "congressos") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(p) for p in regs], ensure_ascii=False, indent=1),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for p in regs:
            d = asdict(p)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc


def coletar_tudo(*, verbose: bool = True) -> list[Participante]:
    regs: list[Participante] = []
    print("[1/6] Quirk's Event")
    regs += coletar_quirks(verbose=verbose)
    print("\n[2/6] IIeX (Greenbook)")
    regs += coletar_iiex(verbose=verbose)
    print("\n[3/6] MRMW")
    regs += coletar_mrmw(verbose=verbose)
    print("\n[4/6] TMRE")
    regs += coletar_tmre(verbose=verbose)
    print("\n[5/6] Insights Association CRC")
    regs += coletar_ia(verbose=verbose)
    print("\n[6/6] MRS Annual Conference")
    regs += coletar_mrs(verbose=verbose)
    return deduplicar(regs)
