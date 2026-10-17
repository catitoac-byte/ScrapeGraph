"""
Monta o comparador visual da vertical sinteticos (mapa, 2x2 e rota de metodos).

    uv run python gerar_comparador_sinteticos.py            # usa a corrida completa, se houver
    uv run python gerar_comparador_sinteticos.py --piloto   # usa dados/saida/sinteticos/piloto/

Fontes, nesta ordem de prioridade por empresa:
  1. empresas.json da coleta (campos com quote conferida pelo validador)
  2. vendors_all.json da base inicial (agentes de busca, 17 out 2026)
  3. empresa_propria de verticais/sinteticos.json (Cassi.ai, quotes conferidas)

O visual reaproveita o deck da Voxpopme (~/Projetos/voxpopme-betsy/deck-web):
mapa de forcas com envoltorias do slide 02, 2x2 com comparacao automatica do
slide 04 e rota com pacotes do slide 07.

Saida em sites/sinteticos/index.html (fora do git: carrega dados coletados) e
uma copia em ~/Projetos/dados-sinteticos-abep/site/comparador-sinteticos.html.
"""

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from scraper_lab.sinteticos import _expandir, _nome_base, carregar_config  # noqa: E402
from scraper_lab.sinteticos_paginas import registravel  # noqa: E402

LAB = Path(__file__).resolve().parent
MODELO = LAB / "vitrine-web" / "sinteticos" / "comparador.html"
SAIDA = LAB / "sites" / "sinteticos" / "index.html"
COPIA = Path.home() / "Projetos" / "dados-sinteticos-abep" / "site" / "comparador-sinteticos.html"

FORA = ("no_public", "stance", "exploring", "research", "third_party_evidence")
GRUPO = {"vendors_startups": "Startup", "vendors_incumbents_regional": "Incumbente regional",
         "vendors_intl": "Internacional"}


def nivel_da_base(s: dict) -> str:
    v = (s.get("validation_status") or "").lower()
    if v.startswith("third"):
        return "third_party"
    if v.startswith("academic"):
        return "peer_reviewed"
    if v.startswith("self"):
        return "self_reported"
    return "none"


def regiao(cfg: dict, hq: str) -> str:
    for chave, (_, reg) in sorted(cfg["locais"].items(), key=lambda x: -len(x[0])):
        if re.search(rf"(?<![\w]){re.escape(chave)}(?![\w])", hq or ""):
            return reg
    if re.search(r"South Korea|Korea", hq or ""):
        return "Coreia"
    return "não informada"


def limpo(t, n=320) -> str:
    if isinstance(t, str) and t.strip().startswith("{"):
        try:
            t = json.loads(t)
        except ValueError:
            t = re.sub(r'^\{"(value|list)":\s*', "", t)
    if isinstance(t, dict) and "list" in t:
        t = ", ".join(t["list"]) if t["list"] else ""
    if isinstance(t, dict):
        t = t.get("value") or t.get("text") or t.get("valor") or ""
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    if re.match(r"(?i)none published|not found|not public$", t):
        return ""
    if t.lower() in ("", "none", "not found", "n/a"):
        return ""
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def da_coleta(reg: dict) -> dict:
    """Resumo do que a coleta automatica conferiu na pagina."""
    def q(c):
        return {"t": c.get("tipo"), "v": c.get("valor"), "q": c.get("quote", ""), "u": c.get("url", "")} if isinstance(c, dict) else None
    return {
        "base": q(reg.get("grounding")),
        "val": q(reg.get("validation_claim")),
        "nivel": ((reg.get("validation_claim") or {}).get("level") or {}).get("valor"),
        "preco": q(reg.get("pricing")),
        "head": q(reg.get("headline_verbatim")),
        "ofertas": [o.get("valor") for o in reg.get("offer_type") or [] if o.get("tipo") == "inferido"],
        "urls": reg.get("source_urls", [])[:8],
        "data": reg.get("date_captured"),
    }


def casos_por_empresa(cfg: dict) -> dict[str, list[dict]]:
    """Cases da base (cases_media.json) ligados ao fornecedor pelo nome."""
    cases = json.loads(_expandir(cfg["sementes"]["cases"]).read_text(encoding="utf-8"))["cases"]
    saida: dict[str, list[dict]] = {}
    for c in cases:
        forn = _nome_base(c.get("vendor") or "").lower()
        if forn:
            saida.setdefault(forn, []).append({
                "t": c.get("title", ""), "marca": c.get("company", ""), "ano": c.get("year", ""),
                "obj": c.get("objective", ""), "res": c.get("result_verbatim", ""),
                "ev": c.get("evidence_type", ""), "u": c.get("url", ""), "data": c.get("date", "")})
    return saida


