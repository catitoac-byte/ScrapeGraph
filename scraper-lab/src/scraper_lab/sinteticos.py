"""
Vertical sinteticos: mercado de dados e personas sinteticas em pesquisa.

Cinco varreduras, na ordem do PRD (~/Projetos/dados-sinteticos-abep/
PRD_E_PROMPT_SCRAPEGRAPH.md):

    V4 empresas      quem oferece respondentes, personas, gemeos, simulacao, boost
    V2 personas      como cada oferta constroi e usa a persona
    V3 dados         o que alimenta, o que sai, e os cases sintetico contra real
    V1 metodologias  como se constroi e como se valida, com as diretrizes
    V5 comparacao    derivada das quatro anteriores, sem busca nova

Como o projeto roda sem LLM (LLM_PROVIDER=manual, ver llm.py), a extracao e
feita em duas camadas:

1. Heuristica. Expressoes de verticais/sinteticos.json acham frases nas
   paginas guardadas. A citacao sai recortada do proprio texto, entao e
   literal por construcao. A classificacao feita a partir dela (tipo de
   oferta, base da persona, nivel de validacao) fica marcada "inferido".
2. Fichas. Correcoes escritas a mao (ou por um LLM, quando houver) em
   dados/cache/sinteticos/fichas/<V>/<chave>.json. Sobrepoem a heuristica
   campo a campo e passam pelo mesmo validador.

Buscas tambem sao plugaveis. O provedor "manual" le os resultados que o
operador registrou (raspar_sinteticos.py buscas registrar); BUSCA_PROVIDER=
brave com BRAVE_API_KEY executa sozinho. O teto por varredura vale para
os dois. Resultado de busca so indica onde olhar: nenhum campo nasce de
snippet, so de pagina aberta.

Todo campo tem o mesmo formato:

    {"valor": ..., "tipo": "literal|inferido|not found|not accessible",
     "quote": "...", "url": "...", "data": "AAAA-MM-DD"}
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from scraper_lab.llm import provedor_ativo
from scraper_lab.pipeline import gravar_json, ler_json
from scraper_lab.robots import UA_PADRAO, permitido
from scraper_lab.sinteticos_paginas import (
    CachePaginas,
    Pagina,
    canonica,
    casa_dominio,
    citacao_confere,
    dominio,
    normalizar,
    recortar,
    registravel,
)

RAIZ = Path(__file__).resolve().parents[2]
VERTICAIS = RAIZ / "verticais"
HOJE = date.today().isoformat()
TIPOS = ("literal", "inferido", "not found", "not accessible")
VARREDURAS = ("V4", "V2", "V3", "V1", "V5")
ARQUIVOS = {"V1": "metodologias", "V2": "personas", "V3": "dados", "V4": "empresas", "V5": "comparacao"}


class TetoDeBuscas(RuntimeError):
    """A varredura ja usou todas as buscas que o teto permite."""


# --------------------------------------------------------------------------
# Campos
# --------------------------------------------------------------------------

def campo(valor, tipo: str, url: str, quote: str | None = None, data: str | None = None, **extra) -> dict:
    c: dict = {"valor": valor, "tipo": tipo}
    if quote:
        c["quote"] = quote
    c["url"] = url
    c["data"] = data or HOJE
    c.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return c


def literal(valor, quote: str, pag: Pagina, **extra) -> dict:
    return campo(valor, "literal", pag.url, quote, pag.data, **extra)


def inferido(valor, pag: Pagina, quote: str | None = None, **extra) -> dict:
    return campo(valor, "inferido", pag.url, quote, pag.data, **extra)


def nao_achado(paginas: list[Pagina], **extra) -> dict:
    ok = [p.url for p in paginas if p.ok] or [p.url for p in paginas]
    return campo("not found", "not found", ok[0] if ok else "", urls_verificadas=ok[:8], **extra)


def inacessivel(pag: Pagina) -> dict:
    return campo("not accessible", "not accessible", pag.url, None, pag.data, motivo=pag.motivo)


def _janela(frase: str, m: re.Match, limite: int = 360) -> str:
    """Recorte literal centrado no trecho que casou."""
    if len(frase) <= limite:
        return frase
    ini = max(0, m.start() - 120)
    if ini:
        ini = frase.find(" ", ini) + 1 or ini
    return recortar(frase[ini:], limite)


def achar(paginas: list[Pagina], rx: re.Pattern, *, contexto: re.Pattern | None = None,
          exigir: re.Pattern | None = None, max_: int = 1, ordem: list[str] | None = None):
    """Frases que casam, na ordem das paginas (ou priorizando URLs que
    contenham alguma das palavras de `ordem`)."""
    lista = [p for p in paginas if p.ok]
    if ordem:
        def peso(p: Pagina) -> int:
            caminho = urlparse(p.url).path.lower()
            return next((i for i, w in enumerate(ordem) if w in caminho), len(ordem))
        lista.sort(key=peso)
    achados, vistos = [], set()
    for p in lista:
        for f in p.frases():
            m = rx.search(f)
            if not m:
                continue
            if contexto is not None and not contexto.search(f):
                continue
            if exigir is not None and not exigir.search(f):
                continue
            q = _janela(f, m)
            if q in vistos:
                continue
            vistos.add(q)
            achados.append((q, p, m))
            if len(achados) >= max_:
                return achados
    return achados


# --------------------------------------------------------------------------
# Configuracao e contexto da corrida
# --------------------------------------------------------------------------

def carregar_config(vid: str = "sinteticos") -> dict:
    cfg = json.loads((VERTICAIS / f"{vid}.json").read_text(encoding="utf-8"))
    cfg["_cache"] = RAIZ / "dados" / "cache" / cfg["saida"]
    cfg["_saida"] = RAIZ / "dados" / "saida" / cfg["saida"]
    return cfg


def _expandir(caminho: str) -> Path:
    return Path(os.path.expanduser(caminho))


def _chave_arquivo(chave: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", chave.lower()).strip("-")[:90]


class Corrida:
    def __init__(self, cfg: dict, *, piloto: int | None = None, teto: int | None = None):
        self.cfg = cfg
        self.piloto = piloto
        self._teto = teto
        self.paginas = CachePaginas(cfg["_cache"], cfg.get("bloqueios_conhecidos"))
        self.buscas = RegistroBuscas(cfg["_cache"] / "buscas.json")
        cl = cfg["classificadores"]
        self.rx = {k: re.compile(v, re.I) for k, v in cl.items() if isinstance(v, str)}
        self.rx_oferta = {k: re.compile(v, re.I) for k, v in cl["offer_type"].items()}
        self.rx_base = {k: re.compile(v, re.I) for k, v in cl["base_da_persona"].items()}
        self.inicio = time.time()

    # ---- caminhos
    @property
    def saida(self) -> Path:
        return self.cfg["_saida"] / "piloto" if self.piloto else self.cfg["_saida"]

    def arquivo(self, v: str) -> Path:
        return self.saida / f"{ARQUIVOS[v]}.json"

    def ler(self, v: str) -> dict:
        return ler_json(self.arquivo(v), {})

    def teto(self, v: str) -> int:
        return self._teto if self._teto is not None else int(self.cfg["teto_buscas"].get(v, 55))

    # ---- fichas
    def ficha(self, v: str, chave: str) -> dict:
        return ler_json(self.cfg["_cache"] / "fichas" / v / f"{_chave_arquivo(chave)}.json", {})

    def fichas(self, v: str) -> list[dict]:
        pasta = self.cfg["_cache"] / "fichas" / v
        return [ler_json(a) for a in sorted(pasta.glob("*.json"))] if pasta.exists() else []

    # ---- classificacao de dominio
    def _em(self, url: str, lista: str) -> bool:
        return any(casa_dominio(url, d) for d in self.cfg.get(lista, []))

    def ignorado(self, url: str) -> bool:
        return self._em(url, "dominios_ignorados")

    def tipo_de_fonte(self, url: str, dom_empresas: set[str]) -> str:
        if casa_dominio(url, "arxiv.org") or casa_dominio(url, "ssrn.com") or casa_dominio(url, "ideas.repec.org"):
            return "preprint"
        if self._em(url, "dominios_academicos"):
            return "peer_reviewed"
        if re.search(r"\.(edu|ac\.[a-z]{2})$", dominio(url)):
            return "preprint"
        if self._em(url, "dominios_associacoes"):
            return "associacao"
        if dominio(url) in dom_empresas:
            return "fornecedor"
        if self._em(url, "dominios_imprensa"):
            return "imprensa"
        return "fornecedor" if dominio(url).count(".") <= 1 else "imprensa"

    def meta(self, v: str, tarefa: str, notas: list[str], **extra) -> dict:
        p = provedor_ativo()
        motor = ("manual: heurística de verticais/sinteticos.json mais fichas"
                 if p.nome == "manual" else f"{p.nome}/{p.modelo}")
        m = {
            "tarefa": tarefa,
            "mercado": self.cfg["mercado"],
            "janela": self.cfg["janela"],
            "data_corrida": HOJE,
            "piloto": bool(self.piloto),
            "websearch_calls_used": self.buscas.usadas(v) if v in self.cfg["teto_buscas"] else 0,
            "websearch_budget": self.teto(v) if v in self.cfg["teto_buscas"] else 0,
            "provedor_de_busca": os.getenv("BUSCA_PROVIDER", "manual"),
            "motor_de_extracao": motor,
            "formato_do_campo": "{valor, tipo, quote, url, data}; tipo literal exige quote presente na página guardada; "
                                "inferido é leitura do analista a partir da quote ou da página; not found traz urls_verificadas; "
                                "not accessible traz motivo. category e source do PRD correspondem a valor e url.",
            "notas_metodo": notas,
        }
        m.update(extra)
        return m


# --------------------------------------------------------------------------
# Buscas
# --------------------------------------------------------------------------

class RegistroBuscas:
    """Cada busca executada, com os resultados. O teto conta aqui."""

    def __init__(self, arquivo: Path):
        self.arquivo = arquivo
        self.d: dict[str, list[dict]] = ler_json(arquivo, {})

    def lista(self, v: str) -> list[dict]:
        return self.d.get(v, [])

    def usadas(self, v: str) -> int:
        return len(self.lista(v))

    def feitas(self, v: str) -> set[str]:
        return {b["consulta"] for b in self.lista(v)}

    def pendentes(self, v: str, cfg: dict, teto: int) -> list[tuple[str, str]]:
        """Consultas ainda nao executadas, alternando idiomas para que um teto
        pequeno ja cubra mais de uma lingua."""
        por_idioma = [[(i, q) for q in qs] for i, qs in cfg["consultas"].get(v, {}).items()]
        intercaladas = []
        while any(por_idioma):
            for fila in por_idioma:
                if fila:
                    intercaladas.append(fila.pop(0))
        feitas = self.feitas(v)
        resto = max(0, teto - self.usadas(v))
        return [x for x in intercaladas if x[1] not in feitas][:resto]

    def registrar(self, v: str, consulta: str, idioma: str, resultados: list[dict],
                  teto: int, provedor: str = "manual") -> None:
        lista = self.d.setdefault(v, [])
        existente = next((b for b in lista if b["consulta"] == consulta), None)
        if existente is None and len(lista) >= teto:
            raise TetoDeBuscas(f"{v}: teto de {teto} buscas atingido; '{consulta}' não registrada")
        reg = {"consulta": consulta, "idioma": idioma, "provedor": provedor, "executada_em": HOJE,
               "resultados": [{"url": canonica(r["url"]), "titulo": r.get("titulo", "")}
                              for r in resultados if r.get("url")]}
        if existente is None:
            lista.append(reg)
        else:
            existente.update(reg)
        gravar_json(self.arquivo, self.d)

    def urls(self, v: str | None = None) -> list[tuple[str, str]]:
        """(varredura, url) de todos os resultados registrados."""
        saida = []
        for chave, lista in self.d.items():
            if v and chave != v:
                continue
            for b in lista:
                saida += [(chave, r["url"]) for r in b["resultados"]]
        return saida


def buscar_por_api(corrida: Corrida, v: str) -> int:
    """Executa as consultas pendentes num provedor com chave. Hoje: Brave."""
    prov = os.getenv("BUSCA_PROVIDER", "manual").lower()
    chave = os.getenv("BRAVE_API_KEY", "")
    if prov != "brave" or not chave:
        raise RuntimeError("Busca automática exige BUSCA_PROVIDER=brave e BRAVE_API_KEY no .env. "
                           "Sem isso, use 'buscas pendentes' e 'buscas registrar'.")
    feitas = 0
    for idioma, q in corrida.buscas.pendentes(v, corrida.cfg, corrida.teto(v)):
        req = Request(f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(q)}&count=10",
                      headers={"X-Subscription-Token": chave, "Accept": "application/json"})
        with urlopen(req, timeout=30) as r:
            dados = json.loads(r.read().decode("utf-8"))
        res = [{"url": x["url"], "titulo": x.get("title", "")} for x in dados.get("web", {}).get("results", [])]
        corrida.buscas.registrar(v, q, idioma, res, corrida.teto(v), provedor="brave")
        feitas += 1
        time.sleep(1.1)
    return feitas


# --------------------------------------------------------------------------
# V4 empresas
# --------------------------------------------------------------------------

_PALAVRAS_GENERICAS = {"the", "and", "inc", "ltd", "group", "grupo", "company", "data", "research", "software",
                       "technology", "innovation", "insights", "japan", "digital", "global", "academic", "incl",
                       "synthetic", "audiences", "personas", "persona", "network", "specialist", "researchers"}


def _nome_base(nome: str) -> str:
    """'Market Logic Software (DeepSights Personas)' vira 'Market Logic Software'."""
    return re.split(r"\s+\(|\s+/\s+", nome)[0].strip()


def _fichas_nome(nome: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _nome_base(nome).lower())
            if len(t) >= 3 and t not in _PALAVRAS_GENERICAS]


def _dominio_proprio(nome: str, url: str) -> bool:
    d = dominio(url).replace(".", "").replace("-", "")
    return any(t in d for t in _fichas_nome(nome))


def _home(url: str) -> str:
    p = urlparse(canonica(url))
    return f"{p.scheme}://{p.netloc}/"


def _resolver_dominio(corrida: Corrida, nome: str, url: str) -> tuple[str | None, str]:
    """Dominio da empresa quando a base inicial aponta para uma reportagem.
    Primeiro procura, no proprio artigo, um link externo cujo dominio tenha o
    nome da empresa; depois a tabela sementes_dominio da configuracao."""
    if _dominio_proprio(nome, url):
        return registravel(url), "domínio da URL da base inicial"
    art = corrida.paginas.abrir(url)
    if art.ok:
        for l in art.links:
            if dominio(l["href"]) != dominio(url) and not corrida.ignorado(l["href"]) \
                    and _dominio_proprio(nome, l["href"]):
                return registravel(l["href"]), f"link para o site da empresa no artigo {art.url}"
    tabela = corrida.cfg.get("sementes_dominio", {})
    chave = next((k for k in tabela if _nome_base(nome).lower().startswith(k.lower())), None)
    if chave:
        return tabela[chave], "tabela sementes_dominio da configuração"
    return None, f"artigo {'sem link para o site da empresa' if art.ok else art.estado}"


def empresas_semente(corrida: Corrida) -> tuple[list[dict], list[dict]]:
    """Agrupa a base inicial por empresa. Varias linhas podem ser a mesma
    empresa (duas URLs da Kantar), e muitas URLs sao reportagens, nao o site
    da empresa. Devolve (empresas, ausencias justificadas)."""
    base = json.loads(_expandir(corrida.cfg["sementes"]["empresas"]).read_text(encoding="utf-8"))
    ausentes = corrida.cfg.get("ausencias_conhecidas", {})
    fora = corrida.cfg.get("status_fora_de_v4", {})
    grupos: dict[str, dict] = {}
    puladas = []
    for s in base:
        status = s.get("status", "")
        motivo = ausentes.get(s["name"]) or next((m for k, m in fora.items() if status.startswith(k)), None)
        if motivo or not str(s.get("url", "")).startswith("http"):
            puladas.append({"name": s["name"], "url": s.get("url", ""), "status": status,
                            "motivo": motivo or "sem URL na base inicial"})
            continue
        chave_nome = _nome_base(s["name"]).lower()
        g = grupos.setdefault(chave_nome, {"nome": _nome_base(s["name"]), "sementes": [], "evidencias": []})
        g["sementes"].append(s)
        g["evidencias"].append(canonica(s["url"]))
    empresas = []
    for g in grupos.values():
        dom, como = None, ""
        for u in g["evidencias"]:
            dom, como = _resolver_dominio(corrida, g["nome"], u)
            if dom:
                break
        g["dominio"] = dom or f"sem-dominio-{_chave_arquivo(g['nome'])}"
        g["home"] = f"https://{dom}/" if dom else g["evidencias"][0]
        g["resolucao"] = como
        empresas.append(g)
    return empresas, puladas


def _amostra_piloto(empresas: list[dict], n: int) -> list[dict]:
    """Alterna os grupos da base (startups, incumbentes, internacionais)."""
    grupos: dict[str, list[dict]] = defaultdict(list)
    for e in empresas:
        grupos[e["sementes"][0].get("source_file", "")].append(e)
    filas = [grupos[g] for g in sorted(grupos)]
    saida = []
    while len(saida) < n and any(filas):
        for f in filas:
            if f and len(saida) < n:
                saida.append(f.pop(0))
    return saida


def _forte(corrida: Corrida, p: Pagina) -> list[tuple[str, str]]:
    """Frases da pagina que indicam oferta sintetica: (tipo, frase)."""
    achados = []
    for tipo, rx in corrida.rx_oferta.items():
        for q, _, _ in achar([p], rx, contexto=corrida.rx["contexto"], max_=1):
            achados.append((tipo, q))
    return achados


def descobrir_candidatas(corrida: Corrida, conhecidos: set[str], limite: int | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Novas empresas a partir das listas de terceiros e dos resultados de
    busca registrados. Devolve (aprovadas, descartadas, bloqueados)."""
    cfg = corrida.cfg
    origens: dict[str, set[str]] = defaultdict(set)
    bloqueados, listas = [], []

    def terceiro(u: str) -> bool:
        return corrida._em(u, "dominios_imprensa") or corrida._em(u, "dominios_academicos") \
            or corrida._em(u, "dominios_associacoes")

    def colher_links(p: Pagina, rotulo: str) -> None:
        externos = []
        for l in p.links:
            d = registravel(l["href"])
            if d and d != registravel(p.url) and not corrida.ignorado(l["href"]) and not terceiro(l["href"]) \
                    and d not in externos:
                externos.append(d)
        for d in externos[:40]:
            origens[d].add(rotulo)

    for lista in cfg.get("listas_terceiros", []):
        p = corrida.paginas.abrir(lista["url"])
        if not p.ok:
            bloqueados.append({"url": p.url, "motivo": p.motivo or p.estado, "fonte": lista["nome"]})
            continue
        m = re.search(r"\d+\s+results?\s+in\s+[^.\n]{3,40}", normalizar(p.texto))
        listas.append(literal(m.group(0), m.group(0), p, fonte=lista["nome"]) if m
                      else inferido("lista aberta", p, fonte=lista["nome"]))
        colher_links(p, f"lista: {lista['nome']}")

    for v, url in corrida.buscas.urls():
        if corrida.ignorado(url):
            continue
        if not terceiro(url):
            origens[registravel(url)].add(f"busca {v}")
        if v == "V4" and urlparse(url).path.strip("/"):
            p = corrida.paginas.abrir(url)
            if p.ok:
                colher_links(p, f"artigo: {p.url}")
            elif p.estado == "not accessible":
                bloqueados.append({"url": p.url, "motivo": p.motivo, "fonte": f"resultado de busca {v}"})

    aprovadas, descartadas = [], []
    for d in sorted(origens, key=lambda x: (-len(origens[x]), x)):
        if d in conhecidos:
            continue
        if limite is not None and len(aprovadas) >= limite:
            break
        home = corrida.paginas.abrir(f"https://{d}/")
        if not home.ok:
            descartadas.append({"dominio": d, "origem": sorted(origens[d]),
                                "motivo": f"home {home.estado}: {home.motivo}"})
            continue
        cabeca = " ".join([home.titulo, *home.h1, home.meta.get("description", ""), home.meta.get("og:description", "")])
        sinais = _forte(corrida, home)
        if sinais and corrida.rx["contexto"].search(cabeca):
            aprovadas.append({"nome": (home.meta.get("og:site_name") or re.split(r"\s[|\-–]\s|:\s", home.titulo)[0]).strip()[:80],
                              "home": home.url, "dominio": d, "origem": sorted(origens[d]), "sinais": sinais})
        else:
            descartadas.append({"dominio": d, "origem": sorted(origens[d]),
                                "motivo": "home sem frase de oferta sintética ou sem o tema no título, h1 ou descrição (inferido)"})
    return aprovadas, descartadas, bloqueados, listas


