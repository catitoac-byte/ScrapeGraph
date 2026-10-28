"""
Vertical duvidas_mercado: perguntas, dores, objecoes e mitos do mercado por
produto da Cassi.ai, em citacao literal com URL e data.

Varreduras (PRD em videos-linkedin/varredura-mercado/PRD_E_PROMPT.md):

    P1 perguntas e duvidas     P2 dores ditas
    P3 objecoes e medos        P4 mitos e confusoes
    P5 sintese por produto, sem busca nova

Reaproveita o padrao da vertical sinteticos: cache de paginas em disco
(CachePaginas), registro de buscas com teto, citacao recortada do proprio texto
guardado e validador que reabre o texto guardado para conferir cada valor.

Motor de extracao. Com LLM_PROVIDER=manual (padrao do projeto) a extracao e por
padroes de linguagem em en, pt e es: a frase sai recortada da pagina, entao e
literal por construcao. Com provedor configurado, o LLM propoe os achados e a
mesma conferencia literal descarta o que nao estiver na pagina. Resultado de
busca so indica onde olhar: nenhum achado nasce de snippet.

Busca. Provedor "manual" le as buscas registradas pelo operador
(`raspar_duvidas_mercado.py --registrar arquivo.json`); BUSCA_PROVIDER=brave com
BRAVE_API_KEY executa sozinho. O teto por produto e por varredura vale nos dois.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from scraper_lab.llm import provedor_ativo
from scraper_lab.pipeline import gravar_json, ler_json
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
VARREDURAS = ("P1", "P2", "P3", "P4")
GRUPOS = ("comprador", "praticante", "fornecedor", "comentarista", "associacao", "academico")


class TetoDeBuscas(RuntimeError):
    pass


def _expandir(caminho: str) -> Path:
    return Path(os.path.expanduser(caminho))


# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------

def carregar_config(vid: str = "duvidas_mercado") -> dict:
    cfg = json.loads((VERTICAIS / f"{vid}.json").read_text(encoding="utf-8"))
    cfg["_cache"] = RAIZ / "dados" / "cache" / cfg["saida"]
    cfg["_saida"] = RAIZ / "dados" / "saida" / cfg["saida"]
    return cfg


def nomes_proibidos(cfg: dict) -> list[str]:
    caminho = _expandir(cfg.get("clientes_nunca_citar", ""))
    if caminho.is_file():
        return [n for n in json.loads(caminho.read_text(encoding="utf-8")).get("nomes", []) if n]
    return []


def carregar_schema(cfg: dict) -> dict:
    return json.loads(_expandir(cfg["schema"]).read_text(encoding="utf-8"))


def tetos_por_varredura(cfg: dict, total: int) -> dict[str, int]:
    """Reparte o teto do produto entre P1 a P4 na proporcao do config, pelo
    maior resto, sem passar do teto de cada varredura."""
    base = cfg["teto_buscas_por_varredura"]
    soma = sum(base.values())
    total = min(total, soma)
    brutos = {v: total * base[v] / soma for v in VARREDURAS}
    tetos = {v: int(brutos[v]) for v in VARREDURAS}
    sobra = total - sum(tetos.values())
    for v in sorted(VARREDURAS, key=lambda x: brutos[x] - tetos[x], reverse=True)[:sobra]:
        tetos[v] += 1
    return {v: min(tetos[v], base[v]) for v in VARREDURAS}


# --------------------------------------------------------------------------
# Consultas e registro de buscas
# --------------------------------------------------------------------------

def _intercalar(listas: list[list]) -> list:
    filas = [list(x) for x in listas]
    saida = []
    while any(filas):
        for f in filas:
            if f:
                saida.append(f.pop(0))
    return saida


def consultas_da_varredura(cfg: dict, slug: str, v: str) -> list[tuple[str, str]]:
    """(idioma, consulta) em ordem de prioridade, idiomas alternados.
    P1 abre com as consultas do proprio produto; todas as varreduras seguem
    com os modelos aplicados a cada tema (em pt e es, o tema e a consulta do
    produto no idioma, porque temas_de_mercado esta em ingles)."""
    prod = cfg["produtos"][slug]
    idiomas = cfg["idiomas"]
    por_idioma = []
    for lang in idiomas:
        qs: list[str] = []
        if v == "P1":
            qs += prod["consultas"].get(lang, [])
        temas = prod["temas_de_mercado"] if lang == "en" else [
            " ".join(q.split()[:5]) for q in prod["consultas"].get(lang, [])]
        for t in temas:
            for modelo in cfg["modelos_por_varredura"][v].get(lang, []):
                qs.append(modelo.replace("{tema}", t))
        vistos, unicas = set(), []
        for q in qs:
            if q not in vistos:
                vistos.add(q)
                unicas.append(q)
        por_idioma.append([(lang, q) for q in unicas])
    return _intercalar(por_idioma)


class RegistroBuscas:
    """Cada busca executada, por produto e varredura. O teto conta aqui."""

    def __init__(self, arquivo: Path):
        self.arquivo = arquivo
        self.d: dict[str, dict[str, list[dict]]] = ler_json(arquivo, {})

    def lista(self, slug: str, v: str | None = None) -> list[dict]:
        por_v = self.d.get(slug, {})
        if v:
            return por_v.get(v, [])
        return [b for x in por_v.values() for b in x]

    def usadas(self, slug: str, v: str | None = None) -> int:
        return len(self.lista(slug, v))

    def feitas(self, slug: str, v: str) -> set[str]:
        return {b["consulta"] for b in self.lista(slug, v)}

    def pendentes(self, cfg: dict, slug: str, v: str, teto_v: int, teto_total: int) -> list[tuple[str, str]]:
        feitas = self.feitas(slug, v)
        resto_v = max(0, teto_v - self.usadas(slug, v))
        resto_t = max(0, teto_total - self.usadas(slug))
        cand = [x for x in consultas_da_varredura(cfg, slug, v) if x[1] not in feitas]
        return cand[: min(resto_v, resto_t)]

    def registrar(self, slug: str, v: str, consulta: str, idioma: str, resultados: list[dict],
                  teto_v: int, teto_total: int, provedor: str = "manual") -> None:
        lista = self.d.setdefault(slug, {}).setdefault(v, [])
        existente = next((b for b in lista if b["consulta"] == consulta), None)
        if existente is None:
            if len(lista) >= teto_v:
                raise TetoDeBuscas(f"{slug} {v}: teto de {teto_v} buscas atingido; '{consulta}' não registrada")
            if self.usadas(slug) >= teto_total:
                raise TetoDeBuscas(f"{slug}: teto de {teto_total} buscas atingido; '{consulta}' não registrada")
        reg = {"consulta": consulta, "idioma": idioma, "provedor": provedor, "executada_em": HOJE,
               "resultados": [{"url": canonica(r["url"]), "titulo": r.get("titulo", "")}
                              for r in resultados if r.get("url")]}
        if existente is None:
            lista.append(reg)
        else:
            existente.update(reg)
        gravar_json(self.arquivo, self.d)


def buscar_por_api(corrida: "Corrida", slug: str) -> int:
    """Executa as consultas pendentes no Brave. Cada chamada conta como busca."""
    chave = os.getenv("BRAVE_API_KEY", "")
    if os.getenv("BUSCA_PROVIDER", "manual").lower() != "brave" or not chave:
        raise RuntimeError("Busca automática exige BUSCA_PROVIDER=brave e BRAVE_API_KEY no ambiente. "
                           "Sem isso, use --pendentes e --registrar.")
    feitas = 0
    for v in VARREDURAS:
        for idioma, q in corrida.buscas.pendentes(corrida.cfg, slug, v, corrida.tetos[v], corrida.teto_total):
            req = Request(f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(q)}&count=10",
                          headers={"X-Subscription-Token": chave, "Accept": "application/json"})
            with urlopen(req, timeout=30) as r:
                dados = json.loads(r.read().decode("utf-8"))
            res = [{"url": x["url"], "titulo": x.get("title", "")} for x in dados.get("web", {}).get("results", [])]
            corrida.buscas.registrar(slug, v, q, idioma, res, corrida.tetos[v], corrida.teto_total, "brave")
            feitas += 1
            time.sleep(1.1)
    return feitas


# --------------------------------------------------------------------------
# Corrida
# --------------------------------------------------------------------------

class Corrida:
    def __init__(self, cfg: dict, *, saida: Path | None = None, teto_buscas: int | None = None,
                 dry_run: bool = False):
        self.cfg = cfg
        self.saida = Path(saida) if saida else cfg["_saida"]
        self.teto_total = min(teto_buscas or cfg["teto_buscas_por_produto"], cfg["teto_buscas_por_produto"])
        self.tetos = tetos_por_varredura(cfg, self.teto_total)
        self.dry_run = dry_run
        self.paginas = CachePaginas(cfg["_cache"], cfg.get("bloqueios_conhecidos"))
        self.buscas = RegistroBuscas(cfg["_cache"] / "buscas.json")
        self.proibidos = nomes_proibidos(cfg)
        self.llm_chamadas = 0
        self._rx = {v: {l: re.compile(p, re.I) for l, p in d.items()} for v, d in cfg["padroes"].items()}
        self._ruido = re.compile(
            r"(cookie|subscribe|newsletter|sign[ -]?up|log ?in|privacy policy|terms of|accept all|contact us|"
            r"book a demo|get started|free trial|request a demo|all rights reserved|assine|inscreva|fale conosco|"
            r"suscr[ií]b|iniciar sesi[oó]n|read more|share this|follow us)", re.I)

    def arquivo(self, slug: str) -> Path:
        return self.saida / f"{slug}.json"


# --------------------------------------------------------------------------
# Texto: idioma, relevancia, grupo, data
# --------------------------------------------------------------------------

_STOP = {"en": {"the", "and", "of", "to", "is", "in", "that", "for", "are", "with", "how", "what"},
         "pt": {"o", "a", "de", "que", "para", "não", "uma", "com", "os", "como", "em", "é"},
         "es": {"el", "la", "de", "que", "los", "para", "una", "con", "las", "cómo", "en", "es"}}
_GENERICAS = {"market", "research", "insights", "using", "other", "pesquisa", "mercado", "investigación",
              "investigacion", "mercados", "empresa", "times", "teams", "analysis", "análisis", "análise",
              "survey", "surveys", "about", "which"}


def idioma_do_texto(texto: str) -> str:
    palavras = re.findall(r"[\wáéíóúãõâêôçñü]+", texto.lower())
    placar = {l: sum(1 for p in palavras if p in s) for l, s in _STOP.items()}
    melhor = max(placar, key=placar.get)
    return melhor if placar[melhor] >= 2 else "en"


def radicais_do_tema(cfg: dict, slug: str) -> set[str]:
    prod = cfg["produtos"][slug]
    fontes = list(prod["temas_de_mercado"]) + [q for l in prod["consultas"].values() for q in l]
    rad = set()
    for f in fontes:
        for w in re.findall(r"[\wáéíóúãõâêôçñü]{5,}", f.lower()):
            if w not in _GENERICAS:
                rad.add(w[:6])
    return rad


def relevancia(frase: str, radicais: set[str]) -> int:
    palavras = {w[:6] for w in re.findall(r"[\wáéíóúãõâêôçñü]{5,}", frase.lower())}
    return len(palavras & radicais)


def classificar_grupo(cfg: dict, url: str) -> str:
    if any(casa_dominio(url, d) for d in cfg["dominios_associacoes"]):
        return "associacao"
    if any(casa_dominio(url, d) for d in cfg["dominios_academicos"]) or re.search(r"\.(edu|ac\.[a-z]{2}|edu\.[a-z]{2})$", dominio(url)):
        return "academico"
    if any(casa_dominio(url, d) for d in cfg["dominios_comentaristas"]):
        return "comentarista"
    return "fornecedor"


_META_DATA = ("article:published_time", "citation_publication_date", "citation_date", "citation_online_date",
              "dc.date")


def data_da_pagina(p: Pagina) -> str:
    """AAAA-MM-DD, AAAA quando so o ano existe, ou 'not found'."""
    for k in _META_DATA:
        m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", p.meta.get(k, ""))
        if m:
            return f"{m[1]}-{m[2]}-{m[3]}"
    for bloco in p.jsonld:
        itens = bloco if isinstance(bloco, list) else [bloco]
        for it in itens:
            if isinstance(it, dict):
                for g in it.get("@graph", [it]) if isinstance(it.get("@graph", None), list) else [it]:
                    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(g.get("datePublished", "")))
                    if m:
                        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", p.url)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.search(r"/(20\d{2})/", p.url)
    if m:
        return m[1]
    return "not found"


# --------------------------------------------------------------------------
# Texto nosso
# --------------------------------------------------------------------------

_GANCHO = {
    "P1": "A pergunta aparece em público desse jeito, e o vídeo responde a ela em 30 a 60 segundos.",
    "P2": "A fala nomeia o que dói nesse trabalho e o que ele custa a quem responde pelo resultado.",
    "P3": "A fala mostra o receio que faz o comprador adiar a decisão, e o vídeo trata dele de frente.",
    "P4": "A fala revela uma confusão comum, e o vídeo separa os dois conceitos antes de qualquer função.",
}
_ROTULO_TEMA = {"P1": "dúvida sobre", "P2": "dor em", "P3": "objeção a", "P4": "confusão sobre"}
_PAPEL = {"fornecedor": "Página de fornecedor do setor de pesquisa",
          "comentarista": "Veículo ou comentarista do setor de pesquisa",
          "associacao": "Publicação de associação do setor",
          "academico": "Publicação acadêmica",
          "comprador": "Comprador de pesquisa",
          "praticante": "Praticante de pesquisa"}


def quem_da_pagina(p: Pagina) -> str:
    return p.meta.get("og:site_name") or registravel(p.url)


def angulo_video(prod: dict, v: str, quem: str) -> str:
    return (f"{prod['trabalho_pt']}. Hoje, {prod['hoje_pt']}. {_GANCHO[v]} "
            f"O vídeo parte da fala de {quem} e só no fim apresenta a Cassi-ai.")


# --------------------------------------------------------------------------
# Extracao
# --------------------------------------------------------------------------

_COMECO_PERGUNTA = re.compile(r"^(how|what|why|can|should|is|are|does|do|will|when|which|como|qual|quais|o que|por que|"
                              r"posso|devo|cómo|qué|por qué|cuál|puedo)\b", re.I)


def candidatos_da_pagina(corrida: Corrida, p: Pagina, slug: str, v: str, radicais: set[str]) -> list[tuple[float, str]]:
    """(pontuacao, frase literal) da pagina para a varredura v."""
    saida = []
    for f in p.frases():
        if corrida._ruido.search(f):
            continue
        if f.isupper() or f.count("|") >= 2:
            continue
        if v == "P1":
            if not f.endswith("?") or not 25 <= len(f) <= 300:
                continue
        else:
            if not 50 <= len(f) <= 600 or f.endswith("?"):
                continue
            if not corrida._rx[v][idioma_do_texto(f)].search(f):
                continue
        rel = relevancia(f, radicais)
        if rel < 1:
            continue
        nota = rel * 2.0
        if v == "P1" and _COMECO_PERGUNTA.match(f):
            nota += 1.5
        nota -= len(f) / 400
        saida.append((nota, recortar(f)))
    saida.sort(key=lambda x: -x[0])
    return saida


def _potencial(v: str, nota: float) -> str:
    if v == "P1" and nota >= 4.5:
        return "alto"
    return "alto" if nota >= 6 else ("medio" if nota >= 3 else "baixo")


def contem_proibido(corrida: Corrida, texto: str) -> bool:
    t = texto.lower()
    return any(n.lower() in t for n in corrida.proibidos)


def achado_de_frase(corrida: Corrida, slug: str, p: Pagina, v: str, frase: str, nota: float) -> dict:
    prod = corrida.cfg["produtos"][slug]
    grupo = classificar_grupo(corrida.cfg, p.url)
    quem = quem_da_pagina(p)
    return {
        "varredura": v,
        "pergunta_ou_fala": {"valor": frase, "tipo": "literal", "url": p.url,
                             "data_pagina": data_da_pagina(p), "data_captura": HOJE},
        "quem": quem,
        "papel": f"{_PAPEL[grupo]} ({registravel(p.url)})",
        "grupo": grupo,
        "idioma": idioma_do_texto(frase),
        "tema": f"{_ROTULO_TEMA[v]} {prod['tema_pt']}",
        "potencial_video": _potencial(v, nota),
        "angulo_video": angulo_video(prod, v, quem),
    }


def _chat(prompt: str) -> str:
    """Chamada unica ao LLM configurado (deepseek/openai compativeis, anthropic)."""
    p = provedor_ativo()
    chave = os.getenv({"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY",
                       "anthropic": "ANTHROPIC_API_KEY"}[p.nome], "")
    if p.nome == "anthropic":
        url, cab = "https://api.anthropic.com/v1/messages", {"x-api-key": chave, "anthropic-version": "2023-06-01"}
        corpo = {"model": p.modelo, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
    else:
        base = "https://api.deepseek.com" if p.nome == "deepseek" else "https://api.openai.com"
        url, cab = f"{base}/v1/chat/completions", {"Authorization": f"Bearer {chave}"}
        corpo = {"model": p.modelo, "messages": [{"role": "user", "content": prompt}]}
    req = Request(url, data=json.dumps(corpo).encode(), headers={**cab, "Content-Type": "application/json"})
    with urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["content"][0]["text"] if p.nome == "anthropic" else d["choices"][0]["message"]["content"]


def achados_por_llm(corrida: Corrida, slug: str, p: Pagina, v: str) -> list[dict]:
    """O LLM so escolhe frases e escreve o texto nosso. A citacao continua
    sujeita ao mesmo conferidor literal, entao frase inventada cai fora."""
    prod = corrida.cfg["produtos"][slug]
    pedido = (f"Varredura {v} para o produto {prod['nome']} (tema: {prod['tema_pt']}). Da página abaixo, copie ATÉ 3 frases "
              f"LITERAIS (sem alterar uma palavra) que sejam, conforme a varredura: P1 pergunta, P2 dor dita, P3 objeção ou "
              f"medo, P4 mito ou confusão. Responda só um JSON: lista de objetos com valor (frase literal), pt (tradução "
              f"livre para português do Brasil, ou null se já estiver em português), quem (autor ou veículo).\n\n"
              f"PÁGINA {p.url}\n{p.texto[:24000]}")
    corrida.llm_chamadas += 1
    bruto = _chat(pedido)
    m = re.search(r"\[.*\]", bruto, re.S)
    try:
        itens = json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []
    saida = []
    for it in itens if isinstance(itens, list) else []:
        valor = recortar(str((it or {}).get("valor", "")))
        if len(valor) < 25 or not citacao_confere(valor, p.texto_validacao()):
            continue
        a = achado_de_frase(corrida, slug, p, v, valor, 4.0)
        if it.get("quem"):
            a["quem"] = str(it["quem"])[:80]
        if a["idioma"] != "pt" and it.get("pt"):
            a["pt"] = {"valor": str(it["pt"]), "tipo": "traducao_livre"}
        saida.append(a)
    return saida


def paginas_para_abrir(corrida: Corrida, slug: str) -> list[tuple[str, str]]:
    """(varredura, url) das paginas a abrir: ate teto_paginas_por_busca de cada
    busca registrada, sem repetir URL nem abrir dominio ignorado."""
    vistas, saida = set(), []
    limite = corrida.cfg["teto_paginas_por_busca"]
    for v in VARREDURAS:
        for b in corrida.buscas.lista(slug, v):
            tomadas = 0
            for r in b["resultados"]:
                u = canonica(r["url"])
                if tomadas >= limite:
                    break
                if any(casa_dominio(u, d) for d in corrida.cfg["dominios_ignorados"]):
                    continue
                tomadas += 1
                if u not in vistas:
                    vistas.add(u)
                    saida.append((v, u))
    return saida


def abrir_paginas(corrida: Corrida, slug: str) -> list[Pagina]:
    """Abre (ou le do cache) cada pagina candidata. Retomavel: pagina guardada
    nao e buscada de novo; bloqueio vira not accessible e nao se insiste."""
    abertas = []
    for _v, u in paginas_para_abrir(corrida, slug):
        abertas.append(corrida.paginas.abrir(u))
    return abertas


def ficha_do_produto(corrida: Corrida, slug: str) -> list[dict]:
    """Achados escritos pelo operador, em dados/cache/duvidas_mercado/fichas/<slug>.json.
    Passam pelo mesmo validador."""
    return ler_json(corrida.cfg["_cache"] / "fichas" / f"{slug}.json", [])


def extrair_achados(corrida: Corrida, slug: str, paginas: list[Pagina]) -> tuple[list[dict], dict]:
    cfg = corrida.cfg
    radicais = radicais_do_tema(cfg, slug)
    por_v_url = {(v, u) for v, u in paginas_para_abrir(corrida, slug)}
    usar_llm = provedor_ativo().pronto and provedor_ativo().nome != "manual"
    achados, vistos, descartados = [], set(), Counter()
    por_pagina: Counter = Counter()

    def adicionar(a: dict) -> bool:
        chave = (canonica(a["pergunta_ou_fala"]["url"]), normalizar(a["pergunta_ou_fala"]["valor"]).lower())
        if chave in vistos:
            descartados["duplicado"] += 1
            return False
        if contem_proibido(corrida, a["pergunta_ou_fala"]["valor"]):
            descartados["nome_proibido"] += 1
            return False
        vistos.add(chave)
        achados.append(a)
        return True

    for a in ficha_do_produto(corrida, slug):
        adicionar(a)

    ordem = {v: i for i, v in enumerate(VARREDURAS)}
    for p in sorted(paginas, key=lambda x: x.url):
        if not p.ok:
            continue
        varreduras_da_pagina = sorted({v for v, u in por_v_url if u == p.url}, key=ordem.get)
        # uma pagina achada por busca de P1 tambem pode servir a P2 a P4
        for v in VARREDURAS:
            if len(achados) >= cfg["max_achados_por_produto"] or por_pagina[p.url] >= cfg["max_achados_por_pagina"]:
                break
            if usar_llm:
                novos = achados_por_llm(corrida, slug, p, v) if v in varreduras_da_pagina else []
            else:
                cand = candidatos_da_pagina(corrida, p, slug, v, radicais)[:1]
                novos = [achado_de_frase(corrida, slug, p, v, f, n) for n, f in cand]
            for a in novos:
                if por_pagina[p.url] < cfg["max_achados_por_pagina"] and adicionar(a):
                    por_pagina[p.url] += 1
    return achados, dict(descartados)


# --------------------------------------------------------------------------
# P5: sintese sem busca nova
# --------------------------------------------------------------------------

def _tokens(frase: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[\wáéíóúãõâêôçñü]{5,}", frase.lower()) if w not in _GENERICAS}


def ranquear(achados: list[dict], limite: int = 10) -> list[str]:
    """Repeticao entre fontes independentes (dominios registraveis diferentes
    com frases de vocabulario parecido) mais potencial de video."""
    pot = {"alto": 3, "medio": 2, "baixo": 1}
    tok = {a["id"]: _tokens(a["pergunta_ou_fala"]["valor"]) for a in achados}
    dom = {a["id"]: registravel(a["pergunta_ou_fala"]["url"]) for a in achados}
    placar = {}
    for a in achados:
        parecidos = {dom[b["id"]] for b in achados if b["id"] != a["id"] and dom[b["id"]] != dom[a["id"]]
                     and len(tok[a["id"]] & tok[b["id"]]) >= 3}
        bonus_p1 = 1 if a["varredura"] == "P1" else 0
        placar[a["id"]] = len(parecidos) * 2 + pot[a["potencial_video"]] + bonus_p1
    return [i for i, _ in sorted(placar.items(), key=lambda x: (-x[1], x[0]))][:limite]


def sintese(corrida: Corrida, slug: str, achados: list[dict], bloqueados: list[str], descartados: dict) -> dict:
    mins = corrida.cfg["minimos"]
    lacunas = []
    if len(achados) < mins["achados"]:
        lacunas.append(f"Só {len(achados)} achados literais com pergunta, dor, objeção ou mito neste teto de "
                       f"{corrida.teto_total} buscas; o mínimo é {mins['achados']}. Faltou completar com mais buscas, "
                       f"sem usar citação fraca.")
    grupos = {a["grupo"] for a in achados}
    if len(grupos) < mins["grupos"]:
        lacunas.append(f"Só {len(grupos)} grupo(s) de fonte ({', '.join(sorted(grupos)) or 'nenhum'}); faltou variedade.")
    if "comprador" not in grupos:
        lacunas.append("Comprador em primeira pessoa: not found. A coleta por padrão de texto só distingue fornecedor, "
                       "comentarista, associação e academia; a fala de comprador entra por ficha do operador.")
    idiomas = {a["idioma"] for a in achados}
    if len(idiomas) < mins["idiomas"]:
        lacunas.append(f"Só {len(idiomas)} idioma(s) nos achados ({', '.join(sorted(idiomas)) or 'nenhum'}).")
    for v in VARREDURAS:
        if not any(a["varredura"] == v for a in achados):
            lacunas.append(f"Varredura {v}: not found nas páginas abertas.")
    if any(a["idioma"] != "pt" for a in achados) and corrida.llm_chamadas == 0:
        lacunas.append("Tradução para o português ausente nos achados em outro idioma: a corrida rodou sem LLM.")
    if bloqueados:
        lacunas.append(f"{len(bloqueados)} fonte(s) em meta.bloqueados ficaram sem leitura (not accessible).")
    if descartados.get("nome_proibido"):
        lacunas.append(f"{descartados['nome_proibido']} frase(s) descartadas por citar nome de cliente que não pode aparecer.")
    return {
        "top_perguntas": ranquear(achados),
        "lacunas": lacunas,
        "nota": "Ranking inferido a partir dos achados gravados, sem busca nova. Pesa a repetição de vocabulário entre "
                "fontes de domínios diferentes e o potencial de vídeo estimado por padrão de texto. Confira cada fala "
                "no link antes de gravar.",
    }


# --------------------------------------------------------------------------
# Produto completo
# --------------------------------------------------------------------------

def bloqueios_da_corrida(corrida: Corrida, paginas: list[Pagina]) -> list[str]:
    saida = []
    for p in paginas:
        if p.estado == "not accessible":
            saida.append(f"{dominio(p.url)}: not accessible ({p.motivo or 'bloqueio'}) em {p.url}")
        elif p.estado == "erro":
            saida.append(f"{dominio(p.url)}: not found, falha ao abrir ({p.motivo}) em {p.url}")
    return sorted(set(saida))


def montar_produto(corrida: Corrida, slug: str) -> dict:
    paginas = abrir_paginas(corrida, slug)
    achados, descartados = extrair_achados(corrida, slug, paginas)
    for i, a in enumerate(achados, 1):
        a["id"] = f"{slug}-{i:03d}"
    bloqueados = bloqueios_da_corrida(corrida, paginas)
    abertas = sum(1 for p in paginas if p.ok)
    motor = "extração por padrões de linguagem em en, pt e es (sem LLM)" if provedor_ativo().nome == "manual" \
        else f"extração por LLM ({provedor_ativo().nome})"
    doc = {
        "meta": {
            "produto": slug,
            "data_captura": HOJE,
            "buscas_usadas": corrida.buscas.usadas(slug),
            "teto_buscas": corrida.teto_total,
            "metodo": (f"{corrida.buscas.usadas(slug)} buscas registradas (tetos P1 a P4: "
                       f"{', '.join(f'{v} {t}' for v, t in corrida.tetos.items())}), {abertas} páginas abertas por "
                       f"urllib, com Chromium quando a página veio vazia; {motor}. Cada citação foi recortada do texto "
                       f"guardado da página e conferida de novo pelo validador. Snippet de busca não virou achado."),
            "bloqueados": bloqueados,
        },
        "achados": [dict(sorted(a.items(), key=lambda kv: _ORDEM_CAMPOS.index(kv[0]))) for a in achados],
        "sintese": sintese(corrida, slug, achados, bloqueados, descartados),
    }
    return doc


_ORDEM_CAMPOS = ["id", "varredura", "pergunta_ou_fala", "pt", "quem", "papel", "grupo", "idioma", "tema",
                 "potencial_video", "angulo_video"]


# --------------------------------------------------------------------------
# Validador
# --------------------------------------------------------------------------

_TRAVESSAO = re.compile(r"[—–]|\s-\s")
_CONTRASTE = re.compile(r"\bnão é\b[^.;]{0,80}\bé\b", re.I)
_VALOR_OU_GRATIS = re.compile(r"R\$|US\$|\bgr[aá]tis\b|\bgratuit\w*|\bfree trial\b|\ba partir de\b", re.I)
_CAMPOS_NOSSOS = ("quem", "papel", "tema", "angulo_video")


def validar(doc: dict, corrida: Corrida, schema: dict | None = None) -> dict:
    """Devolve {violacoes, avisos}. Toda violacao falha a corrida."""
    from jsonschema import Draft202012Validator

    viol: list[dict] = []
    avisos: list[str] = []

    def v(regra: str, caminho: str, detalhe: str = "") -> None:
        viol.append({"regra": regra, "caminho": caminho, "detalhe": detalhe[:160]})

    schema = schema or carregar_schema(corrida.cfg)
    for e in sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda x: list(x.path)):
        v("schema", "/" + "/".join(str(p) for p in e.path), e.message)
    if viol:
        return {"violacoes": viol, "avisos": avisos}

    meta, achados = doc["meta"], doc["achados"]
    if meta["buscas_usadas"] > meta["teto_buscas"]:
        v("teto_de_buscas", "meta.buscas_usadas", f"{meta['buscas_usadas']} > {meta['teto_buscas']}")
    ids = [a["id"] for a in achados]
    if len(ids) != len(set(ids)):
        v("ids_unicos", "achados", "ids repetidos")
    chaves = Counter((canonica(a["pergunta_ou_fala"]["url"]), normalizar(a["pergunta_ou_fala"]["valor"]).lower())
                     for a in achados)
    for k, n in chaves.items():
        if n > 1:
            v("duplicado", k[0], "mesma URL e mesma citação")
    for i, a in enumerate(achados):
        cam = f"achados[{i}]({a['id']})"
        if not a["id"].startswith(meta["produto"] + "-"):
            v("id_fora_do_prefixo", cam)
        f = a["pergunta_ou_fala"]
        if not re.match(r"^https?://\S+$", f["url"]):
            v("url", cam, f["url"])
        pag = corrida.paginas.obter(f["url"])
        if pag is None or not pag.ok:
            v("pagina_nao_guardada", cam, f"{f['url']} sem texto guardado em cache")
        elif not citacao_confere(f["valor"], pag.texto_validacao()):
            v("citacao_ausente_da_pagina", cam, f["valor"])
        if f["data_pagina"] != "not found" and not re.match(r"^\d{4}(-\d{2}-\d{2})?$", f["data_pagina"]):
            v("data_pagina", cam, f["data_pagina"])
        for nome in corrida.proibidos:
            if nome.lower() in json.dumps(a, ensure_ascii=False).lower():
                v("nome_proibido", cam, nome)
        textos = [a[c] for c in _CAMPOS_NOSSOS] + ([a["pt"]["valor"]] if "pt" in a else [])
        for t in textos:
            if _TRAVESSAO.search(t) or _CONTRASTE.search(t):
                v("pontuacao_ou_contraste", cam, t)
            if _VALOR_OU_GRATIS.search(a["angulo_video"]):
                v("valor_ou_gratuidade", cam, a["angulo_video"])
        if a["idioma"] != "pt" and "pt" not in a:
            avisos.append(f"{a['id']}: falta tradução pt")
    for i in doc["sintese"]["top_perguntas"]:
        if i not in ids:
            v("top_perguntas", "sintese.top_perguntas", f"id inexistente {i}")
    for t in doc["sintese"]["lacunas"] + [doc["sintese"]["nota"], meta["metodo"]]:
        if _TRAVESSAO.search(t) or _CONTRASTE.search(t):
            v("pontuacao_ou_contraste", "sintese/meta", t)
    mins = corrida.cfg["minimos"]
    lacunado = bool(doc["sintese"]["lacunas"])
    if len(achados) < mins["achados"]:
        if lacunado:
            avisos.append(f"menos de {mins['achados']} achados ({len(achados)}), com lacuna registrada")
        else:
            v("minimo_de_achados", "achados", f"{len(achados)} achados e nenhuma lacuna registrada")
    if len({a["grupo"] for a in achados}) < mins["grupos"]:
        avisos.append(f"menos de {mins['grupos']} grupos de fonte")
    return {"violacoes": viol, "avisos": avisos}


# --------------------------------------------------------------------------
# Recall contra os achados feitos a mao
# --------------------------------------------------------------------------

def recall(doc: dict, corrida: Corrida, slug: str, referencia: Path | None = None) -> dict:
    ref_dir = referencia or _expandir(corrida.cfg["referencia_achados"])
    arq = ref_dir / f"{slug}.json"
    if not arq.is_file():
        return {"produto": slug, "referencia": None, "motivo": "sem achados à mão para comparar"}
    mao = json.loads(arq.read_text(encoding="utf-8"))["achados"]
    urls_mao = {canonica(a["pergunta_ou_fala"]["url"]) for a in mao}
    urls_run = {canonica(a["pergunta_ou_fala"]["url"]) for a in doc["achados"]}
    candidatas = {u for _v, u in paginas_para_abrir(corrida, slug)}
    perdidas = []
    for u in sorted(urls_mao - urls_run):
        if u not in candidatas:
            motivo = "a busca da corrida não devolveu a URL (teto de buscas ou consulta diferente)"
        else:
            pag = corrida.paginas.obter(u)
            if pag is None or not pag.ok:
                motivo = f"página candidata não abriu ({pag.estado if pag else 'sem cache'}: {pag.motivo if pag else ''})"
            else:
                motivo = "página aberta, mas nenhuma frase passou nos padrões da varredura"
        perdidas.append({"url": u, "motivo": motivo})
    comuns = sorted(urls_mao & urls_run)
    return {
        "produto": slug,
        "referencia": str(arq),
        "achados_a_mao": len(mao),
        "urls_a_mao": len(urls_mao),
        "urls_em_comum": comuns,
        "recall_urls": round(len(comuns) / len(urls_mao), 3) if urls_mao else None,
        "achados_novos_urls": sorted(urls_run - urls_mao),
        "perdidos": perdidas,
    }


# --------------------------------------------------------------------------
# Relatorio
# --------------------------------------------------------------------------

def relatorio(corrida: Corrida, resultados: dict[str, dict]) -> dict:
    por_produto = {}
    for slug, r in resultados.items():
        doc = r["doc"]
        por_produto[slug] = {
            "achados": len(doc["achados"]),
            "por_grupo": dict(Counter(a["grupo"] for a in doc["achados"])),
            "por_varredura": dict(Counter(a["varredura"] for a in doc["achados"])),
            "por_idioma": dict(Counter(a["idioma"] for a in doc["achados"])),
            "buscas_usadas": doc["meta"]["buscas_usadas"],
            "bloqueados": len(doc["meta"]["bloqueados"]),
            "violacoes": r["validacao"]["violacoes"],
            "avisos": len(r["validacao"]["avisos"]),
        }
    return {
        "data": HOJE,
        "produtos": por_produto,
        "custo": {"chamadas_llm": corrida.llm_chamadas,
                  "buscas": sum(p["buscas_usadas"] for p in por_produto.values()),
                  "paginas": dict(corrida.paginas.stats)},
        "total_violacoes": sum(len(p["violacoes"]) for p in por_produto.values()),
    }


def gravar_saida(corrida: Corrida, slug: str, doc: dict) -> Path:
    corrida.saida.mkdir(parents=True, exist_ok=True)
    gravar_json(corrida.arquivo(slug), doc, indent=2)
    return corrida.arquivo(slug)