def montar(cfg: dict, coleta: dict) -> dict:
    base = json.loads(_expandir(cfg["sementes"]["empresas"]).read_text(encoding="utf-8"))
    casos = casos_por_empresa(cfg)
    grupos: dict[str, list[dict]] = {}
    for s in base:
        if not str(s.get("url", "")).startswith("http") or s.get("status", "").startswith(FORA):
            continue
        grupos.setdefault(_nome_base(s["name"]).lower(), []).append(s)

    por_semente = {n: r for r in coleta.get("companies", []) for n in r.get("sementes", [])}
    empresas = []
    for chave, ss in grupos.items():
        s = ss[0]
        reg = next((por_semente[x["name"]] for x in ss if x["name"] in por_semente), None)
        dom = reg["dominio"] if reg else registravel(s["url"])
        ofertas = sorted({o for x in ss for o in x.get("offer") or []})
        empresas.append({
            "id": re.sub(r"[^a-z0-9]+", "-", chave).strip("-"),
            "n": _nome_base(s["name"]),
            "produto": limpo(s.get("product"), 80),
            "url": s["url"], "dom": dom,
            "grupo": GRUPO.get(s.get("source_file"), "Outro"),
            "reg": regiao(cfg, s.get("hq", "")), "hq": limpo(s.get("hq"), 60) or "not found",
            "of": ofertas, "base": s.get("grounding") or "not_disclosed",
            "base_q": limpo(s.get("grounding_quote")),
            "val": nivel_da_base(s), "val_q": limpo(s.get("validation")),
            "val_b": limpo(s.get("validation_basis"), 200) or ("a base inicial registrou: nenhum número publicado"
                                                               if re.match(r"(?i)none published", str(s.get("validation") or "")) else ""),
            "preco": limpo(s.get("pricing"), 160) or "not found",
            "fund": limpo(s.get("funding"), 160) or "not found",
            "cli": limpo(s.get("customers"), 200) or "not found",
            "head": limpo(s.get("headline"), 200),
            "video": s.get("video") if str(s.get("video", "")).startswith("http") else "",
            "ressalva": limpo(s.get("caution"), 260),
            "fundada": limpo(s.get("founded"), 30) or "not found",
            "fontes": [x["url"] for x in ss],
            "site": f"https://{dom}/" if "." in dom else s["url"],
            "casos": casos.get(chave, []),
            "coleta": da_coleta(reg) if reg else None,
            "cassi": False,
        })

    p = cfg["empresa_propria"]
    empresas.insert(0, {
        "id": "cassi-ai", "n": p["name"], "produto": "Synthetic Lab e Synthetic Vertical Simulator",
        "url": p["url"], "dom": p["dominio"], "grupo": "Cassi.ai", "reg": "não informada", "hq": "not found",
        "of": [o["valor"] for o in p["offer_type"]], "base": p["grounding"]["valor"],
        "base_q": p["grounding"]["quote"], "val": "client_data", "val_q": p["declaracao"]["texto"],
        "val_b": p["declaracao"]["fonte"], "preco": "sob consulta (a página convida a pedir acesso)",
        "fund": "not found", "cli": "not found", "site": p["url"], "casos": [],
        "produtos": p["produtos"],
        "head": p["headline_oferta"]["quote"], "video": "", "ressalva": p["limites"]["quote"],
        "fundada": "not found", "fontes": [x["url"] for x in p["produtos"]],
        "como": p["como_e_construida"]["quote"], "vies": p["controle_de_vies"]["quote"],
        "priv": p["privacidade"]["quote"], "dados": p["dados_que_alimentam"]["quote"],
        "of_q": [{"v": o["valor"], "q": o["quote"], "u": o["url"]} for o in p["offer_type"]],
        "coleta": {"data": "2026-10-17", "urls": sorted({o["url"] for o in p["offer_type"]})},
        "cassi": True,
    })

    te = cfg["tipo_empresa"]
    for e in empresas:
        e["tipo"] = te["rotulos"][te["mapa"].get(e["id"], "startup")]
    cont = {
        "total": len(empresas),
        "nivel": dict(Counter(e["val"] for e in empresas)),
        "base": dict(Counter(e["base"] for e in empresas)),
        "oferta": dict(Counter(o for e in empresas for o in e["of"])),
        "regiao": dict(Counter(e["reg"] for e in empresas)),
        "verificadas": sum(1 for e in empresas if e["coleta"]),
    }
    return {"meta": {"data": "2026-10-17", "fonte": "vendors_all.json (base inicial) + coleta scraper-lab + páginas da Cassi.ai",
                     "piloto": bool(coleta.get("meta", {}).get("piloto"))},
            "contagem": cont, "empresas": empresas}


def _textos(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _textos(v)
    elif isinstance(x, list):
        for v in x:
            yield from _textos(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--piloto", action="store_true")
    ap.add_argument("--sem-copia", action="store_true")
    args = ap.parse_args()
    cfg = carregar_config()
    pasta = cfg["_saida"] / ("piloto" if args.piloto else "")
    arq = pasta / "empresas.json"
    coleta = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    dados = montar(cfg, coleta)
    trad = json.loads((LAB / "verticais" / "sinteticos_traducoes.json").read_text(encoding="utf-8"))["textos"]
    usados = {v for e in dados["empresas"] for v in _textos(e)}
    dados["trad"] = {k: v for k, v in trad.items() if k in usados}
    html = MODELO.read_text(encoding="utf-8").replace(
        "/*__DADOS__*/{}", json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(html, encoding="utf-8")
    shutil.copy(MODELO.parent / "open-source.html", SAIDA.parent / "open-source.html")
    if not args.sem_copia:
        shutil.copy(SAIDA, COPIA)
        os_html = (SAIDA.parent / "open-source.html").read_text(encoding="utf-8")
        (COPIA.parent / "open-source.html").write_text(
            os_html.replace('href="index.html"', f'href="{COPIA.name}"'), encoding="utf-8")
        if (SAIDA.parent / "img").exists():
            shutil.copytree(SAIDA.parent / "img", COPIA.parent / "img", dirs_exist_ok=True)
    c = dados["contagem"]
    print(f"{c['total']} empresas ({c['verificadas']} conferidas pela coleta), níveis {c['nivel']}")
    print(SAIDA)
    if not args.sem_copia:
        print(COPIA)


if __name__ == "__main__":
    main()