def _sitemap(corrida: Corrida, home: Pagina) -> list[str]:
    """URLs do sitemap.xml do dominio que falam de oferta sintetica."""
    arq = corrida.cfg["_cache"] / "sitemaps.json"
    cache = ler_json(arq, {})
    dom = dominio(home.url_final or home.url)
    if dom not in cache:
        locs: list[str] = []
        fila, visitados = [f"https://{urlparse(home.url_final or home.url).netloc}/sitemap.xml"], 0
        while fila and visitados < 4 and len(locs) < 5000:
            alvo = fila.pop(0)
            visitados += 1
            if not permitido(alvo, agente=UA_PADRAO, silencioso=True):
                continue
            try:
                with urlopen(Request(alvo, headers={"User-Agent": UA_PADRAO}), timeout=20) as r:
                    xml = r.read(5_000_000).decode("utf-8", errors="replace")
            except Exception:
                continue
            achados = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
            if "<sitemapindex" in xml:
                fila += sorted(achados, key=lambda u: (not re.search(r"page|product|solution|post", u), len(u)))[:3]
            else:
                locs += achados
        cache[dom] = locs[:5000]
        gravar_json(arq, cache, indent=0)
    rx = re.compile(corrida.cfg["subpaginas"]["padrao_sitemap"], re.I)
    escolhidas = [canonica(u) for u in cache[dom] if dominio(u) == dom and rx.search(urlparse(u).path)]
    return sorted(dict.fromkeys(escolhidas), key=lambda u: (bool(re.search(r"/blog|/news|/post|/insights", u)), len(u)))[:3]


