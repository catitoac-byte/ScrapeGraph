"""
Extrator das empresas do BVM (Berufsverband Deutscher Markt- und
Sozialforscher e.V.), a associacao alema de pesquisa de mercado.

O BVM publica os fornecedores em dois lugares complementares, e nenhum dos
dois sozinho da uma base decente:

1. marktforschungsanbieter.de, o portal de anbieter do proprio BVM (linkado
   em bvm.org). E uma SPA em React cujo conteudo vem de uma API REST publica
   em api.marktforschungsanbieter.de/wp-json/bvm/v1. Traz endereco, telefone,
   e-mail e site de todo mundo. Ler o HTML da SPA devolveria pagina vazia; a
   API devolve o registro completo em duas requisicoes.
2. bvm.org/mitgliedschaft/bvm-firmenmitglieder/, a lista de firmas associadas.
   So publica NOMES, e apenas de quem autorizou, mas inclui dezenas de
   institutos que nao pagam anuncio no portal.

Conformidade com robots.txt, tres dominios envolvidos:
  - www.bvm.org tem 10 regras Disallow, duas delas com curinga sobre a query
    (`/*&no_cache` e `/*&tx_kesearch`). Elas proibem justamente as URLs de
    busca do TYPO3, entao a listagem NAO passa pela busca do site: usamos a
    pagina estatica de firmenmitglieder. O urllib.robotparser diria que essas
    URLs estao liberadas, por isso a checagem usa scraper_lab.robots.
  - marktforschungsanbieter.de e api.marktforschungsanbieter.de liberam tudo.
Toda URL, sem excecao, passa por `permitido()` antes da requisicao.

Fica de fora a secao "Nachfrager/Betriebliche Marktforschungsabteilungen" da
pagina de associadas: sao Deutsche Bahn, Telekom, Tchibo e afins, ou seja,
departamentos que COMPRAM pesquisa. Nao sao empresas de pesquisa de mercado e
poluiriam a base.
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
from urllib.parse import quote
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

PORTAL = "https://marktforschungsanbieter.de"
API = "https://api.marktforschungsanbieter.de/wp-json/bvm/v1"
FIRMENMITGLIEDER = "https://www.bvm.org/mitgliedschaft/bvm-firmenmitglieder/"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# A API rejeita per_page acima de 100 com HTTP 400.
POR_PAGINA = 50

# O portal e alemao, mas a filiacao nao exige sede na Alemanha: ha associada
# com endereco na Espanha. O pais sai do registro, nunca fixo.
_PAISES = {"deutschland": "Germany", "österreich": "Austria", "osterreich": "Austria",
           "schweiz": "Switzerland", "spanien": "Spain", "frankreich": "France",
           "niederlande": "Netherlands", "italien": "Italy",
           "vereinigtes königreich": "United Kingdom", "polen": "Poland"}

# Slug de categoria usado na URL publica do portal. O rotulo com barra e
# espaco ("Datenmanagement / IT-Dienstleister") nao vira slug por
# transliteracao simples, entao o mapa e explicito.
_SLUG_CATEGORIA = {
    "Forschungsinstitute": "forschungsinstitute",
    "Feld-Dienstleister": "feld-dienstleister",
    "Berater": "berater",
    "Studios": "studios",
    "Datenmanagement / IT-Dienstleister": "datenmanagement-it",
}

_ESPACOS = re.compile(r"\s+")
# Formas juridicas e sufixos geograficos que atrapalham o casamento de nomes
# entre as duas fontes ("YouGov" no portal, "YouGov Deutschland GmbH" na lista).
_RUIDO_NOME = re.compile(
    r"\b(gmbh|mbh|ag|kg|ohg|se|e\.?k\.?|e\.?v\.?|ug|co|und|deutschland|germany|group)\b")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", (t or "")).strip()


def _normalizar_site(site: str) -> str:
    """
    Garante esquema no endereco do site.

    Duas fichas do portal publicam so o host ("www.quotapoint.de"). Sem
    "https://" a coluna nao serve para requisicao nem para comparar dominio
    com as outras bases, e o defeito passa despercebido porque o campo parece
    preenchido.
    """
    site = _limpar(site)
    if site and not re.match(r"^[a-z][a-z0-9+.-]*://", site, re.I):
        return "https://" + site
    return site


def _normalizar_nome(nome: str) -> str:
    """Nome reduzido a letras e digitos, para comparar as duas fontes."""
    t = unicodedata.normalize("NFKD", nome.lower().replace("ß", "ss"))
    t = t.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", _RUIDO_NOME.sub(" ", t))


def _decodificar(bruto: bytes, ctype: str) -> str:
    """
    Resolve a codificacao pelo cabecalho, depois pela meta tag, e so entao
    tenta utf-8 e latin-1.

    Paginas alemas usam umlaut e ss. Ler utf-8 como latin-1 grava "Nurnberg"
    como "NÃ¼rnberg" sem erro nenhum, e o nome corrompido so aparece no CSV.
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


