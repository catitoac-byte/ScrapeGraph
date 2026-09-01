"""
Extrator dos institutos filiados ao ADM (Arbeitskreis Deutscher Markt- und
Sozialforschungsinstitute e.V.), em adm-ev.de.

Conformidade: o robots.txt do ADM tem duas linhas Disallow. A primeira,
`/wp-content/uploads/_pda/*`, aparece ANTES de qualquer `User-agent:` e por
isso nao pertence a grupo nenhum; a segunda, dentro do grupo `User-agent: *`,
e um `Disallow:` vazio, que libera o site inteiro. Ainda assim toda URL passa
por `permitido()` antes da requisicao, e nada sob `_pda/` e tocado.

As fichas sao renderizadas no servidor, entao HTTP puro basta. Cada ficha traz
endereco, telefone, e-mail e site num unico bloco `ul.contact`, o que evita
capturar por engano os contatos da propria associacao, que ficam no rodape de
todas as paginas.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.adm-ev.de"
LISTAGEM = f"{BASE}/der-adm/unsere-mitglieder/"
SITEMAP = f"{BASE}/member-sitemap.xml"
PAIS = "Germany"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Contatos do proprio ADM, presentes no rodape de toda ficha. Mesmo com a
# extracao restrita ao bloco ul.contact, mantemos a rede de seguranca: um
# ajuste de layout no site nao pode virar 80 registros com o e-mail da
# associacao.
_DOMINIO_ASSOCIACAO = ("adm-ev.de", "rat-marktforschung.de",
                       "deutschlands-marktforscher.de", "cleverreach.com")

_ESPACOS = re.compile(r"[ \t ]+")
# Endereco alemao: o CEP de 5 digitos vem ANTES da cidade ("10115 Berlin").
_CEP_CIDADE = re.compile(r"^(\d{5})\s+(.+)$")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", (t or "").replace("­", "")).strip()


def _decodificar(bruto: bytes, ctype: str) -> str:
    """
    Escolhe a codificacao pelo cabecalho, depois pela meta tag, e so entao
    tenta utf-8 e latin-1.

    Motivo: paginas alemas usam umlaut e ss. Decodificar utf-8 como latin-1
    grava "Nuernberg" como "NÃ¼rnberg" sem estourar exceccao nenhuma, e o
    nome corrompido so aparece la na frente, no CSV.
    """
    candidatos: list[str] = []
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        candidatos.append(m.group(1))
    m = re.search(rb'charset=["\']?([\w-]+)', bruto[:2048], re.I)
    if m:
        candidatos.append(m.group(1).decode("ascii", "ignore"))
    candidatos += ["utf-8", "latin-1"]

    for enc in candidatos:
        try:
            return bruto.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return bruto.decode("utf-8", errors="replace")


# Espera entre tentativas, em segundos. O Apache do ADM devolve 403 esporadico
# em URLs que respondem 200 poucos segundos depois; um 403 isolado e recusa de
# momento, nao veredito sobre a ficha. Sem essa insistencia a coleta perde
# institutos validos e a perda passa despercebida.
_ESPERA_RETENTATIVA = (0, 5, 10, 20, 30)


def _baixar(url: str, *, timeout: int = 40) -> str:
    """Baixa uma pagina, repetindo em falha transitoria."""
    if not robots_permitido(url, agente=UA):
        raise PermissionError("robots.txt proibe")

    cabecalhos = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
    }
    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, headers=cabecalhos), timeout=timeout) as r:
                return _decodificar(r.read(4_000_000), r.headers.get("Content-Type", ""))
        except HTTPError as exc:
            ultimo = exc
            if exc.code in (404, 410):  # ausencia real, nao adianta insistir
                break
        except (URLError, TimeoutError, OSError) as exc:
            ultimo = exc
    raise ultimo if ultimo else RuntimeError("falha desconhecida")


@dataclass
class Instituto:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    cep: str = ""
    cidade: str = ""
    descricao: str = ""
    tipo_filiacao: str = ""      # ordentliches / assoziiertes Mitglied
    ano_fundacao: str = ""
    direcao: str = ""
    funcionarios: str = ""
    associacoes: str = ""
    metodos: str = ""
    setores: str = ""
    temas: str = ""
    unidades: str = ""
    coletado_em: str = ""
    erro: str = ""


def listar_institutos(*, verbose: bool = True) -> list[tuple[str, str]]:
    """
    URLs de ficha com o tipo de filiacao declarado pelo ADM.

    A pagina de membros separa em "Ordentliche Mitglieder" e "Assoziierte
    Mitglieder"; o member-sitemap.xml traz mais URLs que a pagina. As extras
    entram como candidatas e sao filtradas depois, na extracao: ficha sem
    bloco de contato e sem link na listagem e residuo (perfil antigo de
    empresa renomeada), nao membro novo.
    """
    sopa = BeautifulSoup(_baixar(LISTAGEM), "html.parser")

    listados: dict[str, str] = {}
    for h in sopa.find_all(["h2", "h3"]):
        titulo = _limpar(h.get_text())
        if "Mitglieder" not in titulo:
            continue
        bloco = h.find_parent(class_=lambda c: c and "block-members" in c)
        if bloco is None:
            continue
        for a in bloco.select('a[href*="/member/"]'):
            listados.setdefault(a["href"].split("?")[0].rstrip("/") + "/", titulo)

    if verbose:
        print(f"      {len(listados)} fichas na pagina de membros")

    try:
        xml = _baixar(SITEMAP)
        do_sitemap = {u.rstrip("/") + "/" for u in re.findall(r"<loc>(.*?)</loc>", xml)}
    except Exception as exc:
        do_sitemap = set()
        if verbose:
            print(f"      sitemap indisponivel ({type(exc).__name__}), seguindo so pela pagina")

    extras = sorted(do_sitemap - set(listados))
    if verbose and extras:
        print(f"      +{len(extras)} no sitemap sem link na listagem, a verificar")

    return ([(u, listados[u]) for u in sorted(listados)]
            + [(u, "") for u in extras])


def _texto_endereco(li) -> list[str]:
    """Linhas do endereco, separadas pelos <br> do bloco de contato."""
    bruto = li.get_text("\n", strip=True)
    return [_limpar(l) for l in bruto.split("\n") if _limpar(l)]


def extrair_instituto(html: str, url: str, tipo_filiacao: str = "") -> Instituto:
    reg = Instituto(url_perfil=url, tipo_filiacao=tipo_filiacao,
                    coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    titulo = sopa.select_one(".block-member-title h1")
    reg.nome = _limpar(titulo.get_text()) if titulo else ""

    contato = sopa.select_one("ul.contact")
    if contato is None:
        reg.erro = "ficha sem bloco de contato"
        return reg

    endereco = contato.select_one("li.contact__address")
    if endereco is not None:
        linhas = _texto_endereco(endereco)
        # A primeira linha as vezes repete a razao social (ex.: a ficha "SAGO"
        # abre com "Schlesinger Group Germany GmbH"). Ela e informacao de
        # empresa, nao de logradouro, entao sai do endereco.
        if len(linhas) > 2 and not re.match(r"^\d", linhas[0]) and \
                not re.search(r"(stra(ss|ß)e|str\.|weg|platz|allee|ring|damm|gasse|ufer)",
                              linhas[0], re.I):
            reg.nome = reg.nome or linhas[0]
            linhas = linhas[1:]
        for linha in linhas:
            m = _CEP_CIDADE.match(linha)
            if m:
                reg.cep, reg.cidade = m.group(1), _limpar(m.group(2))
        reg.endereco = ", ".join(linhas)

    for a in contato.select("a[href]"):
        href = a["href"].strip()
        alvo = href.lower()
        texto = _limpar(a.get_text())

        if alvo.startswith("tel:"):
            # o texto visivel preserva a formatacao alema; o href e so digitos
            reg.telefone = reg.telefone or texto or href[4:]
            continue

        # Alguns cadastros publicam o e-mail como link http ("horizoom" tem
        # href="http://sales@horizoom.de"). Sem esta checagem o endereco vira
        # site invalido E o e-mail se perde, os dois erros de uma vez. O texto
        # visivel do link e o desempate confiavel.
        candidato = href[7:].split("?")[0].strip() if alvo.startswith("mailto:") else ""
        if not candidato and _EMAIL.match(texto):
            candidato = texto
        elif not candidato:
            sem_esquema = re.sub(r"^[a-z]+://", "", href, flags=re.I).rstrip("/")
            if _EMAIL.match(sem_esquema):
                candidato = sem_esquema

        if candidato:
            if not any(d in candidato.lower() for d in _DOMINIO_ASSOCIACAO):
                reg.email = reg.email or candidato
        elif alvo.startswith("http") and not any(d in alvo for d in _DOMINIO_ASSOCIACAO):
            reg.site = reg.site or href

    perfil = sopa.select_one(".block-member-profile")
    if perfil is not None:
        texto = re.sub(r"^\s*Profil\s*", "", perfil.get_text(" ", strip=True))
        reg.descricao = _limpar(texto)[:1200]

    fatos = {}
    for item in sopa.select(".block-member-facts .facts__item"):
        rotulo = _limpar(item.select_one(".facts__description").get_text()
                         if item.select_one(".facts__description") else "")
        valor = _limpar(item.select_one(".facts__text").get_text()
                        if item.select_one(".facts__text") else "")
        if rotulo:
            fatos[rotulo.rstrip(":").lower()] = valor
    reg.ano_fundacao = fatos.get("gründungsjahr", "")
    reg.direcao = fatos.get("geschäftsführung", "")
    reg.associacoes = fatos.get("mitgliedschaften", "")
    reg.funcionarios = (fatos.get("festangestellte mitarbeiter*innen")
                        or fatos.get("festangestellte mitarbeiter") or "")

    # Standorte / Methoden / Branchen / Themen ficam lado a lado em colunas
    # irmas dentro do mesmo bloco. A leitura precisa ser por coluna: subir ate
    # um ancestral comum mistura as quatro listas num campo so.
    rotulos = {"standorte": "unidades", "methoden": "metodos",
               "branchen": "setores", "themen": "temas"}
    for coluna in sopa.select(".block-member-attributes .attributes__column"):
        cabeca = coluna.find(["h2", "h3"])
        campo = rotulos.get(_limpar(cabeca.get_text()).lower() if cabeca else "")
        if not campo:
            continue
        itens = [i for li in coluna.select("li") if (i := _limpar(li.get_text()))]
        if itens:
            setattr(reg, campo, " | ".join(dict.fromkeys(itens)))

    if not reg.nome:
        reg.erro = "ficha sem nome"
    return reg


# Pausa entre fichas. O minimo do projeto e 1,5s, mas nesse ritmo o Apache do
# ADM comeca a devolver 403 em quase toda requisicao, e cada ficha passa a
# custar tres ou quatro tentativas com espera longa. Em 4s o servidor responde
# 200 de primeira: a coleta inteira fica MAIS rapida e o site recebe menos
# requisicoes do que com a pausa curta.
DELAY_PADRAO = 4.0


def coletar(alvos: list[tuple[str, str]], *, delay: float = DELAY_PADRAO,
            verbose: bool = True) -> list[Instituto]:
    institutos: list[Instituto] = []
    total = len(alvos)
    for i, (url, tipo) in enumerate(alvos, 1):
        try:
            reg = extrair_instituto(_baixar(url), url, tipo)
        except Exception as exc:
            reg = Instituto(url_perfil=url, tipo_filiacao=tipo,
                            erro=f"{type(exc).__name__}: {exc}"[:150],
                            coletado_em=datetime.now(timezone.utc).isoformat())
        institutos.append(reg)
        if verbose:
            print(f"  [{i:>3}/{total}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:36]:36} | {reg.email[:30]:30} | {reg.cidade[:16]}")
        if i < total:
            time.sleep(delay)
    return institutos


def util(reg: Instituto) -> bool:
    """
    Mantem so ficha de instituto de verdade.

    Quem esta linkado na pagina de membros fica, mesmo sem contato publicado:
    a SINUS tem `<ul class="contact">` vazio no site do ADM, e descartar um
    membro declarado por causa disso perderia nome e filiacao em silencio.

    Ja as URLs que so existem no sitemap precisam provar que sao empresa, e
    site sozinho nao prova: exigimos e-mail, telefone ou endereco. E assim que
    caem o perfil antigo da empresa renomeada (sem contato nenhum) e a ficha
    da DGOF, que e sociedade cientifica parceira, nao fornecedora de pesquisa.
    """
    if reg.erro or not reg.nome:
        return False
    if reg.tipo_filiacao:
        return True
    return bool(reg.email or reg.telefone or reg.endereco)


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "cep", "cidade",
           "descricao", "tipo_filiacao", "ano_fundacao", "direcao", "funcionarios",
           "associacoes", "metodos", "setores", "temas", "unidades",
           "url_perfil", "erro"]


def exportar(institutos: list[Instituto], nome: str = "adm") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(i) for i in institutos], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig porque o Excel em maquina alema abre utf-8 sem BOM como
    # latin-1 e transforma "Nurnberg" em lixo.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for i in institutos:
            d = asdict(i)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