def paginas_da_empresa(corrida: Corrida, home_url: str, evidencias: list[str] | None = None,
                       extras: list[str] | None = None) -> list[Pagina]:
    home = corrida.paginas.abrir(home_url)
    paginas = [home]
    vistos = {home.url, home.url_final}
    for u in evidencias or []:
        if canonica(u) not in vistos:
            vistos.add(canonica(u))
            paginas.append(corrida.paginas.abrir(u))
    if home.ok:
        teto = corrida.cfg.get("teto_paginas_por_empresa", 8)
        for u in _sitemap(corrida, home):
            if u not in vistos and len(paginas) < teto:
                vistos.add(u)
                paginas.append(corrida.paginas.abrir(u))
        sub = corrida.cfg["subpaginas"]
        rx = re.compile(sub["padrao_link"], re.I)
        prioridade = sub["prioridade"]
        dom = dominio(home.url_final or home.url)
        candidatos = []
        for l in home.links:
            if dominio(l["href"]) != dom or l["href"] in vistos:
                continue
            caminho = urlparse(l["href"]).path.lower()
            if caminho.count("/") > 3 or re.search(r"\.(pdf|png|jpg|zip)$", caminho):
                continue
            alvo = caminho + " " + l["texto"].lower()
            if not rx.search(alvo):
                continue
            peso = next((i for i, w in enumerate(prioridade) if re.search(w, alvo)), len(prioridade))
            candidatos.append((peso, len(caminho), l["href"]))
        for _, _, href in sorted(candidatos):
            if len(paginas) >= teto:
                break
            if href not in vistos:
                vistos.add(href)
                paginas.append(corrida.paginas.abrir(href))
    for e in extras or []:
        if canonica(e) not in vistos:
            vistos.add(canonica(e))
            paginas.append(corrida.paginas.abrir(e))
    return paginas


def _local(corrida: Corrida, texto: str) -> tuple[str, str, str] | None:
    """(chave encontrada, pais, regiao) para o primeiro local conhecido no texto."""
    for chave, (pais, regiao) in sorted(corrida.cfg["locais"].items(), key=lambda x: -len(x[0])):
        if re.search(rf"(?<![\w]){re.escape(chave)}(?![\w])", texto):
            return chave, pais, regiao
    return None