_ESPERA_RETENTATIVA = (0, 4, 10, 20)


def _baixar(url: str, *, timeout: int = 40) -> str:
    """Baixa uma URL ja aprovada pelo robots, insistindo em falha transitoria."""
    if not robots_permitido(url, agente=UA):
        raise PermissionError("robots.txt proibe")

    cabecalhos = {"User-Agent": UA,
                  "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                  "Accept-Language": "de-DE,de;q=0.9,en;q=0.7"}
    ultimo: Exception | None = None
    for espera in _ESPERA_RETENTATIVA:
        if espera:
            time.sleep(espera)
        try:
            with urlopen(Request(url, headers=cabecalhos), timeout=timeout) as r:
                return _decodificar(r.read(6_000_000), r.headers.get("Content-Type", ""))
        except HTTPError as exc:
            ultimo = exc
            if exc.code in (400, 404, 410):
                break
        except (URLError, TimeoutError, OSError) as exc:
            ultimo = exc
    raise ultimo if ultimo else RuntimeError("falha desconhecida")


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = "Germany"
    telefone: str = ""
    endereco: str = ""
    cep: str = ""
    cidade: str = ""
    descricao: str = ""
    categoria: str = ""
    membro_bvm: str = ""
    origem: str = ""
    ano_fundacao: str = ""
    funcionarios: str = ""
    metodos: str = ""
    setores: str = ""
    servicos: str = ""
    associacoes: str = ""
    coletado_em: str = ""
    erro: str = ""


def _url_perfil(registro: dict) -> str:
    categorias = registro.get("categories") or []
    slug_cat = _SLUG_CATEGORIA.get(categorias[0] if categorias else "", "forschungsinstitute")
    return f"{PORTAL}/{slug_cat}/{quote(registro.get('slug') or str(registro.get('id')))}"


def listar_portal(*, delay: float = 1.6, verbose: bool = True) -> list[dict]:
    """
    Todos os registros do portal de anbieter, via API.

    A paginacao so para depois de DUAS paginas vazias seguidas. Uma pagina
    vazia isolada pode ser hipo do backend, e parar nela truncaria a lista sem
    erro visivel. O total declarado pela API e devolvido junto para conferencia
    contra o que foi efetivamente coletado.
    """
    registros: list[dict] = []
    pagina, vazias, total_declarado = 1, 0, None

    while vazias < 2 and pagina <= 40:
        dados = json.loads(_baixar(f"{API}/search?page={pagina}&per_page={POR_PAGINA}"))
        if total_declarado is None:
            total_declarado = dados.get("total")
        itens = dados.get("results") or []
        vazias = vazias + 1 if not itens else 0
        registros += [i.get("source") or {} for i in itens]
        if verbose:
            print(f"      pagina {pagina:>2}: {len(itens):>2} registros "
                  f"(acumulado {len(registros)}/{total_declarado})")
        pagina += 1
        time.sleep(delay)

    if verbose and total_declarado is not None and len(registros) != total_declarado:
        print(f"      ATENCAO: coletados {len(registros)}, portal declara {total_declarado}")
    return registros


def extrair_portal(registro: dict) -> Empresa:
    """Converte um registro cru da API no formato da base."""
    url = _url_perfil(registro)
    e = Empresa(url_perfil=url, origem="portal_anbieter",
                coletado_em=datetime.now(timezone.utc).isoformat())
    e.nome = _limpar(registro.get("name"))
    e.email = _limpar(registro.get("email")).lower()
    e.site = _normalizar_site(registro.get("website") or "")
    e.telefone = _limpar(registro.get("phone"))

    pais = _limpar(registro.get("country"))
    e.pais = _PAISES.get(pais.lower(), pais or "Germany")

    e.cep = _limpar(registro.get("zipcode"))
    e.cidade = _limpar(registro.get("city"))
    rua = _limpar(registro.get("street"))
    # Endereco alemao: CEP antes da cidade ("Alexanderplatz 1, 10115 Berlin").
    partes = [p for p in (rua, f"{e.cep} {e.cidade}".strip(), pais) if p]
    e.endereco = ", ".join(partes)

    e.descricao = _limpar(registro.get("description"))[:1200]
    e.categoria = " | ".join(registro.get("categories") or [])
    e.membro_bvm = "sim" if registro.get("is_bvm_member") else "nao"
    e.ano_fundacao = str(registro.get("foundation_year") or "")
    e.funcionarios = str(registro.get("employees_total") or "")
    e.metodos = " | ".join(registro.get("methods") or [])[:800]
    e.setores = " | ".join(registro.get("sectors") or [])[:800]
    e.servicos = " | ".join(registro.get("services") or [])[:800]
    e.associacoes = " | ".join(registro.get("memberships") or [])

    if not e.nome:
        e.erro = "registro sem nome"
    return e


# Rotulos de secao da pagina de associadas. So "Anbieter" sao fornecedores de
# pesquisa; "Nachfrager" sao os clientes.
_SECAO_FORNECEDOR = "anbieter"


def listar_membros_bvm(*, verbose: bool = True) -> list[str]:
    """Nomes das firmas associadas publicados em bvm.org, so os fornecedores."""
    sopa = BeautifulSoup(_baixar(FIRMENMITGLIEDER), "html.parser")
    principal = sopa.find("main") or sopa.body

    nomes: list[str] = []
    secao = ""
    for el in principal.find_all(["h2", "h3", "h4", "li"]):
        texto = _limpar(el.get_text(" "))
        if el.name != "li":
            secao = texto
            continue
        # os itens de compartilhamento social moram na mesma <ul> do conteudo
        if not texto or texto.startswith("Auf ") or not secao:
            continue
        if _SECAO_FORNECEDOR in secao.lower() and texto not in nomes:
            nomes.append(texto)

    if verbose:
        print(f"      {len(nomes)} fornecedores nomeados em bvm.org")
    return nomes


def _casa(nome: str, indice: dict[str, str]) -> str | None:
    """
    Devolve a chave do portal que corresponde ao nome, se houver.

    Casamento exato depois de normalizar, mais prefixo: o portal usa a marca
    curta ("YouGov", "IfD") e a lista de associadas usa a razao social
    completa ("YouGov Deutschland GmbH"). Prefixos de menos de tres letras
    ficariam ambiguos demais e sao rejeitados.
    """
    n = _normalizar_nome(nome)
    if not n:
        return None
    if n in indice:
        return n
    for chave in indice:
        if len(chave) >= 3 and (n.startswith(chave) or chave.startswith(n)):
            return chave
    return None


def coletar(*, delay: float = 1.6, verbose: bool = True) -> list[Empresa]:
    """
    Base do BVM: portal de anbieter mais os associados que so aparecem por
    nome em bvm.org.

    Dois registros do portal apontam para o mesmo slug porque a empresa se
    inscreveu em duas categorias. Deduplicamos por slug e juntamos as
    categorias, senao a base carrega duplicata exata com telefone e e-mail
    identicos.
    """
    if verbose:
        print("    portal de anbieter (API)")
    brutos = listar_portal(delay=delay, verbose=verbose)

    por_slug: dict[str, Empresa] = {}
    for bruto in brutos:
        empresa = extrair_portal(bruto)
        chave = bruto.get("slug") or empresa.url_perfil
        anterior = por_slug.get(chave)
        if anterior is None:
            por_slug[chave] = empresa
            continue
        categorias = dict.fromkeys(
            filter(None, anterior.categoria.split(" | ") + empresa.categoria.split(" | ")))
        anterior.categoria = " | ".join(categorias)
    empresas = list(por_slug.values())
    if verbose and len(empresas) != len(brutos):
        print(f"      {len(brutos) - len(empresas)} duplicata(s) por slug unificada(s)")

    if verbose:
        print("    lista de firmenmitglieder (bvm.org)")
    try:
        nomes = listar_membros_bvm(verbose=verbose)
    except Exception as exc:
        nomes = []
        if verbose:
            print(f"      lista indisponivel ({type(exc).__name__}), seguindo so com o portal")

    indice = {_normalizar_nome(e.nome): e for e in empresas if e.nome}
    agora = datetime.now(timezone.utc).isoformat()
    novos = 0
    for nome in nomes:
        chave = _casa(nome, indice)
        if chave is not None:
            indice[chave].membro_bvm = "sim"
            continue
        # Sem contato nenhum, mas e um instituto alemao de pesquisa nomeado
        # pela propria associacao: vale como alvo para o enriquecimento, desde
        # que a origem fique explicita na linha.
        empresas.append(Empresa(url_perfil=FIRMENMITGLIEDER, nome=nome,
                                origem="lista_firmenmitglieder", membro_bvm="sim",
                                coletado_em=agora))
        novos += 1
    if verbose:
        print(f"      {len(nomes) - novos} ja no portal, +{novos} so na lista de associadas")
    return empresas


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "cep", "cidade",
           "descricao", "categoria", "membro_bvm", "origem", "ano_fundacao",
           "funcionarios", "metodos", "setores", "servicos", "associacoes",
           "url_perfil", "erro"]


def exportar(empresas: list[Empresa], nome: str = "bvm") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    # utf-8-sig: sem BOM o Excel em maquina alema le o arquivo como latin-1 e
    # corrompe todo umlaut.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
