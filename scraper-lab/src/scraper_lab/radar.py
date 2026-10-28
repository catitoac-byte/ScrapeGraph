"""
Camada de coleta do radar de mercado (sem LLM).

Fontes: feeds RSS/Atom e sitemaps por publicador e idioma, mais consultas de
busca quando ha provedor com chave (Brave) ou resultados registrados a mao.
Cada pagina e aberta pelo mesmo CachePaginas da vertical duvidas_mercado
(cache em disco, robots.txt, pausa por dominio, bloqueio vira "not accessible"
e nao se insiste). Os trechos sao paragrafos literais da pagina que contem
palavra do vocabulario da categoria. O julgamento (tema, hipotese, hype, buzz)
fica com os agentes; aqui so se coleta e se confere.

Comandos em raspar_radar.py: coletar, conferir, feeds.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from lxml import etree

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
)

RAIZ = Path(__file__).resolve().parents[2]
CACHE_RADAR = RAIZ / "dados" / "cache" / "radar"
SAIDA_RADAR = RAIZ / "dados" / "saida" / "radar"

MAX_FEED_BYTES = 30_000_000
PAUSA_FEED = 1.0
MAX_ITENS_POR_FONTE = 300
MAX_FILHOS_SITEMAP = 6
TETO_PAGINAS_PADRAO = 60
TETO_BUSCAS_PADRAO = 20
MAX_TRECHOS = 5
TRECHO_MAX = 500

# Termos de sinal: o que indica novidade, tendencia, hype ou dado novo.
SINAIS_PADRAO = {
    "en": ["trend", "hype", "survey finds", "survey shows", "report", "launch", "launches", "launched",
           "new study", "forecast", "adoption", "predict", "breakthrough", "announces", "raises", "funding",
           "acquires", "acquisition", "benchmark", "white paper", "study finds"],
    "pt": ["tendência", "tendencia", "pesquisa mostra", "pesquisa revela", "lançamento", "lança", "lançou",
           "relatório", "estudo", "aposta", "previsão", "adoção", "aquisição", "investimento", "hype"],
    "es": ["tendencia", "tendencias", "encuesta", "estudio", "informe", "lanzamiento", "lanza", "lanzó",
           "pronóstico", "adopción", "adquisición", "inversión", "hype"],
}

_STOP_CONSULTA = {"the", "and", "for", "with", "how", "what", "why", "does", "are", "vs", "de", "do", "da", "para",
                  "com", "que", "como", "los", "las", "una", "del", "por", "con", "en", "el", "la", "sin"}


# --------------------------------------------------------------------------
# Datas e texto
# --------------------------------------------------------------------------

def parse_data(txt: str | None) -> date | None:
    """RFC 822 (RSS), ISO 8601 (Atom, sitemap) ou AAAA-MM-DD solto. None se nao der."""
    if not txt:
        return None
    s = txt.strip()
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError, IndexError):
        pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


def na_janela(d: date | None, hoje: date, janela_dias: int) -> bool:
    """Data dentro de [hoje - janela, hoje + 1 dia] (1 dia de folga para fuso)."""
    if d is None:
        return False
    return hoje - timedelta(days=janela_dias) <= d <= hoje + timedelta(days=1)


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _chave(t: str) -> str:
    """Minusculo, sem acento, aspas e travessoes unificados: base da busca de termos."""
    return _sem_acento(normalizar(t)).lower()


def compilar_termos(termos: list[str]) -> re.Pattern | None:
    """Regex que casa o inicio de qualquer termo (aceita sufixo: synthetic -> synthetically)."""
    ts = sorted({_chave(t) for t in termos if t and t.strip()}, key=len, reverse=True)
    if not ts:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(t) for t in ts) + ")")


def contar(rx: re.Pattern | None, texto: str) -> int:
    return len(rx.findall(_chave(texto))) if rx else 0


# --------------------------------------------------------------------------
# Configuracao tolerante
# --------------------------------------------------------------------------

@dataclass
class Fonte:
    publicador: str
    idioma: str
    tipo: str          # rss | atom | sitemap | auto
    url: str
    incluir: str = ""  # regex opcional: so URLs de sitemap que casam
    extra: dict = field(default_factory=dict)


@dataclass
class ConfigRadar:
    fontes: list[Fonte]
    consultas: dict[str, list[tuple[str, str]]]      # categoria -> [(idioma, consulta)]
    vocabulario: list[str]
    sinais: list[str]
    bloqueios: dict[str, str]
    avisos: list[str]


def _lista(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else []


def _por_idioma(v) -> list[tuple[str, str]]:
    """Aceita {idioma: [..]} ou [..] (idioma desconhecido vira '')."""
    if isinstance(v, dict):
        return [(i, q) for i, qs in v.items() for q in _lista(qs)]
    return [("", q) for q in _lista(v)]


def _tipo(raw: str, url: str) -> str:
    t = (raw or "").lower()
    if t in ("rss", "atom", "sitemap", "auto"):
        return t
    if t in ("feed", "xml"):
        return "auto"
    return "sitemap" if "sitemap" in url.lower() else "auto"


def _fontes_de(cfg: dict, avisos: list[str]) -> list[Fonte]:
    bruto = cfg.get("fontes_feeds")
    if bruto is None:
        avisos.append("config sem 'fontes_feeds': seguindo so com consultas")
        return []
    if isinstance(bruto, dict):
        itens = []
        for pub, v in bruto.items():
            if isinstance(v, list):
                itens += [dict(x, publicador=x.get("publicador", pub)) for x in v if isinstance(x, dict)]
            elif isinstance(v, dict):
                itens.append(dict(v, publicador=v.get("publicador", pub)))
    else:
        itens = [x for x in bruto if isinstance(x, dict)]
    fontes: list[Fonte] = []
    for it in itens:
        pub = it.get("publicador") or it.get("nome") or it.get("publisher") or ""
        idioma = it.get("idioma") or it.get("lang") or it.get("language") or ""
        if not idioma:
            avisos.append(f"fonte '{pub or it}' sem idioma: assumindo 'en'")
            idioma = "en"
        achou = False
        for chave, tipo_fixo in (("url", None), ("feed", "auto"), ("rss", "rss"), ("atom", "atom"), ("sitemap", "sitemap")):
            u = it.get(chave)
            if isinstance(u, str) and u.startswith("http"):
                achou = True
                tipo = tipo_fixo or _tipo(it.get("tipo") or it.get("type") or "", u)
                if chave == "url" and tipo_fixo is None:
                    tipo = _tipo(it.get("tipo") or it.get("type") or "", u)
                fontes.append(Fonte(pub or dominio(u), idioma.lower(), tipo, u, it.get("incluir", ""),
                                    {k: v for k, v in it.items() if k not in ("publicador", "nome", "publisher")}))
        if not achou:
            avisos.append(f"fonte '{pub or it}' sem URL: ignorada")
    return fontes


def carregar_config(caminho: Path, categoria: str) -> ConfigRadar:
    """Le o config; chave ausente vira aviso, nunca erro."""
    cfg = json.loads(Path(caminho).read_text(encoding="utf-8"))
    avisos: list[str] = []
    fontes = _fontes_de(cfg, avisos)

    consultas_cat = _por_idioma((cfg.get("consultas") or {}).get(categoria)) if isinstance(cfg.get("consultas"), dict) else []
    if not consultas_cat:
        avisos.append(f"config sem consultas para a categoria '{categoria}'")

    voc_raw = None
    for k in ("vocabulario", "vocabulario_por_categoria", "palavras_chave"):
        if isinstance(cfg.get(k), dict) and categoria in cfg[k]:
            voc_raw = cfg[k][categoria]
            break
    vocabulario = [t for _, t in _por_idioma(voc_raw)] if voc_raw is not None else []
    if not vocabulario:
        # sem vocabulario no config: deriva das consultas (palavras de 5+ letras)
        derivadas = {w for _, q in consultas_cat for w in re.findall(r"[\wáéíóúãõâêôçñü]{5,}", q.lower())
                     if w not in _STOP_CONSULTA}
        vocabulario = sorted(derivadas)
        avisos.append(f"config sem vocabulario para '{categoria}': derivado das consultas ({len(vocabulario)} termos)")

    sinais = [t for _, t in _por_idioma(cfg.get("termos_de_sinal") or cfg.get("sinais"))]
    if not sinais:
        sinais = [t for ts in SINAIS_PADRAO.values() for t in ts]
        avisos.append("config sem termos_de_sinal: usando os padrões do projeto")

    bloqueios = cfg.get("bloqueios_conhecidos") if isinstance(cfg.get("bloqueios_conhecidos"), dict) else {}
    return ConfigRadar(fontes, {categoria: consultas_cat}, vocabulario, sinais, bloqueios, avisos)


# --------------------------------------------------------------------------
# Download de feed e sitemap (robots, pausa, cache do dia)
# --------------------------------------------------------------------------

_ultimo_acesso: dict[str, float] = {}


def baixar(url: str, *, cache_dir: Path | None = None, hoje: date | None = None) -> dict:
    """Devolve {status, motivo, dados, content_type, do_cache}. Respeita robots.txt.
    Feed muda todo dia, entao o cache de feed vale so no dia da corrida."""
    hoje = hoje or date.today()
    arq = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        arq = cache_dir / f"{hoje.isoformat()}-{hashlib.sha256(url.encode()).hexdigest()[:14]}.xml"
        if arq.exists():
            return {"status": 200, "motivo": "", "dados": arq.read_bytes(), "content_type": "cache", "do_cache": True}
    if not permitido(url, agente=UA_PADRAO, silencioso=True):
        return {"status": 0, "motivo": "robots.txt proíbe (not accessible)", "dados": None, "content_type": "", "do_cache": False}
    d = dominio(url)
    espera = PAUSA_FEED - (time.time() - _ultimo_acesso.get(d, 0))
    if espera > 0:
        time.sleep(espera)
    _ultimo_acesso[d] = time.time()
    try:
        req = Request(url, headers={"User-Agent": UA_PADRAO, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
        with urlopen(req, timeout=40) as r:
            dados = r.read(MAX_FEED_BYTES)
            ct = r.headers.get("Content-Type", "")
            status = r.status
    except HTTPError as e:
        return {"status": e.code, "motivo": f"HTTP {e.code}" + (" (not accessible)" if e.code in (401, 403, 429, 451, 999) else ""),
                "dados": None, "content_type": "", "do_cache": False}
    except (URLError, TimeoutError, OSError, ValueError) as e:
        return {"status": 0, "motivo": f"{type(e).__name__}: {str(e)[:100]}", "dados": None, "content_type": "", "do_cache": False}
    if arq is not None and dados:
        arq.write_bytes(dados)
    return {"status": status, "motivo": "", "dados": dados, "content_type": ct, "do_cache": False}


def _local(tag) -> str:
    return tag.split("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _texto(el) -> str:
    return normalizar("".join(el.itertext())) if el is not None else ""


def _filho(el, *nomes: str):
    for f in el:
        if _local(f.tag) in nomes:
            return f
    return None


def interpretar(dados: bytes) -> dict:
    """Detecta e le feed (rss/atom), sitemap (urlset) ou indice de sitemaps.
    Devolve {tipo, itens:[{url,titulo,data,resumo}], filhos:[{url,lastmod}]}."""
    try:
        raiz = etree.fromstring(dados, parser=etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True))
    except Exception:
        raiz = None
    if raiz is None:
        return {"tipo": "invalido", "itens": [], "filhos": []}
    r = _local(raiz.tag)
    itens, filhos = [], []
    if r == "sitemapindex":
        for s in raiz:
            if _local(s.tag) == "sitemap":
                loc = _texto(_filho(s, "loc"))
                if loc:
                    filhos.append({"url": loc, "lastmod": _texto(_filho(s, "lastmod"))})
        return {"tipo": "indice", "itens": [], "filhos": filhos}
    if r == "urlset":
        for u in raiz:
            if _local(u.tag) != "url":
                continue
            loc = _texto(_filho(u, "loc"))
            data = _texto(_filho(u, "lastmod"))
            titulo = ""
            for f in u.iter():
                n = _local(f.tag)
                if n == "publication_date" and f.text:
                    data = f.text.strip()
                elif n == "title" and f.text and not titulo:
                    titulo = normalizar(f.text)
            if loc:
                itens.append({"url": loc, "titulo": titulo, "data": data, "resumo": ""})
        return {"tipo": "sitemap", "itens": itens, "filhos": []}
    if r in ("rss", "rdf", "feed"):
        for it in raiz.iter():
            n = _local(it.tag)
            if n not in ("item", "entry"):
                continue
            titulo = _texto(_filho(it, "title"))
            link = ""
            for f in it:
                if _local(f.tag) == "link":
                    if f.get("href") and (f.get("rel") in (None, "alternate")):
                        link = f.get("href")
                        break
                    if (f.text or "").strip():
                        link = f.text.strip()
                        break
            if not link:
                g = _filho(it, "guid", "id")
                if g is not None and (g.text or "").startswith("http"):
                    link = g.text.strip()
            data = ""
            for nome in ("pubdate", "published", "date", "updated", "issued", "created"):
                f = _filho(it, nome)
                if f is not None and (f.text or "").strip():
                    data = f.text.strip()
                    break
            resumo = _texto(_filho(it, "description", "summary", "encoded", "content"))[:800]
            if link:
                itens.append({"url": link, "titulo": titulo, "data": data, "resumo": resumo})
        return {"tipo": "atom" if r == "feed" else "rss", "itens": itens, "filhos": []}
    return {"tipo": "invalido", "itens": [], "filhos": []}


def ler_fonte(f: Fonte, *, cache_dir: Path, hoje: date, janela_dias: int, max_itens: int = MAX_ITENS_POR_FONTE) -> dict:
    """Le uma fonte (expande indice de sitemap) e devolve itens JA filtrados pela janela.
    Retorno: {itens, lidos, sem_data, fora_da_janela, erro}."""
    resultado = {"itens": [], "lidos": 0, "sem_data": 0, "fora_da_janela": 0, "erro": "", "status": 0}
    fila = [(f.url, 0)]
    vistos_xml = set()
    filhos_lidos = 0
    todos = []
    while fila:
        url, prof = fila.pop(0)
        if url in vistos_xml:
            continue
        vistos_xml.add(url)
        r = baixar(url, cache_dir=cache_dir, hoje=hoje)
        if prof == 0:
            resultado["status"] = r["status"]
        if not r["dados"]:
            if prof == 0:
                resultado["erro"] = r["motivo"] or f"HTTP {r['status']}"
            continue
        doc = interpretar(r["dados"])
        if doc["tipo"] == "invalido":
            if prof == 0:
                resultado["erro"] = "conteúdo não é feed nem sitemap"
            continue
        if doc["tipo"] == "indice" and prof < 2:
            filhos = doc["filhos"]
            # so filhos que podem ter conteudo da janela; mais recentes primeiro
            def ordem(c):
                d = parse_data(c["lastmod"])
                return (d is None, -(d.toordinal()) if d else 0, c["url"])
            candidatos = [c for c in filhos if parse_data(c["lastmod"]) is None or
                          parse_data(c["lastmod"]) >= hoje - timedelta(days=janela_dias)]
            for c in sorted(candidatos, key=ordem):
                if filhos_lidos >= MAX_FILHOS_SITEMAP:
                    break
                filhos_lidos += 1
                fila.append((c["url"], prof + 1))
            continue
        todos.extend(doc["itens"])
    resultado["lidos"] = len(todos)
    rx_inc = re.compile(f.incluir) if f.incluir else None
    vistos = set()
    dentro = []
    for it in todos:
        if rx_inc and not rx_inc.search(it["url"]):
            continue
        u = canonica(it["url"])
        if u in vistos:
            continue
        vistos.add(u)
        d = parse_data(it["data"])
        if d is None:
            resultado["sem_data"] += 1
            continue
        if not na_janela(d, hoje, janela_dias):
            resultado["fora_da_janela"] += 1
            continue
        dentro.append({**it, "url": u, "data_item": d.isoformat()})
    dentro.sort(key=lambda x: x["data_item"], reverse=True)
    resultado["itens"] = dentro[:max_itens]
    return resultado


# --------------------------------------------------------------------------
# Busca (opcional): Brave com chave, ou resultados registrados a mao
# --------------------------------------------------------------------------

def buscas_registradas(cache_dir: Path) -> dict:
    return ler_json(cache_dir / "buscas.json", {})


def registrar_buscas(cache_dir: Path, lista: list[dict]) -> int:
    """lista de {categoria, consulta, idioma, resultados:[{url,titulo}]}; sobrescreve a mesma consulta."""
    d = buscas_registradas(cache_dir)
    for it in lista:
        cat = it["categoria"]
        d.setdefault(cat, {})[it["consulta"]] = {
            "idioma": it.get("idioma", ""), "provedor": it.get("provedor", "manual"),
            "executada_em": date.today().isoformat(),
            "resultados": [{"url": canonica(r["url"]), "titulo": r.get("titulo", "")} for r in it.get("resultados", []) if r.get("url")],
        }
    gravar_json(cache_dir / "buscas.json", d, indent=1)
    return len(lista)


def executar_buscas(categoria: str, consultas: list[tuple[str, str]], teto: int, cache_dir: Path,
                    dry_run: bool = False) -> tuple[list[dict], dict]:
    """Devolve ({url,titulo,consulta,idioma}, info). Brave so com BUSCA_PROVIDER=brave e BRAVE_API_KEY.
    Sem chave, usa so o que foi registrado; consulta sem resultado registrado fica pendente."""
    info = {"provedor": "nenhum", "usadas": 0, "pendentes": 0, "motivo": ""}
    registro = buscas_registradas(cache_dir).get(categoria, {})
    chave = os.getenv("BRAVE_API_KEY", "")
    brave = os.getenv("BUSCA_PROVIDER", "manual").lower() == "brave" and bool(chave)
    resultados: list[dict] = []
    novos = []
    for idioma, q in consultas[:teto]:
        reg = registro.get(q)
        if reg is None and brave and not dry_run:
            try:
                req = Request(f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(q)}&count=10&freshness=pm",
                              headers={"X-Subscription-Token": chave, "Accept": "application/json"})
                with urlopen(req, timeout=30) as r:
                    dados = json.loads(r.read().decode("utf-8"))
                res = [{"url": x["url"], "titulo": x.get("title", "")} for x in dados.get("web", {}).get("results", [])]
                novos.append({"categoria": categoria, "consulta": q, "idioma": idioma, "provedor": "brave", "resultados": res})
                reg = {"idioma": idioma, "resultados": res}
                time.sleep(1.1)
            except Exception as e:
                info["motivo"] = f"Brave falhou: {type(e).__name__}"
        if reg is None:
            info["pendentes"] += 1
            continue
        info["usadas"] += 1
        for r in reg["resultados"]:
            resultados.append({"url": r["url"], "titulo": r.get("titulo", ""), "consulta": q, "idioma": reg.get("idioma") or idioma})
    if novos:
        registrar_buscas(cache_dir, novos)
        info["provedor"] = "brave"
    elif info["usadas"]:
        info["provedor"] = "registro manual"
    if not brave and not info["usadas"] and not info["motivo"]:
        info["motivo"] = ("sem BRAVE_API_KEY e sem resultados registrados em buscas.json: "
                          "seguindo só com feeds (use registrar-buscas para incluir consultas)")
    return resultados, info


# --------------------------------------------------------------------------
# Trechos
# --------------------------------------------------------------------------

_FIM_FRASE = ('.', '!', '?', '"', '”', "'", ')', '…')
_FIM = ('.', '!', '?', '"', '”', "'", ')', '…', ':')


def blocos(texto: str) -> list[str]:
    """Reconstroi paragrafos a partir das linhas do texto guardado (que quebra em cada tag inline).
    Une linha seguinte quando a anterior nao fechou frase ou a seguinte comeca em minuscula.
    Todo bloco continua literal: so troca quebra de linha por espaco."""
    saida: list[str] = []
    atual: list[str] = []

    def fechar():
        if atual:
            b = normalizar(" ".join(atual))
            curtas = sum(1 for x in atual if len(x) < 25)
            # titulo ou menu nao e paragrafo: paragrafo fecha frase e nao e feito so de linhas curtas
            if b and b.endswith(_FIM_FRASE) and not (len(atual) >= 4 and curtas * 2 > len(atual)):
                saida.append(b)
            atual.clear()

    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if atual:
            ant = atual[-1]
            continua = (linha[0].islower() or linha[0] in ',;:.)%'
                        or (not ant.endswith(_FIM) and len(linha) < 25))
            if not continua or len(" ".join(atual)) > 1500:
                fechar()
        atual.append(linha)
    fechar()
    return saida


def extrair_trechos(p: Pagina, rx_voc: re.Pattern | None, rx_sinal: re.Pattern | None) -> list[str]:
    """Ate MAX_TRECHOS paragrafos com palavra do vocabulario, os de mais sinal primeiro, na ordem da pagina."""
    pontuados = []
    for i, b in enumerate(blocos(p.texto)):
        if len(b) < 60:
            continue
        v = contar(rx_voc, b)
        if v == 0:
            continue
        s = contar(rx_sinal, b)
        pontuados.append((v + 2 * s, i, recortar(b, TRECHO_MAX)))
    melhores = sorted(pontuados, key=lambda x: (-x[0], x[1]))[:MAX_TRECHOS]
    return [t for _, _, t in sorted(melhores, key=lambda x: x[1])]


# --------------------------------------------------------------------------
# Coleta
# --------------------------------------------------------------------------

_STOP_IDIOMA = {"en": {"the", "and", "of", "to", "is", "in", "that", "for", "are", "with", "how", "what"},
                "pt": {"o", "a", "de", "que", "para", "não", "uma", "com", "os", "como", "em", "é"},
                "es": {"el", "la", "de", "que", "los", "para", "una", "con", "las", "cómo", "en", "es"}}


def idioma_do_texto(texto: str, padrao: str = "en") -> str:
    palavras = re.findall(r"[\wáéíóúãõâêôçñü]+", texto[:6000].lower())
    placar = {l: sum(1 for w in palavras if w in s) for l, s in _STOP_IDIOMA.items()}
    melhor = max(placar, key=placar.get)
    return melhor if placar[melhor] >= 3 else padrao


def data_da_pagina(p: Pagina) -> str:
    """AAAA-MM-DD da pagina (meta, JSON-LD, URL) ou 'not found'. Reusa a regra da vertical duvidas_mercado."""
    from scraper_lab.duvidas_mercado import data_da_pagina as _d
    return _d(p)


def _slug_url(url: str) -> str:
    return re.sub(r"[-_/]+", " ", urlparse(url).path)


def _publicador_da_url(fontes: list[Fonte], url: str, p: Pagina | None) -> str:
    for f in fontes:
        if casa_dominio(url, dominio(f.url)) or dominio(url).split(".")[-2:] == dominio(f.url).split(".")[-2:]:
            return f.publicador
    if p is not None and p.meta.get("og:site_name"):
        return p.meta["og:site_name"]
    return dominio(url)


def coletar(config: Path, categoria: str, janela_dias: int, saida: Path, *, teto_paginas: int = TETO_PAGINAS_PADRAO,
            teto_buscas: int = TETO_BUSCAS_PADRAO, dry_run: bool = False, hoje: date | None = None,
            cache_dir: Path | None = None, navegador: bool = False, log=print) -> dict:
    hoje = hoje or date.today()
    cache_dir = Path(cache_dir) if cache_dir else CACHE_RADAR
    cfg = carregar_config(config, categoria)
    for a in cfg.avisos:
        log(f"  [aviso] {a}")
    rx_voc = compilar_termos(cfg.vocabulario)
    rx_sinal = compilar_termos(cfg.sinais)

    meta = {"categoria": categoria, "janela_dias": janela_dias, "data_corrida": hoje.isoformat(),
            "fontes_lidas": 0, "itens_de_feed": 0, "paginas_abertas": 0, "consultas_usadas": 0, "bloqueados": [],
            "avisos": cfg.avisos, "fontes_com_falha": [], "itens_na_janela": 0, "itens_com_vocabulario": 0,
            "paginas_do_cache": 0, "busca": {}, "dry_run": dry_run}

    # 1. feeds e sitemaps
    itens: list[dict] = []
    for f in cfg.fontes:
        if dry_run:
            log(f"  [plano] {f.publicador} ({f.idioma}, {f.tipo}) {f.url}")
            continue
        r = ler_fonte(f, cache_dir=cache_dir / "feeds", hoje=hoje, janela_dias=janela_dias)
        if r["erro"] and not r["itens"] and not r["lidos"]:
            meta["fontes_com_falha"].append({"publicador": f.publicador, "url": f.url, "motivo": r["erro"]})
            log(f"  [falha] {f.publicador} {f.url}: {r['erro']}")
            continue
        meta["fontes_lidas"] += 1
        meta["itens_de_feed"] += len(r["itens"])
        log(f"  [fonte] {f.publicador:28} {f.tipo:7} lidos {r['lidos']:5} na janela {len(r['itens']):4} sem data {r['sem_data']}")
        for it in r["itens"]:
            itens.append({**it, "publicador": f.publicador, "idioma_feed": f.idioma,
                          "origem": f"feed: {f.publicador} ({f.url})"})
    meta["itens_na_janela"] = len(itens)

    # 2. consultas
    achados_busca, info = executar_buscas(categoria, cfg.consultas.get(categoria, []), teto_buscas, cache_dir, dry_run)
    meta["consultas_usadas"] = info["usadas"]
    meta["busca"] = info
    if info["motivo"]:
        log(f"  [busca] {info['motivo']}")
    vistos = {i["url"] for i in itens}
    for r in achados_busca:
        u = canonica(r["url"])
        if u in vistos:
            continue
        vistos.add(u)
        itens.append({"url": u, "titulo": r["titulo"], "resumo": "", "data": "", "data_item": "",
                      "publicador": "", "idioma_feed": r["idioma"], "origem": f"consulta: {r['consulta']}"})

    # 3. prioridade: relevancia previa (titulo, resumo, slug), intercalando publicadores
    pontuados = []
    descartados = 0
    for it in itens:
        score = contar(rx_voc, " ".join([it["titulo"], it["resumo"], _slug_url(it["url"])]))
        if score == 0 and not it["origem"].startswith("consulta"):
            descartados += 1
            continue
        it["_score"] = score + contar(rx_sinal, " ".join([it["titulo"], it["resumo"]]))
        pontuados.append(it)
    meta["itens_com_vocabulario"] = len(pontuados)
    por_pub: dict[str, list[dict]] = {}
    for it in sorted(pontuados, key=lambda x: (-x["_score"], x.get("data_item", ""))):
        por_pub.setdefault(it["publicador"] or it["origem"], []).append(it)
    ordem: list[dict] = []
    while any(por_pub.values()) and len(ordem) < teto_paginas:
        for k in list(por_pub):
            if por_pub[k] and len(ordem) < teto_paginas:
                ordem.append(por_pub[k].pop(0))
    if dry_run:
        log(f"  [plano] {len(ordem)} páginas seriam abertas (teto {teto_paginas}); {descartados} itens sem vocabulário")
        return {"meta": meta, "candidatos": []}

    # 4. abrir paginas
    cache = CachePaginas(cache_dir, cfg.bloqueios)
    candidatos: list[dict] = []
    bloqueados: list[dict] = []
    for it in ordem:
        p = cache.abrir(it["url"], navegador=navegador)
        if p.estado != "ok":
            bloqueados.append({"url": it["url"], "estado": p.estado, "motivo": p.motivo or f"HTTP {p.status}"})
            continue
        trechos = extrair_trechos(p, rx_voc, rx_sinal)
        if not trechos:
            continue
        d_pag = data_da_pagina(p)
        d_item = it.get("data_item") or ""
        data_final = d_pag if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d_pag) else (d_item or d_pag)
        dd = parse_data(data_final) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_final) else None
        if dd is not None and not na_janela(dd, hoje, janela_dias):
            continue   # a pagina diz que e antiga mesmo que o sitemap diga que mudou na janela
        candidatos.append({
            "url": it["url"],
            "publicador": it["publicador"] or _publicador_da_url(cfg.fontes, it["url"], p),
            "titulo": p.h1[0] if p.h1 else (it["titulo"] or p.titulo),
            "data_pagina": data_final,
            "idioma": idioma_do_texto(p.texto, it.get("idioma_feed") or "en"),
            "consulta_ou_feed": it["origem"],
            "trechos": trechos,
            "cache_path": str(cache._arquivo(it["url"])),
            "score": it["_score"],
        })
    meta["paginas_abertas"] = cache.stats["abertas_agora"]
    meta["paginas_do_cache"] = cache.stats["do_cache"]
    meta["bloqueados"] = bloqueados
    candidatos.sort(key=lambda c: c["data_pagina"], reverse=True)

    doc = {"meta": meta, "candidatos": candidatos}
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    gravar_json(saida / f"candidatos-{categoria}.json", doc, indent=2)
    return doc


# --------------------------------------------------------------------------
# Conferencia literal
# --------------------------------------------------------------------------

def _paginas_em_cache(cache: CachePaginas) -> list[Pagina]:
    return cache.todas()


def conferir(arquivo: Path, *, cache_dir: Path | None = None, navegador: bool = False, log=print) -> dict:
    """Cada sinais[].evidencias[].valor precisa estar literalmente na pagina (cache ou aberta agora)."""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_RADAR
    doc = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    cache = CachePaginas(cache_dir)
    violacoes: list[dict] = []
    verificadas = 0
    todas: list[Pagina] | None = None
    for i, s in enumerate(doc.get("sinais", [])):
        sid = s.get("id") or s.get("sinal") or f"#{i}"
        for j, ev in enumerate(s.get("evidencias", []) or []):
            valor = ev.get("valor")
            url = ev.get("url") or ev.get("fonte") or s.get("url") or ""
            base = {"sinal": sid, "evidencia": j, "url": url, "valor": valor}
            if not isinstance(valor, str) or not valor.strip():
                violacoes.append({**base, "motivo": "evidência sem 'valor' em texto"})
                continue
            verificadas += 1
            if url:
                p = cache.abrir(url, navegador=navegador)
                if not p.ok:
                    violacoes.append({**base, "motivo": f"página não abre ({p.estado}: {p.motivo or p.status}); não verificável"})
                    continue
                if not citacao_confere(valor, p.texto_validacao()):
                    violacoes.append({**base, "motivo": "citação ausente do texto da página"})
            else:
                if todas is None:
                    todas = _paginas_em_cache(cache)
                if not any(p.ok and citacao_confere(valor, p.texto_validacao()) for p in todas):
                    violacoes.append({**base, "motivo": "evidência sem URL e citação não encontrada em nenhuma página do cache"})
    res = {"arquivo": str(arquivo), "conferido_em": datetime.now(timezone.utc).isoformat(),
           "evidencias_verificadas": verificadas, "violacoes": violacoes, "ok": not violacoes}
    gravar_json(Path(str(arquivo) + ".conferencia.json"), res, indent=2)
    return res


# --------------------------------------------------------------------------
# Saude dos feeds
# --------------------------------------------------------------------------

def checar_fontes(config: Path, *, cache_dir: Path | None = None, hoje: date | None = None, janela_dias: int = 90,
                  atualizar: bool = False, log=print) -> list[dict]:
    """Status HTTP, tipo, numero de itens e data do mais novo de cada fonte. Sem cache: o ponto e ver agora."""
    hoje = hoje or date.today()
    bruto = json.loads(Path(config).read_text(encoding="utf-8"))
    avisos: list[str] = []
    fontes = _fontes_de(bruto, avisos)
    for a in avisos:
        log(f"  [aviso] {a}")
    linhas = []
    for f in fontes:
        r = baixar(f.url, cache_dir=None, hoje=hoje)
        linha = {"publicador": f.publicador, "idioma": f.idioma, "url": f.url, "status_http": r["status"],
                 "tipo_detectado": "", "itens": 0, "mais_novo": "", "itens_na_janela": 0, "estado": "", "motivo": r["motivo"],
                 "verificado_em": hoje.isoformat()}
        if r["dados"]:
            doc = interpretar(r["dados"])
            linha["tipo_detectado"] = doc["tipo"]
            if doc["tipo"] == "indice":
                linha["itens"] = len(doc["filhos"])
                datas = [d for d in (parse_data(c["lastmod"]) for c in doc["filhos"]) if d]
            else:
                linha["itens"] = len(doc["itens"])
                datas = [d for d in (parse_data(i["data"]) for i in doc["itens"]) if d]
            if datas:
                linha["mais_novo"] = max(datas).isoformat()
                linha["itens_na_janela"] = sum(1 for d in datas if na_janela(d, hoje, janela_dias))
            if doc["tipo"] == "invalido":
                linha["estado"], linha["motivo"] = "invalido", "não é feed nem sitemap"
            elif not datas:
                linha["estado"], linha["motivo"] = "sem_datas", "sem datas legíveis"
            elif max(datas) < hoje - timedelta(days=janela_dias):
                linha["estado"] = "parado"
            else:
                linha["estado"] = "vivo"
        else:
            linha["estado"] = "fora"
        linhas.append(linha)
        log(f"  {linha['estado']:9} {linha['status_http']:>3} {f.publicador:26} {f.idioma} {linha['tipo_detectado']:8} "
            f"itens {linha['itens']:5} novo {linha['mais_novo'] or '-':10} {f.url}")
    if atualizar:
        _gravar_status(Path(config), bruto, linhas)
    return linhas


def _gravar_status(caminho: Path, bruto: dict, linhas: list[dict]) -> None:
    por_url = {l["url"]: l for l in linhas}
    campos = ("status_http", "estado", "tipo_detectado", "itens", "mais_novo", "itens_na_janela", "motivo", "verificado_em")
    fontes = bruto.get("fontes_feeds")
    if isinstance(fontes, list):
        for it in fontes:
            for chave in ("url", "feed", "rss", "atom", "sitemap"):
                u = it.get(chave) if isinstance(it, dict) else None
                if u in por_url:
                    it["status"] = {c: por_url[u][c] for c in campos}
                    break
    gravar_json(caminho, bruto, indent=2)