def _jsonld_valores(p: Pagina, chave: str) -> list[str]:
    achados = []

    def andar(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == chave and isinstance(v, (str, int)):
                    achados.append(str(v))
                elif k == chave and isinstance(v, dict) and v.get("name"):
                    achados.append(str(v["name"]))
                else:
                    andar(v)
        elif isinstance(x, list):
            for i in x:
                andar(i)
    andar(p.jsonld)
    return achados


def _sede(corrida: Corrida, paginas: list[Pagina]) -> dict:
    """Frase que diz onde fica a sede vale como literal quando nomeia o pais.
    Endereco solto (rodape, contato, JSON-LD) so permite inferir: pode ser um
    escritorio entre varios."""
    for q, p, m in achar(paginas, corrida.rx["sede"], max_=6):
        mm = corrida.rx["sede"].search(q)
        loc = (_local(corrida, q[mm.start():]) if mm else None) or _local(corrida, q)
        if loc:
            tipo = "literal" if loc[0] == loc[1] else "inferido"
            return campo(loc[1], tipo, p.url, q, p.data, regiao=loc[2],
                         nota=None if tipo == "literal" else f"país inferido de '{loc[0]}'")
    for p in [x for x in paginas if x.ok]:
        for v in _jsonld_valores(p, "addressCountry") + _jsonld_valores(p, "addressLocality"):
            loc = _local(corrida, v)
            if loc:
                return inferido(loc[1], p, v, regiao=loc[2], nota="endereço no JSON-LD da página")
    ordem = sorted([x for x in paginas if x.ok],
                   key=lambda p: (not re.search(r"contact|contato|contacto|about|sobre", p.url), p.url != paginas[0].url))
    for p in ordem:
        for linha in p.texto.split("\n"):
            if 8 <= len(linha) <= 220 and corrida.rx["endereco"].search(linha):
                loc = _local(corrida, linha)
                if loc:
                    return inferido(loc[1], p, linha, regiao=loc[2],
                                    nota="endereço publicado na página; pode ser um dos escritórios")
    return nao_achado(paginas)


def _tipo_empresa(corrida: Corrida, semente: dict | None, home: Pagina, fundacao: dict) -> dict:
    cabeca = " ".join([home.titulo, *home.h1, home.meta.get("description", ""),
                       home.meta.get("og:description", "")])
    corpo = " ".join(home.frases()[:80])
    regras = [
        ("academic", cabeca, r"\buniversit|research\s+lab|\blaborat[oó]rio"),
        ("panel", cabeca, r"\bpanel(ists)?\b|\bpainel\b|\bpanel\s+de\b"),
        ("panel", corpo, r"\d[\d.,]*\s*(m|million|mi|milh[oõ]es)?\s*\+?\s*(panel(ists)?|panel\s+members|painelistas)"),
        ("survey_platform", cabeca, r"survey\s+(platform|software|tool)|experience\s+management|plataforma\s+de\s+pesquisa"),
        ("agency", cabeca, r"\bagency\b|\bag[eê]ncia\b|\bagencia\b"),
        ("consultancy", cabeca, r"\bconsult(ing|ancy)\b|\bconsultoria\b"),
    ]
    for tipo, texto, rx in regras:
        m = re.search(rx, texto, re.I)
        if m:
            return inferido(tipo, home, base=f"página inicial cita '{m.group(0)}'")
    grupo = (semente or {}).get("source_file", "")
    ano = fundacao.get("valor") if fundacao.get("tipo") == "literal" else None
    if grupo == "vendors_incumbents_regional":
        return inferido("incumbent_research", home, base="grupo incumbentes da base inicial")
    if ano and str(ano).isdigit() and int(ano) < 2015:
        return inferido("incumbent_research", home, base=f"fundada em {ano}")
    return inferido("startup", home, base="grupo startups da base inicial" if grupo == "vendors_startups"
                    else "sem sinal de incumbente, painel, plataforma, agência ou consultoria")


_NAO_NOME = {"We", "Our", "The", "Some", "Many", "Leading", "Fortune", "Global", "World", "Best", "Top", "And",
             "With", "From", "For", "All", "More", "Most", "Teams", "Brands", "Companies", "Clients", "Customers",
             "AI", "Read", "Learn", "See", "Join", "Over", "Hundreds", "Thousands", "Including", "Like", "Such",
             "Nossos", "Nuestros", "Os", "Las", "Los", "As", "A", "An", "In", "At", "Of", "To", "I", "It", "This"}


def _clientes(corrida: Corrida, paginas: list[Pagina], nome: str) -> list[dict]:
    """So frase que nomeia clientes, e titulo de pagina de case. Logo nao
    entra: na pratica mistura investidor, imprensa e selo de seguranca."""
    saida = []
    for q, p, m in achar(paginas, corrida.rx["clientes"], max_=6):
        mm = corrida.rx["clientes"].search(q)
        depois = q[mm.end():] if mm else ""
        proprio = set(re.findall(r"\w+", nome))
        nomes = [t for t in re.findall(r"\b[A-Z][\w&'.-]*[\w&]", depois) if t not in _NAO_NOME and t not in proprio]
        if len(nomes) >= 2:
            saida.append(literal(q, q, p, nota="frase da página que nomeia clientes; os nomes estão na quote"))
        if len(saida) >= 3:
            break
    for p in [x for x in paginas if x.ok]:
        if re.search(r"(case-stud(y|ies)|customer-stor(y|ies)|success-stor(y|ies)|/customers|/cases?)/[^/]+", p.url) and p.h1:
            saida.append(literal(p.h1[0], p.h1[0], p, nota="título de página de case de cliente"))
    return saida[:10]


def _video(paginas: list[Pagina]) -> dict:
    rx = re.compile(r"youtube\.com/(embed|watch)|youtu\.be/|vimeo\.com/(video/)?\d|wistia\.(com|net)|loom\.com/(share|embed)|vidyard", re.I)
    for p in [x for x in paginas if x.ok]:
        for u in p.iframes + [l["href"] for l in p.links]:
            if rx.search(u):
                return literal(u, u, p)
    return nao_achado(paginas)


def _imprensa(corrida: Corrida, paginas: list[Pagina]) -> list[dict]:
    saida, vistos = [], set()
    for p in [x for x in paginas if x.ok]:
        for l in p.links:
            u = l["href"]
            if corrida._em(u, "dominios_imprensa") and dominio(u) != dominio(p.url) \
                    and len(urlparse(u).path.strip("/")) > 8 and u not in vistos:
                vistos.add(u)
                saida.append(literal(u, u, p, titulo_link=l["texto"] or None))
    return saida[:8]


def _validacao(corrida: Corrida, paginas: list[Pagina]) -> dict:
    ordem = ["accuracy", "validat", "benchmark", "research", "science", "method", "publication", "case"]
    achados = achar(paginas, corrida.rx["validacao"], contexto=corrida.rx["contexto"],
                    exigir=corrida.rx["validacao_numero"], max_=12, ordem=ordem)

    def nota_frase(a) -> int:
        q = a[0]
        return (2 * bool(corrida.rx["validacao_preferir"].search(q)) + bool("%" in q)
                - 3 * bool(corrida.rx["validacao_evitar"].search(q)))
    achados = sorted(achados, key=nota_frase, reverse=True)[:3]
    if not achados:
        home = next((p for p in paginas if p.ok), paginas[0])
        return campo("none", "inferido", home.url, None, home.data,
                     basis="nenhuma alegação de validação com número nas páginas abertas",
                     level=inferido("none", home), urls_verificadas=[p.url for p in paginas if p.ok][:8])
    q, p, _ = achados[0]
    if corrida.rx["nivel_peer_reviewed"].search(q):
        nivel, base = "peer_reviewed", "a frase cita revisão por pares ou periódico"
    elif corrida.rx["nivel_third_party"].search(q):
        nivel, base = "third_party", "a frase atribui o estudo a terceiro"
    else:
        nivel, base = "self_reported", "número publicado pelo próprio fornecedor"
    outras = [literal(x[0], x[0], x[1]) for x in achados[1:]]
    return campo(q, "literal", p.url, q, p.data, basis=base, level=inferido(nivel, p, q), outras=outras)


def _grounding(corrida: Corrida, paginas: list[Pagina]) -> dict:
    for cat, rx in corrida.rx_base.items():
        r = achar(paginas, rx, contexto=corrida.rx["contexto"], max_=1)
        if r:
            q, p, _ = r[0]
            return inferido(cat, p, q)
    home = next((p for p in paginas if p.ok), paginas[0])
    return campo("not_disclosed", "inferido", home.url, None, home.data,
                 nota="nenhuma frase sobre a base da persona nas páginas abertas",
                 urls_verificadas=[p.url for p in paginas if p.ok][:8])


def _preco(corrida: Corrida, paginas: list[Pagina]) -> dict:
    ok = [p for p in paginas if p.ok]
    de_preco = [p for p in ok if re.search(r"pricing|plans|precos|precios|planos", p.url)]
    r = achar(de_preco, corrida.rx["preco"], max_=2) or \
        achar(ok, corrida.rx["preco"], exigir=corrida.rx["preco_contexto"], max_=2)
    if r:
        return literal(r[0][0], r[0][0], r[0][1], outras=[literal(x[0], x[0], x[1]) for x in r[1:]])
    r = achar(de_preco, corrida.rx["preco_sem_valor"], max_=1)
    if r:
        return literal(r[0][0], r[0][0], r[0][1], nota="página de preço sem valor publicado")
    if de_preco:
        return campo("not found", "not found", de_preco[0].url, None, de_preco[0].data,
                     nota="página de preço aberta sem valor nem convite a falar com vendas")
    return nao_achado(paginas, nota="nenhuma página de preço entre as abertas")


def extrair_empresa(corrida: Corrida, alvo: dict) -> dict:
    """alvo: nome, dominio, home, evidencias, sementes, origem, resolucao."""
    nome, chave = alvo["nome"], alvo["dominio"]
    sementes = alvo.get("sementes") or []
    semente = sementes[0] if sementes else None
    ficha = corrida.ficha("V4", chave)
    paginas = paginas_da_empresa(corrida, alvo["home"], alvo.get("evidencias"), ficha.get("paginas_extras"))
    home = paginas[0]
    reg: dict = {"name": None, "dominio": chave, "url": home.url, "origem": alvo.get("origem", []),
                 "resolucao_do_dominio": alvo.get("resolucao", "")}

    if not any(p.ok for p in paginas):
        na = inacessivel(home)
        for k in ("hq_country", "region", "founded_year", "company_type", "headline_verbatim",
                  "headline_oferta", "grounding", "validation_claim", "pricing", "funding_last", "demo_video_url"):
            reg[k] = na
        reg["name"] = campo(nome, "inferido", home.url, None, home.data,
                            nota="nome da base inicial; página não acessível", motivo=home.motivo)
        reg.update({"offer_type": [na], "named_customers": [], "notable_media": [], "hq_source": home.url})
    else:
        ok = [p for p in paginas if p.ok]
        pag_nome = next((p for p in ok if nome in p.texto_validacao()), None)
        if pag_nome:
            reg["name"] = literal(nome, nome, pag_nome)
        elif home.ok and home.meta.get("og:site_name"):
            reg["name"] = literal(home.meta["og:site_name"], home.meta["og:site_name"], home)
        else:
            reg["name"] = campo(nome, "inferido", ok[0].url, None, ok[0].data, nota="nome da base inicial ou do título")
        sede = _sede(corrida, paginas)
        regiao = sede.pop("regiao", None)
        reg["hq_country"] = sede
        reg["hq_source"] = sede["url"]
        reg["region"] = (campo(regiao, "inferido", sede["url"], None, sede["data"], base=f"região do país {sede['valor']}")
                         if regiao else nao_achado(paginas))
        fund = None
        for p in ok:
            for v in _jsonld_valores(p, "foundingDate"):
                if re.match(r"(19|20)\d\d", v):
                    fund = literal(v[:4], v, p, nota="JSON-LD foundingDate")
                    break
            if fund:
                break
        if not fund:
            r = achar(paginas, corrida.rx["fundacao"], max_=1, ordem=["about", "sobre", "nosotros", "company"])
            fund = literal(r[0][2].group(3), r[0][0], r[0][1]) if r else nao_achado(paginas)
        reg["founded_year"] = fund
        reg["company_type"] = _tipo_empresa(corrida, semente, home if home.ok else ok[0], fund)
        base_h = home if home.ok else ok[0]
        h1 = next((h for h in base_h.h1 if len(h) >= 8), None)
        if h1:
            reg["headline_verbatim"] = literal(h1, h1, base_h, origem_texto="h1")
        elif base_h.meta.get("og:title") or base_h.titulo:
            t = base_h.meta.get("og:title") or base_h.titulo
            reg["headline_verbatim"] = literal(t, t, base_h, origem_texto="og:title ou title")
        else:
            reg["headline_verbatim"] = nao_achado(paginas)
        # pagina da oferta sintetica (evidencia da base inicial ou do sitemap)
        oferta = next((p for p in ok[1:] if p.h1 and corrida.rx["contexto"].search(p.h1[0] + " " + p.titulo)), None)
        reg["headline_oferta"] = (literal(oferta.h1[0], oferta.h1[0], oferta, origem_texto="h1 da página da oferta")
                                  if oferta else nao_achado(paginas))
        ofertas = []
        for tipo, rx in corrida.rx_oferta.items():
            r = achar(paginas, rx, contexto=corrida.rx["contexto"], max_=1)
            if r:
                ofertas.append(inferido(tipo, r[0][1], r[0][0]))
        reg["offer_type"] = ofertas or [nao_achado(paginas)]
        reg["grounding"] = _grounding(corrida, paginas)
        reg["validation_claim"] = _validacao(corrida, paginas)
        reg["pricing"] = _preco(corrida, paginas)
        r = achar(paginas, corrida.rx["financiamento"], max_=1)
        reg["funding_last"] = literal(r[0][0], r[0][0], r[0][1]) if r else nao_achado(paginas)
        reg["named_customers"] = _clientes(corrida, paginas, nome)
        reg["demo_video_url"] = _video(paginas)
        reg["notable_media"] = _imprensa(corrida, paginas)

    reg["source_urls"] = [p.url for p in paginas if p.ok]
    reg["paginas_nao_acessiveis"] = [{"url": p.url, "motivo": p.motivo or p.estado} for p in paginas if not p.ok]
    reg["date_captured"] = HOJE
    reg["sementes"] = [s["name"] for s in sementes]
    if sementes:
        reg["base_inicial"] = [{k: s.get(k) for k in
                                ("name", "url", "hq", "offer", "grounding", "validation_status",
                                 "pricing", "funding", "customers", "status", "source_file")} for s in sementes]
    for k, v in (ficha.get("campos") or {}).items():
        reg[k] = v
    if ficha.get("campos"):
        reg["ficha_aplicada"] = sorted(ficha["campos"])
    return reg


def varrer_v4(corrida: Corrida) -> dict:
    empresas_base, puladas = empresas_semente(corrida)
    fichas = corrida.fichas("V4")
    excluir = {f["chave"]: f["excluir"] for f in fichas if f.get("excluir")}
    if corrida.piloto:
        alvo_base = _amostra_piloto(empresas_base, max(1, corrida.piloto - 2))
        limite_novas = corrida.piloto - len(alvo_base)
    else:
        alvo_base, limite_novas = empresas_base, None
    conhecidos = {e["dominio"] for e in empresas_base}
    aprovadas, descartadas, bloqueados, listas = descobrir_candidatas(corrida, conhecidos, limite_novas)
    for f in fichas:
        if f.get("incluir") and dominio(f["url"]) not in conhecidos \
                and all(a["dominio"] != dominio(f["url"]) for a in aprovadas):
            aprovadas.append({"nome": f.get("nome", dominio(f["url"])), "home": _home(f["url"]),
                              "dominio": dominio(f["url"]), "origem": ["ficha"]})

    alvos = [dict(e, origem=["semente: vendors_all.json"]) for e in alvo_base] + \
            [dict(a, evidencias=[], sementes=[], resolucao="descoberta") for a in aprovadas]
    empresas, vistos = [], set()
    for n, alvo in enumerate(alvos, 1):
        d = alvo["dominio"]
        if d in vistos:
            continue
        vistos.add(d)
        if d in excluir:
            descartadas.append({"dominio": d, "origem": alvo["origem"], "motivo": f"ficha: {excluir[d]}",
                                "sementes": [s["name"] for s in alvo.get("sementes", [])]})
            continue
        print(f"  [{n:>3}/{len(alvos)}] {alvo['nome'][:40]:40} {d}")
        reg = extrair_empresa(corrida, alvo)
        empresas.append(reg)
        for p in reg["paginas_nao_acessiveis"]:
            if p["motivo"].startswith(("HTTP", "robots", "bloqueio")):
                bloqueados.append({"url": p["url"], "motivo": p["motivo"], "fonte": d})

    propria = corrida.cfg.get("empresa_propria")
    if propria and propria["dominio"] not in vistos:
        reg = dict(propria, origem=["empresa própria: verticais/sinteticos.json"], date_captured=HOJE,
                   source_urls=sorted({c["url"] for c in _campos(propria)}), paginas_nao_acessiveis=[],
                   sementes=[], name=campo(propria["name"], "literal", propria["url"], propria["name"]))
        reg.pop("produtos", None)
        reg["produtos"] = propria.get("produtos", [])
        empresas.append(reg)

    saida = {
        "meta": corrida.meta("V4", "V4 empresas: quem oferece respondentes, personas, gêmeos, simulação ou boost", [
            "Sementes: vendors_all.json agrupado por empresa; URL de reportagem vira página de evidência e o domínio da empresa é resolvido pelo link no artigo ou pela tabela sementes_dominio.",
            "Linhas da base com status sem oferta (stance_only, no_public_offering_found, exploring, research, third_party_evidence) ficam fora da V4 com motivo no recall.",
            "Novas empresas vêm das listas de terceiros e dos resultados de busca; só entram se a home tem frase de oferta sintética e o tema aparece no título, h1 ou descrição.",
            "Páginas por empresa: home, evidências da base, até 3 do sitemap com termo sintético e links internos por prioridade, até o teto.",
            "offer_type, grounding, company_type, level e hq por endereço são inferidos; cada um traz a quote literal que o sustenta.",
            "named_customers: só frase que nomeia clientes ou título de página de case; logos não entram.",
            "pricing e funding_last só com valor em frase da página; nada deduzido.",
            "Deduplicado por domínio.",
        ], bloqueados=_dedup(bloqueados), listas_de_terceiros=listas, sementes_puladas=puladas,
            descartadas=descartadas, total=len(empresas)),
        "companies": empresas,
    }
    gravar_json(corrida.arquivo("V4"), saida, indent=2)
    return saida


def _campos(x) -> list[dict]:
    """Todos os campos {valor, tipo, url} dentro de um registro."""
    if isinstance(x, dict):
        proprio = [x] if "tipo" in x and "url" in x else []
        return proprio + [c for v in x.values() for c in _campos(v)]
    if isinstance(x, list):
        return [c for v in x for c in _campos(v)]
    return []


def _dedup(lista: list[dict]) -> list[dict]:
    vistos, saida = set(), []
    for x in lista:
        if x.get("url") and x["url"] not in vistos:
            vistos.add(x["url"])
            saida.append(x)
    return saida


# --------------------------------------------------------------------------
# V2 personas
# --------------------------------------------------------------------------

def _paginas_registradas(corrida: Corrida, reg: dict, v: str) -> list[Pagina]:
    """Paginas que a V4 ja abriu, mais resultados de busca da varredura v no
    mesmo dominio."""
    urls = list(reg.get("source_urls") or [])
    urls += [u for vv, u in corrida.buscas.urls(v) if registravel(u) == reg["dominio"]]
    paginas = []
    for u in dict.fromkeys(urls):
        paginas.append(corrida.paginas.abrir(u))
    return paginas or [corrida.paginas.abrir(reg["url"])]


def varrer_v2(corrida: Corrida) -> dict:
    v4 = corrida.ler("V4")
    if not v4:
        raise RuntimeError("V2 depende de empresas.json. Rode a V4 antes.")
    rx = corrida.rx
    produtos = {s["name"]: s.get("product", "") for s in
                json.loads(_expandir(corrida.cfg["sementes"]["empresas"]).read_text(encoding="utf-8"))}
    ofertas = []
    for reg in v4["companies"]:
        if not any(o.get("tipo") == "inferido" for o in reg.get("offer_type", [])):
            continue
        paginas = _paginas_registradas(corrida, reg, "V2")
        ficha = corrida.ficha("V2", reg["dominio"])
        produto = None
        for nome_produto in [produtos.get(n, "") for n in reg.get("sementes", [])]:
            for p in [x for x in paginas if x.ok]:
                if nome_produto and nome_produto in p.texto_validacao():
                    produto = literal(nome_produto, nome_produto, p, nota="nome do produto da base inicial, achado na página")
                    break
            if produto:
                break
        if produto is None:
            for chave in ("headline_oferta", "headline_verbatim"):
                if (reg.get(chave) or {}).get("tipo") == "literal":
                    produto = reg[chave]
                    break
        produto = produto or nao_achado(paginas)

        def frase(chave: str, ctx: bool = True) -> dict:
            r = achar(paginas, rx[chave], contexto=rx["contexto"] if ctx else None, max_=1,
                      ordem=["how-it-works", "method", "science", "persona", "twin", "synthetic", "product"])
            return literal(r[0][0], r[0][0], r[0][1]) if r else nao_achado(paginas)

        como = frase("como_construida")
        if como["tipo"] == "not found" and reg["grounding"].get("quote"):
            g = reg["grounding"]
            como = campo(g["quote"], "literal", g["url"], g["quote"], g["data"], nota="mesma frase usada no grounding")
        item = {
            "oferta": produto,
            "empresa": reg["name"],
            "dominio": reg["dominio"],
            "tipos_de_oferta": [o["valor"] for o in reg["offer_type"] if o.get("tipo") == "inferido"],
            "como_e_construida": como,
            "base_da_persona": reg["grounding"],
            "granularidade": frase("granularidade"),
            "controle_de_vies": frase("controle_de_vies"),
            "divulgacao_ao_cliente": frase("divulgacao"),
            "url": reg["url"],
            "data": HOJE,
        }
        for k, v in (ficha.get("campos") or {}).items():
            item[k] = v
        ofertas.append(item)

    dom_v4 = {r["dominio"] for r in v4["companies"]}
    novas = sorted({registravel(u) for _, u in corrida.buscas.urls("V2")
                    if registravel(u) not in dom_v4 and not corrida.ignorado(u)
                    and not corrida._em(u, "dominios_imprensa") and not corrida._em(u, "dominios_academicos")})
    saida = {
        "meta": corrida.meta("V2", "V2 personas: como cada oferta constrói e usa a persona sintética", [
            "Uma linha por empresa da V4 com oferta sintética inferida.",
            "Páginas: as que a V4 abriu mais resultados de busca V2 no mesmo domínio.",
            "base_da_persona é a mesma classificação inferida da V4, com a quote que a sustenta.",
            "Domínios novos vindos das buscas V2 ficam em candidatas_para_v4; a próxima corrida da V4 os avalia.",
        ], candidatas_para_v4=novas, total=len(ofertas)),
        "ofertas": ofertas,
    }
    gravar_json(corrida.arquivo("V2"), saida, indent=2)
    return saida


# --------------------------------------------------------------------------
# V3 dados e cases
# --------------------------------------------------------------------------

def _data_publicacao(p: Pagina) -> dict | None:
    for chave in ("citation_publication_date", "citation_date", "article:published_time",
                  "citation_online_date", "dc.date"):
        v = p.meta.get(chave)
        if v and re.match(r"(19|20)\d\d", v):
            return literal(_iso(v), v, p, origem_texto=chave)
    for v in _jsonld_valores(p, "datePublished"):
        if re.match(r"(19|20)\d\d", v):
            return literal(_iso(v), v, p, origem_texto="JSON-LD datePublished")
    m = re.search(r"Submitted on (\d{1,2} \w{3} (19|20)\d\d)", p.texto)
    if m:
        return literal(_iso(m.group(1)), m.group(0), p, origem_texto="arXiv")
    return None


_MESES = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                      "sep", "oct", "nov", "dec"], 1)}


