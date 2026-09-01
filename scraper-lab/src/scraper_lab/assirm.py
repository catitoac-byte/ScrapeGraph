"""
Extrator do elenco de aziende associate da ASSIRM (assirm.it/aziende/).

O robots.txt do site tem dois grupos `User-agent: *`: o primeiro proibe
/wp-admin/, tres pastas do WooCommerce e as URLs com `?add-to-cart=`; o
segundo, gerado pelo Yoast, traz um `Disallow:` vazio, que nao libera nada
alem do que ja estava liberado. Nada do diretorio de associadas cai nessas
regras, mas o verificador confirma URL a URL antes de cada requisicao.

Paginas renderizadas no servidor: HTTP puro basta, sem navegador.

Duas armadilhas especificas deste site:

1. Bilinguismo. Cada ficha existe em italiano (/aziende_associate/slug/) e
   em ingles (/en/aziende_associate/slug-2/). O CMS declara 125 posts, que
   sao as 63 fichas italianas mais 62 traducoes. Coletamos so as italianas,
   que sao as unicas linkadas no diretorio.

2. Slug nao acompanha renome de empresa. "WPP Media" mora em /groupm/,
   "CIRCANA" em /iri-information-resources/, "Bilendi" em
   /via-part-of-bilendi/. Por isso o vinculo nome-ficha vem sempre do href
   da listagem, nunca de casamento por nome ou por slug.
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
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

# Reaproveitamos o decodificador de e-mail do Cloudflare ja validado na ABEP.
from scraper_lab.abep import decodifica_cfemail
from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.assirm.it"
LISTAGEM = f"{BASE}/aziende/"

# As tres categorias de socio moram na mesma pagina, trocadas por querystring.
# O rotulo entra no registro porque separa empresa de pesquisa (ordinari) de
# cliente/entidade (istituzionali, sostenitori).
ABAS = {
    "ordinari": "Associato ordinario",
    "istituzionali": "Associato istituzionale",
    "sostenitori": "Associato sostenitore",
}

# O CMS expoe o custom post type das associadas; usamos o cabecalho
# X-WP-Total so para conferir o total coletado contra a contagem do site.
API_CPT = f"{BASE}/wp-json/wp/v2/aziende_associate"

PAIS = "Italy"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Contatos da propria ASSIRM, que aparecem no rodape de toda pagina. Nunca
# tocamos o rodape (so lemos o bloco da ficha), mas o filtro fica como rede
# de seguranca contra mudanca de template.
_DOMINIO_ASSOCIACAO = "assirm.it"
_TELEFONE_ASSOCIACAO = {"390258315750", "0258315750", "0258315750"}

_ESPACOS = re.compile(r"[ \t ]+")
_VAZIOS = {"", "-", "--", "n/a", "na", "nd", "n.d.", "/"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# CAP italiano (5 digitos) seguido da cidade fecha o endereco.
_CAP_CIDADE = re.compile(r"(\d{5})\s+([^\d,;]{2,40})$")
_PERFIL_IT = re.compile(rf"^{re.escape(BASE)}/aziende_associate/[^/]+/$")


def _limpar(texto: str | None) -> str:
    """Normaliza espacos e acentuacao; devolve vazio para placeholders."""
    t = _ESPACOS.sub(" ", (texto or "").replace("​", "")).strip()
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    # NFC evita que "è" decomposto (e + U+0300) vire uma empresa diferente
    # de "è" composto na hora de deduplicar ou cruzar bases.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


def _so_digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "")


def _baixar(url: str, timeout: int = 40) -> str:
    """
    Requisicao unica do modulo. Toda URL passa pelo verificador de robots
    antes de sair, inclusive as da API do CMS.
    """
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")
    req = Request(url, headers={"User-Agent": UA,
                                "Accept-Language": "it-IT,it;q=0.9,en;q=0.6"})
    with urlopen(req, timeout=timeout) as r:
        bruto = r.read(4_000_000)
        # O site declara UTF-8, mas lemos o charset do cabecalho em vez de
        # assumir: um dia de manutencao em latin-1 quebraria "Areté" e
        # "Tecnè" sem erro nenhum, so com caractere trocado.
        ctype = r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    codec = m.group(1) if m else "utf-8"
    try:
        return bruto.decode(codec, errors="replace")
    except LookupError:
        return bruto.decode("utf-8", errors="replace")


def _total_declarado() -> int | None:
    """
    Total de posts do CPT segundo o proprio CMS. Vale como conferencia, nao
    como fonte: o numero inclui as traducoes em ingles.
    """
    url = f"{API_CPT}?per_page=1&_fields=id"
    if not robots_permitido(url, agente=UA):
        return None
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=30) as r:
            r.read(2000)
            return int(r.headers.get("X-WP-Total", 0)) or None
    except Exception:
        # Conferencia indisponivel nao invalida a coleta; so deixa de somar.
        return None


@dataclass
class Associada:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    razao_social: str = ""
    tipo_associado: str = ""
    cidade: str = ""
    cap: str = ""
    fax: str = ""
    attestato: str = ""
    fundacao: str = ""
    capital_social: str = ""
    outras_sedes: str = ""
    gruppo_dirigente: str = ""
    especializacoes: str = ""
    coletado_em: str = ""
    erro: str = ""
    emails_extras: list[str] = field(default_factory=list)


def _proprio_da_associacao(email: str = "", telefone: str = "") -> bool:
    """E-mail ou telefone institucional da ASSIRM, que nao pertence a ficha."""
    if email and email.lower().endswith("@" + _DOMINIO_ASSOCIACAO):
        return True
    return bool(telefone) and _so_digitos(telefone) in _TELEFONE_ASSOCIACAO


def _perfis_da_pagina(html: str) -> list[str]:
    """Fichas italianas linkadas numa aba da listagem, sem repeticao."""
    sopa = BeautifulSoup(html, "html.parser")
    achados: list[str] = []
    for a in sopa.select("a[href]"):
        href = (a.get("href") or "").split("?")[0].split("#")[0]
        # /en/aziende_associate/... e traducao da mesma empresa: fora.
        if _PERFIL_IT.match(href) and href not in achados:
            achados.append(href)
    return achados


def listar_associadas(*, delay: float = 1.6, verbose: bool = True) -> list[tuple[str, str]]:
    """
    Pares (url_da_ficha, tipo_de_associado) das tres abas da listagem.

    A listagem nao pagina: as tres abas juntas trazem o elenco inteiro, e o
    total confere com o CPT do CMS. Mesmo assim, uma aba vazia e tratada
    como suspeita e refeita uma vez antes de virar veredito, porque render
    lento ou erro transitorio nao e ausencia de dado.
    """
    pares: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for i, (chave, rotulo) in enumerate(ABAS.items()):
        url = f"{LISTAGEM}?tipo={chave}"
        if i:
            time.sleep(delay)
        perfis = _perfis_da_pagina(_baixar(url))
        if not perfis:
            time.sleep(delay * 2)
            perfis = _perfis_da_pagina(_baixar(url))
        if verbose:
            print(f"      {rotulo:26} {len(perfis):>3} fichas")
        for u in perfis:
            # Uma empresa pode aparecer em mais de uma aba; a primeira
            # ocorrencia manda, e as abas vao da categoria mais alta a mais
            # baixa na ordem de ABAS.
            if u not in vistos:
                vistos.add(u)
                pares.append((u, rotulo))
    return pares


_ROTULO_CONTATO = re.compile(r"^\s*(Telefono|Tel|Fax|E-?mail|Mail)\s*:", re.I)


def _bloco_contato(bloco) -> object | None:
    """
    Paragrafo com endereco e canais, achado por qualquer rotulo de contato.

    Procurar so por "Telefono:" derrubava as fichas que publicam apenas
    e-mail (Ales, GfK, Toluna, PREDICTA, Pharma Data Factory): sem o
    paragrafo, perdiamos tambem o endereco, que mora na primeira linha dele.
    A posicao do paragrafo varia conforme a ficha tenha ou nao attestato e
    logo, entao a busca e pelo rotulo, nunca pelo indice.
    """
    for p in bloco.find_all("p"):
        if p.find("strong", string=_ROTULO_CONTATO):
            return p
    return None


def _linhas(no) -> list[str]:
    """
    Texto de um no com <br> virando quebra de linha.

    O separador de get_text e vazio de proposito: o rotulo mora num <strong>
    e o valor no texto seguinte, entao qualquer separador jogaria
    "Telefono:" e "02 3057321" em linhas diferentes e o par se perderia.
    """
    copia = BeautifulSoup(str(no), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    return [l.strip() for l in copia.get_text("").split("\n") if l.strip()]


_ROTULOS = {"telefono": "telefone", "tel": "telefone", "fax": "fax",
            "email": "email", "e-mail": "email", "mail": "email"}


def _extrair_contato(bloco, reg: Associada) -> None:
    p = _bloco_contato(bloco)
    if p is None:
        return
    for linha in _linhas(p):
        m = re.match(r"^(Telefono|Tel|Fax|E-?mail|Mail)\s*:\s*(.*)$", linha, re.I)
        if m:
            campo = _ROTULOS[m.group(1).lower().replace("-", "")]
            valor = _limpar(m.group(2))
            if valor and not getattr(reg, campo):
                setattr(reg, campo, valor)
        elif not reg.endereco:
            # Primeira linha sem rotulo e o endereco da sede.
            reg.endereco = _limpar(linha)

    # E-mail pode vir como link mailto ou ofuscado pelo Cloudflare; o texto
    # cru so aparece quando o site nao aplicou nenhuma das duas protecoes.
    if not reg.email:
        oculto = p.find(class_="__cf_email__")
        if oculto is not None and oculto.get("data-cfemail"):
            reg.email = decodifica_cfemail(oculto["data-cfemail"])
    if not reg.email:
        link = p.find("a", href=re.compile(r"^mailto:", re.I))
        if link:
            reg.email = link["href"][7:].split("?")[0]

    if _proprio_da_associacao(email=reg.email):
        reg.email = ""
    if _proprio_da_associacao(telefone=reg.telefone):
        reg.telefone = ""


_FIM_SEDES = re.compile(r"Fondata nel|Capitale Sociale", re.I)


def _extrair_sedes(bloco) -> str:
    """
    Texto que segue o titulo "Altre sedi" ate o bloco de dados societarios.

    O corte e por posicao dentro do texto, nao por paragrafo: em fichas com
    <p> mal fechado o parser junta a filial e os dados societarios no mesmo
    no, e parar no paragrafo inteiro descartaria a filial junto.
    """
    marco = bloco.find("strong", string=re.compile(r"^\s*Altre sedi", re.I))
    if marco is None:
        return ""
    partes: list[str] = []
    vistos: set[str] = set()
    for irmao in marco.find_parent("p").find_next_siblings("p"):
        texto = _limpar(irmao.get_text(" ", strip=True))
        corte = _FIM_SEDES.search(texto)
        if corte:
            texto = _limpar(texto[:corte.start()])
            if texto and texto not in vistos:
                partes.append(texto)
            break
        # O mesmo endereco costuma aparecer duplicado por causa dos <p>
        # aninhados; guardamos so a primeira ocorrencia.
        if texto and texto not in vistos:
            vistos.add(texto)
            partes.append(texto)
    return " | ".join(partes)[:500]


_MARCA = "\x00"


def _extrair_descricao(sopa) -> tuple[str, str, str]:
    """
    Divide o corpo da ficha em (descricao, gruppo dirigente, especializacoes).

    O corpo e uma sequencia de <p> cortada por <h2> ("Gruppo dirigente",
    "Specializzazioni"). Nao da para caminhar so pelos filhos diretos: em
    varias fichas o texto foi colado do Word com <p> sem fechamento, e o
    parser aninha os paragrafos uns dentro dos outros, enterrando o <h2>
    quatro niveis abaixo. Por isso achatamos a arvore com marcadores e
    fatiamos o texto linearmente, o que independe do formato do HTML.
    """
    alvo = sopa.find("div", class_="desc-istituti")
    if alvo is None:
        return "", "", ""

    copia = BeautifulSoup(str(alvo), "html.parser")
    for t in copia(["script", "style", "noscript", "h1"]):
        t.decompose()
    for h in copia.find_all(["h2", "h3", "h4"]):
        h.replace_with(f"\n{_MARCA}{_limpar(h.get_text(' ', strip=True)).lower()}{_MARCA}\n")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    for tag in copia.find_all(["p", "div", "li", "tr"]):
        tag.insert_before("\n")
        tag.insert_after("\n")

    # Separador vazio preserva o espaco que o proprio HTML ja tem entre
    # elementos inline; qualquer outro separador colaria ou picotaria frases.
    secoes: dict[str, list[str]] = {"": []}
    atual = ""
    for linha in copia.get_text("").split("\n"):
        linha = _limpar(linha)
        if not linha:
            continue
        if linha.startswith(_MARCA) and linha.endswith(_MARCA):
            atual = linha.strip(_MARCA)
            secoes.setdefault(atual, [])
            continue
        secoes[atual].append(linha)

    def junta(chave: str, limite: int) -> str:
        for k, v in secoes.items():
            if chave in k:
                return " | ".join(v)[:limite]
        return ""

    descricao = _ESPACOS.sub(" ", " ".join(secoes.get("", [])))[:900]
    return descricao, junta("gruppo dirigente", 400), junta("specializzazioni", 600)


def extrair_associada(html: str, url: str, tipo: str = "") -> Associada:
    reg = Associada(url_perfil=url, tipo_associado=tipo,
                    coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    curto = sopa.select_one("article h1.hideDesktopTitle")
    legal = sopa.select_one("article h1.hideMobileTitle")
    reg.nome = _limpar(curto.get_text() if curto else "")
    reg.razao_social = _limpar(legal.get_text() if legal else "")
    if not reg.nome:
        h1 = sopa.select_one("article h1")
        reg.nome = _limpar(h1.get_text() if h1 else "") or reg.razao_social

    bloco = sopa.find("div", class_="info-istituto")
    if bloco is None:
        reg.erro = "bloco info-istituto ausente"
    else:
        _extrair_contato(bloco, reg)
        reg.outras_sedes = _extrair_sedes(bloco)

        texto = _limpar(bloco.get_text("\n", strip=True))
        for campo, padrao in (("attestato", r"Attestato n\.?\s*\n?([^\n]+)"),
                              ("fundacao", r"Fondata nel\s*([0-9]{4})"),
                              # Exige digito: fichas sem capital declarado
                              # trazem so "Capitale Sociale €  i.v.".
                              ("capital_social", r"Capitale Sociale\s*([^\n]*\d[^\n]*?)\s*i\.v\.")):
            m = re.search(padrao, texto, re.I)
            if m:
                setattr(reg, campo, _limpar(m.group(1)))

        # Site: unico link externo do bloco. "VAI ALLE NEWS" aponta para o
        # proprio dominio da associacao e fica de fora.
        for a in bloco.select('a[href^="http"]'):
            href = a["href"].strip()
            if _DOMINIO_ASSOCIACAO in href:
                continue
            reg.site = href
            break
        if not reg.site:
            # Algumas fichas digitam o endereco do site como texto solto,
            # sem virar link (PREDICTA: "www.predicta.company"). O olhar
            # negativo para "@" evita capturar o dominio de um e-mail.
            m = re.search(r"(?<![@\w.])(www\.[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
                          r"(?:/\S*)?)", bloco.get_text(" ", strip=True))
            if m and _DOMINIO_ASSOCIACAO not in m.group(1):
                reg.site = "https://" + m.group(1)

        # E-mails adicionais publicados no bloco (ex.: sede secundaria).
        extras = []
        for v in _EMAIL.findall(bloco.get_text(" ", strip=True)):
            v = v.lower()
            if v != reg.email.lower() and not _proprio_da_associacao(email=v) \
                    and v not in extras:
                extras.append(v)
        reg.emails_extras = extras[:3]

    if reg.endereco:
        m = _CAP_CIDADE.search(reg.endereco)
        if m:
            reg.cap, reg.cidade = m.group(1), _limpar(m.group(2))

    reg.descricao, reg.gruppo_dirigente, reg.especializacoes = _extrair_descricao(sopa)

    if not reg.nome and not reg.erro:
        reg.erro = "sem nome na ficha"
    return reg


def coletar(pares: list[tuple[str, str]], *, delay: float = 1.6,
            verbose: bool = True) -> list[Associada]:
    """
    Percorre as fichas com pausa minima entre requisicoes.

    Um erro de rede vira campo `erro` na linha e uma segunda tentativa, e
    nunca a conclusao de que a empresa nao tem dado: timeout e falha de
    transporte, nao ausencia de informacao.
    """
    saida: list[Associada] = []
    for i, (url, tipo) in enumerate(pares, 1):
        reg = None
        for tentativa in (1, 2):
            try:
                reg = extrair_associada(_baixar(url), url, tipo)
                break
            except Exception as exc:
                motivo = f"{type(exc).__name__}: {exc}"[:140]
                if tentativa == 2:
                    reg = Associada(url_perfil=url, tipo_associado=tipo,
                                    erro=motivo,
                                    coletado_em=datetime.now(timezone.utc).isoformat())
                else:
                    time.sleep(delay * 2)
        saida.append(reg)
        if verbose:
            print(f"  [{i:>3}/{len(pares)}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:32]:32} | {reg.email[:30]:30} | {reg.cidade[:14]}")
        if i < len(pares):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "razao_social", "email", "site", "pais", "telefone", "fax",
           "endereco", "cidade", "cap", "tipo_associado", "attestato",
           "fundacao", "capital_social", "outras_sedes", "gruppo_dirigente",
           "especializacoes", "descricao", "emails_extras", "url_perfil", "erro"]


def exportar(registros: list[Associada], nome: str = "assirm") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(r) for r in registros], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for r in registros:
            d = asdict(r)
            d["emails_extras"] = " | ".join(d.get("emails_extras") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