def _iso(v: str) -> str:
    m = re.match(r"((19|20)\d\d)[-/](\d{1,2})(?:[-/](\d{1,2}))?", v)
    if m:
        return f"{m.group(1)}-{int(m.group(3)):02d}" + (f"-{int(m.group(4)):02d}" if m.group(4) else "")
    m = re.match(r"(\d{1,2}) (\w{3})\w* ((19|20)\d\d)", v)
    if m and m.group(2).lower()[:3] in _MESES:
        return f"{m.group(3)}-{_MESES[m.group(2).lower()[:3]]:02d}-{int(m.group(1)):02d}"
    return v[:10]


def _confianca_data(corrida: Corrida, d: dict | None) -> str:
    if not d or d.get("tipo") not in ("literal", "inferido"):
        return "low"
    ini, fim = corrida.cfg["janela"]["inicio"], corrida.cfg["janela"]["fim"]
    return "high" if ini[: len(d["valor"])] <= d["valor"] <= fim else "low"


def _titulo(p: Pagina) -> dict:
    for chave in ("citation_title", "og:title", "dc.title"):
        if p.meta.get(chave):
            return literal(p.meta[chave], p.meta[chave], p, origem_texto=chave)
    if p.h1:
        return literal(p.h1[0], p.h1[0], p, origem_texto="h1")
    if p.titulo:
        return literal(p.titulo, p.titulo, p, origem_texto="title")
    return nao_achado([p])


def _sinal(texto: str) -> str:
    if re.search(r"fail|not\s+really|cannot|can't|worse|poor|overestimat|underestimat|"
                 r"no\s+better|misleading|flatten|bias|did\s+not\s+(match|replicate)", texto, re.I):
        return "negativo_ou_misto"
    return "positivo_ou_neutro"


def extrair_case(corrida: Corrida, p: Pagina, semente: dict | None, empresas: dict[str, dict]) -> dict:
    rx = corrida.rx
    if not p.ok:
        na = inacessivel(p)
        base = {k: na for k in ("titulo", "marca", "fornecedor", "ano", "objetivo", "metodo",
                                "independente_ou_autodeclarado")}
        base.update({"resultado_literal": [na], "url": p.url, "data": p.data, "date_confidence": "low"})
        if semente:
            base["base_inicial"] = {k: semente.get(k) for k in ("title", "company", "vendor", "year", "evidence_type")}
        return base
    texto = p.texto_validacao()

    def nome_na_pagina(nome: str | None, rotulo: str) -> dict:
        if not nome:
            return nao_achado([p])
        candidatos = [nome] + [re.split(r"\s*[(,/]", nome)[0].strip()]
        for c in candidatos:
            if c and len(c) >= 2 and c in texto:
                return literal(c, c, p)
        return campo("not found", "not found", p.url, None, p.data,
                     nota=f"base inicial cita '{nome}' como {rotulo}; nome não confirmado na página")

    marca = nome_na_pagina((semente or {}).get("company"), "marca")
    fornecedor = nome_na_pagina((semente or {}).get("vendor"), "fornecedor") if semente else None
    if fornecedor is None or fornecedor["tipo"] == "not found":
        for d, reg in empresas.items():
            n = reg["name"].get("valor") if isinstance(reg.get("name"), dict) else None
            if n and len(n) > 3 and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", p.texto):
                fornecedor = literal(n, n, p, nota="nome de empresa da V4 encontrado na página")
                break
        fornecedor = fornecedor or nao_achado([p])

    ano = _data_publicacao(p)
    if ano is None and semente and semente.get("date"):
        ano = campo(semente["date"], "inferido", p.url, None, p.data, nota="data da base inicial; a página não expõe data em metadado")
    obj = achar([p], re.compile(r"(objective|goal|aim(ed)?\s+to|wanted\s+to|set\s+out\s+to|test(ed)?\s+whether|"
                                r"to\s+(see|check|find\s+out)\s+(whether|if)|compar\w+)", re.I),
                contexto=rx["contexto"], max_=1)
    met = achar([p], re.compile(r"(compar\w+|replicat\w+|against|versus|\bvs\.?\b|same\s+questions|"
                                r"side[- ]by[- ]side|parallel|benchmark\w*)", re.I),
                contexto=rx["contexto"], max_=1)
    res = achar([p], rx["resultado_case"], contexto=rx["contexto"], max_=3)

    dom_fornecedor = None
    if fornecedor.get("tipo") == "literal":
        dom_fornecedor = next((d for d, r in empresas.items()
                               if isinstance(r.get("name"), dict) and r["name"].get("valor") == fornecedor["valor"]), None)
    if dom_fornecedor and registravel(p.url) == dom_fornecedor:
        indep = inferido("autodeclarado", p, base="página do próprio fornecedor")
    elif corrida._em(p.url, "dominios_academicos") or corrida._em(p.url, "dominios_associacoes"):
        indep = inferido("independente", p, base="fonte acadêmica ou associação")
    elif semente and re.search(r"self", semente.get("evidence_type", ""), re.I):
        indep = inferido("autodeclarado", p, base="base inicial classifica a evidência como autodeclarada")
    elif semente and re.search(r"independent|third|peer", semente.get("evidence_type", ""), re.I):
        indep = inferido("independente", p, base="base inicial classifica a evidência como independente")
    else:
        indep = inferido("autodeclarado", p, base="padrão conservador: sem sinal de estudo independente")

    item = {
        "titulo": _titulo(p),
        "marca": marca,
        "fornecedor": fornecedor,
        "ano": ano or nao_achado([p]),
        "objetivo": literal(obj[0][0], obj[0][0], p) if obj else nao_achado([p]),
        "metodo": literal(met[0][0], met[0][0], p) if met else nao_achado([p]),
        "resultado_literal": [literal(q, q, pg) for q, pg, _ in res] or [nao_achado([p])],
        "sinal": inferido(_sinal(" ".join(q for q, _, _ in res) + " " + p.titulo), p),
        "independente_ou_autodeclarado": indep,
        "url": p.url,
        "data": p.data,
    }
    item["date_confidence"] = _confianca_data(corrida, item["ano"])
    if semente:
        item["base_inicial"] = {k: semente.get(k) for k in ("title", "company", "vendor", "year", "evidence_type")}
    return item


def varrer_v3(corrida: Corrida) -> dict:
    v4 = corrida.ler("V4")
    if not v4:
        raise RuntimeError("V3 depende de empresas.json. Rode a V4 antes.")
    rx = corrida.rx
    empresas = {r["dominio"]: r for r in v4["companies"]}
    dados = []
    for reg in v4["companies"]:
        paginas = _paginas_registradas(corrida, reg, "V3")
        if not any(p.ok for p in paginas):
            continue

        def frase(chave: str, ctx: bool = False, n: int = 1) -> dict:
            r = achar(paginas, rx[chave], contexto=rx["contexto"] if ctx else None, max_=n,
                      ordem=["security", "trust", "privacy", "method", "science", "data", "product"])
            if not r:
                return nao_achado(paginas)
            return literal(r[0][0], r[0][0], r[0][1], outras=[literal(x[0], x[0], x[1]) for x in r[1:]])

        dados.append({
            "empresa": reg["name"], "dominio": reg["dominio"],
            "origem_dados_ancoragem": frase("origem_dados", ctx=True),
            "volume": frase("volume", n=2),
            "idioma_pais_cobertos": frase("cobertura"),
            "privacidade_consentimento": frase("privacidade", n=2),
            "formato_entrega": frase("formato_entrega", ctx=True),
            "url": reg["url"], "data": HOJE,
        })

    sementes_cases = json.loads(_expandir(corrida.cfg["sementes"]["cases"]).read_text(encoding="utf-8"))["cases"]
    if corrida.piloto:
        nomes = {r["name"].get("valor", "").lower() for r in v4["companies"] if isinstance(r.get("name"), dict)}
        ligados = [c for c in sementes_cases if (c.get("vendor") or "").lower() in nomes]
        sementes_cases = (ligados + [c for c in sementes_cases if c not in ligados])[: max(5, corrida.piloto // 2)]
    cases, descartados, vistos = [], [], set()
    for c in sementes_cases:
        p = corrida.paginas.abrir(c["url"])
        vistos.add(p.url)
        cases.append(extrair_case(corrida, p, c, empresas))
    for _, u in corrida.buscas.urls("V3"):
        if canonica(u) in vistos or corrida.ignorado(u):
            continue
        vistos.add(canonica(u))
        p = corrida.paginas.abrir(u)
        if not p.ok:
            cases.append(extrair_case(corrida, p, None, empresas))
            continue
        if not achar([p], rx["resultado_case"], contexto=rx["contexto"], max_=1):
            descartados.append({"url": p.url, "motivo": "sem frase com número ligada a sintético (inferido)"})
            continue
        if not rx["pesquisa_de_mercado"].search(p.titulo + " " + p.texto[:5000]):
            descartados.append({"url": p.url, "motivo": "estudo fora de pesquisa de mercado ou opinião (inferido)"})
            continue
        cases.append(extrair_case(corrida, p, None, empresas))
    for f in corrida.fichas("V3"):
        for i, c in enumerate(cases):
            if c["url"] == canonica(f.get("url", "")):
                cases[i].update(f.get("campos") or {})

    bloqueados = [{"url": c["url"], "motivo": c["titulo"].get("motivo", "")} for c in cases
                  if c["titulo"].get("tipo") == "not accessible"]
    saida = {
        "meta": corrida.meta("V3", "V3 dados: o que alimenta e o que sai, e os estudos sintético contra real", [
            "dados_por_empresa usa as páginas da V4 mais resultados de busca V3 no mesmo domínio.",
            "cases: os da base inicial (cases_media.json) mais resultados de busca V3 com frase numérica sobre sintético.",
            "marca e fornecedor só são literais quando o nome aparece na página; o que a base inicial dizia fica em base_inicial.",
            "independente_ou_autodeclarado e sinal são inferidos; a regra está em cada campo.",
        ], bloqueados=bloqueados, cases_descartados=descartados,
            total=len(dados) + len(cases), total_dados=len(dados), total_cases=len(cases)),
        "dados_por_empresa": dados,
        "cases": cases,
    }
    gravar_json(corrida.arquivo("V3"), saida, indent=2)
    return saida


# --------------------------------------------------------------------------
# V1 metodologias
# --------------------------------------------------------------------------

def _fontes_v1(corrida: Corrida) -> list[tuple[str, str | None, str]]:
    md = _expandir(corrida.cfg["sementes"]["metodologias"]).read_text(encoding="utf-8")
    urls = []
    for u in re.findall(r"https?://[^\s)\]>,;\"*]+", md):
        u = u.rstrip(".")
        u = re.sub(r"(arxiv\.org/abs/\d{4}\.\d{4,5})v\d+$", r"\1", u)
        urls.append(u)
    fontes = [(u, None, "methods_validation.md") for u in dict.fromkeys(urls)]
    fontes += [(f["url"], f.get("familia"), "configuração") for f in corrida.cfg.get("fontes_v1_extras", [])]
    fontes += [(u, None, "busca V1") for _, u in corrida.buscas.urls("V1")]
    vistos, saida = set(), []
    for u, fam, orig in fontes:
        if canonica(u) not in vistos and not corrida.ignorado(u):
            vistos.add(canonica(u))
            saida.append((u, fam, orig))
    return saida


def extrair_metodologia(corrida: Corrida, p: Pagina, familia: str | None, origem: str,
                        dom_empresas: set[str]) -> dict:
    rx = corrida.rx
    ident = re.sub(r"[^a-z0-9]+", "-", (urlparse(p.url).netloc + urlparse(p.url).path).lower()).strip("-")[:80]
    tfonte = corrida.tipo_de_fonte(p.url, dom_empresas)
    if not p.ok:
        na = inacessivel(p)
        return {"id": ident, "nome": na, "familia": na, "descricao_literal": na, "quando_usar": na,
                "limites": na, "fonte": na,
                "tipo_de_fonte": campo(tfonte, "inferido", p.url, None, p.data, base="domínio da URL"),
                "url": p.url, "data": p.data, "date_confidence": "low", "origem": origem}
    nome = _titulo(p)
    desc = None
    for chave in ("citation_abstract", "dc.description", "og:description", "description"):
        if p.meta.get(chave) and len(p.meta[chave]) > 60:
            desc = literal(recortar(p.meta[chave], 900), recortar(p.meta[chave], 900), p, origem_texto=chave)
            break
    if desc is None:
        m = re.search(r"Abstract:?\s*(.{80,1200}?)(?:\n|$)", p.texto)
        if m:
            q = recortar(m.group(1), 900)
            desc = literal(q, q, p, origem_texto="bloco Abstract")
    if desc is None:
        r = achar([p], re.compile(r"(this\s+(paper|report|guidance|article|study|document|code)|we\s+(propose|present|show|find|introduce)|"
                                  r"esta\s+lei|este\s+documento)", re.I), max_=1)
        desc = literal(r[0][0], r[0][0], p) if r else nao_achado([p])

    base_fam = " ".join([nome.get("valor", ""), desc.get("valor", "")]) if desc.get("tipo") == "literal" else nome.get("valor", "")
    if familia:
        fam = inferido(familia, p, base="família definida na configuração da corrida")
    elif re.search(r"eur-lex|planalto|artificialintelligenceact|iso\.org", p.url):
        fam = inferido("regulacao", p, base="lei, regulamento ou norma")
    elif tfonte == "associacao":
        fam = inferido("boa_pratica", p, base="código ou guia de associação")
    else:
        nv = len(rx["familia_validacao"].findall(base_fam))
        nc = len(rx["familia_construcao"].findall(base_fam))
        fam = inferido("validacao" if nv >= max(2, nc / 2) else "construcao", p,
                       base=f"{nv} termos de validação contra {nc} de construção no título e resumo")

    quando = achar([p], rx["quando_usar"], contexto=rx["contexto"], max_=1)
    limites = achar([p], rx["limites"], contexto=rx["contexto"], max_=2)
    if p.meta.get("citation_journal_title"):
        fonte = literal(p.meta["citation_journal_title"], p.meta["citation_journal_title"], p)
    elif p.meta.get("og:site_name"):
        fonte = literal(p.meta["og:site_name"], p.meta["og:site_name"], p)
    else:
        fonte = inferido(dominio(p.url), p, base="domínio da URL")
    data_pub = _data_publicacao(p)
    item = {
        "id": ident,
        "nome": nome,
        "familia": fam,
        "descricao_literal": desc,
        "quando_usar": literal(quando[0][0], quando[0][0], p) if quando else nao_achado([p]),
        "limites": literal(limites[0][0], limites[0][0], p,
                           outras=[literal(x[0], x[0], x[1]) for x in limites[1:]]) if limites else nao_achado([p]),
        "fonte": fonte,
        "tipo_de_fonte": inferido(tfonte, p, base="domínio da URL"),
        "url": p.url,
        "data": data_pub["valor"] if data_pub else "not found",
        "data_campo": data_pub or nao_achado([p]),
        "date_confidence": _confianca_data(corrida, data_pub),
        "menciona_brasil": inferido(bool(rx["brasil"].search(p.texto)), p,
                                    base="busca por Brasil, Brazil, LGPD, ABEP no texto"),
        "origem": origem,
    }
    return item


def varrer_v1(corrida: Corrida) -> dict:
    v4 = corrida.ler("V4")
    dom_empresas = {r["dominio"] for r in v4.get("companies", [])}
    fontes = _fontes_v1(corrida)
    if corrida.piloto:
        fontes = fontes[: max(8, corrida.piloto)]
    itens, descartados = [], []
    for n, (u, fam, origem) in enumerate(fontes, 1):
        p = corrida.paginas.abrir(u)
        print(f"  [{n:>3}/{len(fontes)}] {p.estado:15} {u[:80]}")
        if origem == "busca V1" and p.ok and not corrida.rx["contexto"].search(p.titulo + " " + p.texto[:3000]):
            descartados.append({"url": p.url, "motivo": "sem menção ao tema no título ou início do texto (inferido)"})
            continue
        itens.append(extrair_metodologia(corrida, p, fam, origem, dom_empresas))
    for f in corrida.fichas("V1"):
        for i, it in enumerate(itens):
            if it["url"] == canonica(f.get("url", "")):
                itens[i].update(f.get("campos") or {})
    bloqueados = [{"url": i["url"], "motivo": i["nome"].get("motivo", "")} for i in itens
                  if i["nome"].get("tipo") == "not accessible"]
    saida = {
        "meta": corrida.meta("V1", "V1 metodologias: como se constrói e como se valida dado ou persona sintética", [
            "Fontes: todas as URLs de methods_validation.md, as diretrizes da configuração e os resultados de busca V1.",
            "descricao_literal vem do resumo em metadado (citation_abstract, description) ou do bloco Abstract.",
            "familia e tipo_de_fonte são inferidos pelo domínio e pelos termos do título e do resumo.",
            "Data fora da janela ou ausente recebe date_confidence low.",
        ], bloqueados=bloqueados, descartados=descartados, total=len(itens)),
        "metodologias": itens,
    }
    gravar_json(corrida.arquivo("V1"), saida, indent=2)
    return saida


# --------------------------------------------------------------------------
# V5 comparacao (sem busca nova)
# --------------------------------------------------------------------------

def varrer_v5(corrida: Corrida) -> dict:
    v1, v2, v3, v4 = (corrida.ler(v) for v in ("V1", "V2", "V3", "V4"))
    if not v4:
        raise RuntimeError("V5 depende de empresas.json.")
    por_dom_v2 = {o["dominio"]: o for o in v2.get("ofertas", [])}
    por_dom_v3 = {d["dominio"]: d for d in v3.get("dados_por_empresa", [])}
    cases = v3.get("cases", [])
    linhas = []
    for r in v4["companies"]:
        d = r["dominio"]
        nome = r["name"].get("valor") if isinstance(r.get("name"), dict) else d
        cases_dela = [c for c in cases if isinstance(c.get("fornecedor"), dict) and c["fornecedor"].get("valor") == nome]
        o2, o3 = por_dom_v2.get(d, {}), por_dom_v3.get(d, {})
        linhas.append({
            "empresa": r["name"], "dominio": d,
            "tipo_de_oferta": r.get("offer_type"),
            "base_da_persona": r.get("grounding"),
            "dados_que_alimentam": o3.get("origem_dados_ancoragem") or nao_achado([Pagina(url=r["url"])]),
            "metodologia_declarada": o2.get("como_e_construida") or nao_achado([Pagina(url=r["url"])]),
            "validacao_declarada": r.get("validation_claim"),
            "nivel_validacao": (r.get("validation_claim") or {}).get("level"),
            "preco": r.get("pricing"),
            "clientes": r.get("named_customers"),
            "ressalvas_publicadas": [c["resultado_literal"] for c in cases_dela
                                     if c.get("sinal", {}).get("valor") == "negativo_ou_misto"],
            "cases_ligados": [c["url"] for c in cases_dela],
        })

    def nivel(l): return ((l.get("nivel_validacao") or {}).get("valor")) or "none"
    total = len(linhas) or 1
    contagem = Counter(nivel(l) for l in linhas)
    sem_preco = [l["dominio"] for l in linhas if (l["preco"] or {}).get("tipo") != "literal"]
    nao_div = [l["dominio"] for l in linhas if (l["base_da_persona"] or {}).get("valor") == "not_disclosed"]
    url_v4 = "empresas.json"
    lacunas = [
        {"lacuna": "validação independente", "tipo": "inferido", "url": url_v4, "data": HOJE,
         "evidencia": f"{contagem.get('third_party', 0) + contagem.get('peer_reviewed', 0)} de {len(linhas)} empresas "
                      f"com validação de terceiro ou revisada por pares; {contagem.get('self_reported', 0)} autodeclaradas; "
                      f"{contagem.get('none', 0)} sem alegação com número",
         "dominios": [l["dominio"] for l in linhas if nivel(l) in ("none", "self_reported")]},
        {"lacuna": "preço público", "tipo": "inferido", "url": url_v4, "data": HOJE,
         "evidencia": f"{len(sem_preco)} de {len(linhas)} sem preço literal nas páginas abertas",
         "dominios": sem_preco},
        {"lacuna": "base da persona", "tipo": "inferido", "url": url_v4, "data": HOJE,
         "evidencia": f"{len(nao_div)} de {len(linhas)} sem frase sobre a base da persona",
         "dominios": nao_div},
    ]
    divergencias = []
    for l in linhas:
        if nivel(l) != "self_reported":
            continue
        nome = l["empresa"].get("valor") if isinstance(l["empresa"], dict) else ""
        for c in cases:
            if (c.get("independente_ou_autodeclarado") or {}).get("valor") != "independente":
                continue
            forn = (c.get("fornecedor") or {}).get("valor")
            if forn == nome:
                divergencias.append({
                    "empresa": nome, "tipo": "inferido", "data": HOJE,
                    "afirmacao_do_fornecedor": l["validacao_declarada"],
                    "estudo_independente": {"titulo": c["titulo"], "resultado": c["resultado_literal"], "url": c["url"]},
                    "url": c["url"],
                })
    rxb = corrida.rx["brasil"]
    lacuna_brasil = {
        "tipo": "inferido", "url": "metodologias.json; dados.json; empresas.json", "data": HOJE,
        "metodologias_que_citam_brasil": [m["url"] for m in v1.get("metodologias", [])
                                          if (m.get("menciona_brasil") or {}).get("valor") is True],
        "cases_com_brasil": [c["url"] for c in cases
                             if rxb.search(json.dumps(c.get("resultado_literal"), ensure_ascii=False) + " "
                                           + json.dumps(c.get("titulo"), ensure_ascii=False))],
        "empresas_com_sede_no_brasil": [l["dominio"] for l, r in zip(linhas, v4["companies"])
                                        if (r.get("hq_country") or {}).get("valor") == "Brazil"],
        "empresas_brasileiras_com_validacao_de_terceiro": [
            l["dominio"] for l, r in zip(linhas, v4["companies"])
            if (r.get("hq_country") or {}).get("valor") == "Brazil" and nivel(l) in ("third_party", "peer_reviewed")],
    }
    lacuna_brasil["leitura"] = (
        f"{len(lacuna_brasil['metodologias_que_citam_brasil'])} fontes de metodologia citam o Brasil; "
        f"{len(lacuna_brasil['cases_com_brasil'])} cases citam o Brasil; "
        f"{len(lacuna_brasil['empresas_com_sede_no_brasil'])} empresas com sede no Brasil, "
        f"{len(lacuna_brasil['empresas_brasileiras_com_validacao_de_terceiro'])} delas com validação de terceiro.")
    saida = {
        "meta": corrida.meta("V5", "V5 comparação empresa por empresa, derivada de V1 a V4", [
            "Gerada só a partir de metodologias.json, personas.json, dados.json e empresas.json; nenhuma busca nova.",
            "Cada célula copia o campo da varredura de origem, com tipo, quote e URL.",
            "lacunas, divergencias e lacuna_brasil são inferidos e dizem de onde vem cada contagem.",
        ], fontes=[str(corrida.arquivo(v).name) for v in ("V1", "V2", "V3", "V4")], total=len(linhas)),
        "tabela": linhas,
        "lacunas": lacunas,
        "divergencias": divergencias,
        "lacuna_brasil": lacuna_brasil,
    }
    gravar_json(corrida.arquivo("V5"), saida, indent=2)
    return saida


# --------------------------------------------------------------------------
# Validador
# --------------------------------------------------------------------------

VOCAB_POR_CHAVE = {
    "company_type": "company_type", "offer_type": "offer_type", "grounding": "base_da_persona",
    "base_da_persona": "base_da_persona", "level": "validation_level", "nivel_validacao": "validation_level",
    "familia": "familia", "tipo_de_fonte": "tipo_de_fonte",
    "independente_ou_autodeclarado": "independente_ou_autodeclarado",
}


def validar(corrida: Corrida) -> dict:
    """Toda quote presente na pagina guardada; todo campo com URL; valores
    fechados dentro do vocabulario. Devolve contagens e violacoes."""
    vocab = corrida.cfg["vocabulario"]
    violacoes, contagem = [], Counter()
    paginas_cache: dict[str, str | None] = {}

    def texto_de(url: str) -> str | None:
        if url not in paginas_cache:
            p = corrida.paginas.obter(url)
            paginas_cache[url] = p.texto_validacao() if p and p.ok else None
        return paginas_cache[url]

    def andar(x, caminho: str, arquivo: str, chave_pai: str | None):
        if isinstance(x, dict):
            if x.get("tipo") in TIPOS and "valor" in x:
                contagem[f"{arquivo}:{x['tipo']}"] += 1
                contagem[x["tipo"]] += 1
                if not x.get("url"):
                    violacoes.append({"arquivo": arquivo, "caminho": caminho, "regra": "campo sem URL"})
                q = x.get("quote")
                if x["tipo"] == "literal" and not q:
                    violacoes.append({"arquivo": arquivo, "caminho": caminho, "regra": "literal sem quote"})
                if q and x.get("url") and x["url"].startswith("http"):
                    t = texto_de(x["url"])
                    if t is None:
                        violacoes.append({"arquivo": arquivo, "caminho": caminho, "url": x["url"],
                                          "regra": "quote de página não guardada ou não acessível"})
                    elif not citacao_confere(q, t):
                        violacoes.append({"arquivo": arquivo, "caminho": caminho, "url": x["url"],
                                          "regra": "quote não encontrada literalmente", "quote": q[:200]})
                nome_vocab = VOCAB_POR_CHAVE.get(chave_pai or "")
                if nome_vocab and x["tipo"] in ("literal", "inferido") and x["valor"] not in vocab[nome_vocab]:
                    violacoes.append({"arquivo": arquivo, "caminho": caminho, "valor": x["valor"],
                                      "regra": f"valor fora do vocabulário {nome_vocab}"})
            for k, v in x.items():
                if k in ("meta", "base_inicial"):
                    continue
                andar(v, f"{caminho}.{k}", arquivo, k)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                andar(v, f"{caminho}[{i}]", arquivo, chave_pai)

    arquivos = {}
    for v in ("V1", "V2", "V3", "V4", "V5"):
        d = corrida.ler(v)
        if d:
            arquivos[ARQUIVOS[v]] = d
            andar(d, ARQUIVOS[v], ARQUIVOS[v], None)
    rel = {"data": HOJE, "arquivos": sorted(arquivos), "contagem": dict(contagem),
           "violacoes": violacoes, "total_violacoes": len(violacoes)}
    gravar_json(corrida.saida / "validacao.json", rel, indent=2)
    return rel


# --------------------------------------------------------------------------
# Recall contra a base inicial
# --------------------------------------------------------------------------

def recall(corrida: Corrida) -> dict:
    """Cada linha da base inicial precisa estar em empresas.json ou ter motivo."""
    v4 = corrida.ler("V4")
    meta = v4.get("meta", {})
    puladas = meta.get("sementes_puladas", [])
    no_v4 = {n: r["dominio"] for r in v4.get("companies", []) for n in r.get("sementes", [])}
    descartes = {n: x["motivo"] for x in meta.get("descartadas", []) for n in x.get("sementes", [])}
    fichas = {f["chave"]: f.get("ausencia") for f in corrida.fichas("V4") if f.get("ausencia")}
    empresas_base, _ = empresas_semente(corrida)
    if corrida.piloto:
        empresas_base = _amostra_piloto(empresas_base, max(1, corrida.piloto - 2))
        puladas = []
    linhas, sem_motivo = [], []
    for e in empresas_base:
        for s in e["sementes"]:
            n = s["name"]
            if n in no_v4:
                linhas.append({"name": n, "dominio": no_v4[n], "situacao": "presente"})
            elif n in descartes or e["dominio"] in fichas:
                linhas.append({"name": n, "dominio": e["dominio"], "situacao": "ausente_justificada",
                               "motivo": descartes.get(n) or fichas[e["dominio"]]})
            else:
                linhas.append({"name": n, "dominio": e["dominio"], "situacao": "ausente_sem_motivo"})
                sem_motivo.append(n)
    for p in puladas:
        linhas.append({"name": p["name"], "dominio": dominio(p["url"]) if p["url"].startswith("http") else "",
                       "situacao": "ausente_justificada", "motivo": p["motivo"]})
    rel = {"data": HOJE, "base": str(corrida.cfg["sementes"]["empresas"]), "total_base": len(linhas),
           "presentes": sum(1 for l in linhas if l["situacao"] == "presente"),
           "justificadas": sum(1 for l in linhas if l["situacao"] == "ausente_justificada"),
           "sem_motivo": sem_motivo, "passou": not sem_motivo, "linhas": linhas}
    gravar_json(corrida.saida / "recall.json", rel, indent=2)
    return rel


# --------------------------------------------------------------------------
# Relatorio de custo e cobertura, e RESUMO.md
# --------------------------------------------------------------------------

def cobertura(corrida: Corrida) -> dict:
    v4 = corrida.ler("V4")
    campos = ["name", "hq_country", "founded_year", "company_type", "headline_verbatim", "grounding",
              "validation_claim", "pricing", "funding_last", "demo_video_url"]
    por_campo = {}
    for c in campos:
        cont = Counter((r.get(c) or {}).get("tipo", "ausente") for r in v4.get("companies", []))
        por_campo[c] = dict(cont)
    for c in ("offer_type", "named_customers", "notable_media"):
        com = sum(1 for r in v4.get("companies", [])
                  if any(x.get("tipo") in ("literal", "inferido") for x in r.get(c) or []))
        por_campo[c] = {"com_valor": com, "sem_valor": len(v4.get("companies", [])) - com}
    return por_campo


def relatorio(corrida: Corrida, validacao: dict | None = None, rec: dict | None = None) -> dict:
    validacao = validacao or ler_json(corrida.saida / "validacao.json", {})
    rec = rec or ler_json(corrida.saida / "recall.json", {})
    st = corrida.paginas.stats
    todas = corrida.paginas.todas()
    rel = {
        "data": HOJE,
        "piloto": bool(corrida.piloto),
        "buscas": {v: {"usadas": corrida.buscas.usadas(v), "teto": corrida.teto(v)} for v in corrida.cfg["teto_buscas"]},
        "paginas_no_cache": {"total": len(todas), "ok": sum(1 for p in todas if p.ok),
                             "not_accessible": sum(1 for p in todas if p.estado == "not accessible"),
                             "erro": sum(1 for p in todas if p.estado == "erro"),
                             "por_metodo": dict(Counter(p.metodo for p in todas if p.ok)),
                             "megabytes": round(sum(p.bytes for p in todas) / 1e6, 1)},
        "esta_execucao": dict(st, segundos=round(time.time() - corrida.inicio)),
        "custo": {"llm_tokens": 0 if provedor_ativo().nome == "manual" else "ver provedor",
                  "api_de_busca": os.getenv("BUSCA_PROVIDER", "manual"),
                  "dinheiro_usd": 0 if os.getenv("BUSCA_PROVIDER", "manual") == "manual"
                  and provedor_ativo().nome == "manual" else "ver provedor"},
        "cobertura_v4": cobertura(corrida),
        "totais": {ARQUIVOS[v]: (corrida.ler(v).get("meta") or {}).get("total") for v in VARREDURAS},
        "violacoes_validador": validacao.get("total_violacoes"),
        "recall": {k: rec.get(k) for k in ("total_base", "presentes", "justificadas", "passou")},
    }
    gravar_json(corrida.saida / "relatorio.json", rel, indent=2)
    return rel


def _relevancia(r: dict) -> int:
    nivel = ((r.get("validation_claim") or {}).get("level") or {}).get("valor", "none")
    pontos = {"peer_reviewed": 6, "third_party": 4, "self_reported": 2}.get(nivel, 0)
    pontos += min(4, sum(1 for c in r.get("named_customers") or [] if c.get("tipo") in ("literal", "inferido")))
    pontos += 2 if (r.get("funding_last") or {}).get("tipo") == "literal" else 0
    pontos += len([o for o in r.get("offer_type") or [] if o.get("tipo") == "inferido"])
    pontos += min(3, len(r.get("notable_media") or []))
    return pontos


def escrever_resumo(corrida: Corrida, rel: dict) -> Path:
    v1, v2, v3, v4 = (corrida.ler(v) for v in ("V1", "V2", "V3", "V4"))
    emp = v4.get("companies", [])
    tipos = Counter((r.get("company_type") or {}).get("valor", "not found") for r in emp)
    regioes = Counter((r.get("region") or {}).get("valor", "not found") for r in emp)
    ofertas = Counter(o["valor"] for r in emp for o in r.get("offer_type") or [] if o.get("tipo") == "inferido")
    top = sorted(emp, key=_relevancia, reverse=True)[:10]
    novas = [r for r in emp if not r.get("base_inicial")]
    mudou = []
    for r in emp:
        for b in r.get("base_inicial") or []:
            g = (r.get("grounding") or {}).get("valor")
            if b.get("grounding") and g and g != b["grounding"]:
                mudou.append(f"{b['name']}: base da persona {b['grounding']} na base inicial, {g} agora (inferido)")
            nivel = ((r.get("validation_claim") or {}).get("level") or {}).get("valor")
            if (b.get("validation_status") or "").startswith("self") and nivel == "none":
                mudou.append(f"{b['name']}: base inicial tinha validação autodeclarada; esta corrida não achou frase com número nas páginas abertas")
    nf = defaultdict(list)
    for r in emp:
        nome = (r.get("name") or {}).get("valor", r["dominio"])
        for k in ("hq_country", "founded_year", "pricing", "funding_last", "demo_video_url", "headline_verbatim"):
            if (r.get(k) or {}).get("tipo") in ("not found", "not accessible"):
                nf[k].append(nome)

    L = [f"# Resumo da vertical sinteticos{' (piloto)' if corrida.piloto else ''}", "",
         f"Corrida de {HOJE}. Mercado: {corrida.cfg['mercado']}.", "",
         "## Totais", "",
         f"- Empresas (V4): {len(emp)}, das quais {len(novas)} fora da base inicial.",
         f"- Ofertas de persona (V2): {len(v2.get('ofertas', []))}.",
         f"- Dados por empresa (V3): {len(v3.get('dados_por_empresa', []))}. Cases: {len(v3.get('cases', []))}.",
         f"- Metodologias (V1): {len(v1.get('metodologias', []))}.",
         "", "### Por tipo de empresa (inferido)", ""]
    L += [f"- {k}: {n}" for k, n in tipos.most_common()]
    L += ["", "### Por região (inferida da sede)", ""]
    L += [f"- {k}: {n}" for k, n in regioes.most_common()]
    L += ["", "### Por tipo de oferta (inferido)", ""]
    L += [f"- {k}: {n}" for k, n in ofertas.most_common()]
    L += ["", "## As 10 mais relevantes", "",
          "Pontuação transparente: nível de validação (revisada por pares 6, terceiro 4, autodeclarada 2), "
          "até 4 clientes nomeados, 2 por financiamento literal, 1 por tipo de oferta, até 3 por menções na imprensa.", ""]
    for r in top:
        nome = (r.get("name") or {}).get("valor", r["dominio"])
        nivel = ((r.get("validation_claim") or {}).get("level") or {}).get("valor", "none")
        L.append(f"1. {nome} ({r['dominio']}): {_relevancia(r)} pontos, validação {nivel}.")
    L += ["", "## O que mudou contra a base inicial", ""]
    L += [f"- Nova: {(r.get('name') or {}).get('valor', r['dominio'])} ({r['dominio']}), origem {', '.join(r.get('origem', []))}." for r in novas] or ["- Nenhuma empresa nova."]
    L += [f"- {m}" for m in mudou] or []
    rec = rel.get("recall") or {}
    L += [f"- Recall: {rec.get('presentes')} presentes e {rec.get('justificadas')} ausências justificadas "
          f"de {rec.get('total_base')} registros da base.", ""]
    L += ["## Ficou not found ou not accessible", ""]
    for k, nomes in nf.items():
        L.append(f"- {k} ({len(nomes)}): {', '.join(nomes)}.")
    L += ["", "## Buscas, bloqueios e validador", ""]
    for v, b in rel["buscas"].items():
        L.append(f"- {v}: {b['usadas']} de {b['teto']} buscas.")
    bloq = [b for v in ("V1", "V3", "V4") for b in (corrida.ler(v).get("meta") or {}).get("bloqueados", [])]
    L.append(f"- Bloqueados: {len(bloq)} URLs (lista na meta de cada arquivo).")
    L.append(f"- Violações do validador: {rel.get('violacoes_validador')}.")
    L.append(f"- Custo: {rel['custo']['dinheiro_usd']} USD; tokens de LLM {rel['custo']['llm_tokens']}; "
             f"{rel['paginas_no_cache']['total']} páginas no cache, {rel['paginas_no_cache']['megabytes']} MB.")
    caminho = corrida.saida / "RESUMO.md"
    caminho.write_text("\n".join(L) + "\n", encoding="utf-8")
    return caminho


VARRER = {"V4": varrer_v4, "V2": varrer_v2, "V3": varrer_v3, "V1": varrer_v1, "V5": varrer_v5}
