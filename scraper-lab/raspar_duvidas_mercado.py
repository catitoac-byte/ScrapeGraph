"""
Runner da vertical duvidas_mercado (perguntas, dores, objecoes e mitos por produto).

    uv run python raspar_duvidas_mercado.py --produto dash-lab --teto-buscas 10
    uv run python raspar_duvidas_mercado.py --todos
    uv run python raspar_duvidas_mercado.py --produto dash-lab --dry-run     # so mostra o plano
    uv run python raspar_duvidas_mercado.py --produto dash-lab --pendentes   # consultas ainda sem busca
    uv run python raspar_duvidas_mercado.py --produto dash-lab --registrar buscas.json

buscas.json e uma lista de
    {"produto": "dash-lab", "varredura": "P1", "consulta": "...", "idioma": "en",
     "resultados": [{"url": "...", "titulo": "..."}]}

BUSCA_PROVIDER=brave com BRAVE_API_KEY no ambiente executa as buscas pendentes sozinho.
Saida: <saida>/<slug>.json no schema achados.schema.json, mais <saida>/_relatorio/.
Cache de paginas e buscas em dados/cache/duvidas_mercado/ (retomada automatica).
A corrida termina com codigo 1 se o validador achar qualquer violacao.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from scraper_lab.duvidas_mercado import (
    VARREDURAS,
    Corrida,
    TetoDeBuscas,
    buscar_por_api,
    carregar_config,
    carregar_schema,
    consultas_da_varredura,
    gravar_saida,
    montar_produto,
    recall,
    relatorio,
    validar,
)
from scraper_lab.pipeline import gravar_json


def plano(corrida: Corrida, slug: str) -> None:
    print(f"\n[{slug}] teto {corrida.teto_total} buscas; por varredura {corrida.tetos}")
    for v in VARREDURAS:
        feitas = corrida.buscas.usadas(slug, v)
        pend = corrida.buscas.pendentes(corrida.cfg, slug, v, corrida.tetos[v], corrida.teto_total)
        total = len(consultas_da_varredura(corrida.cfg, slug, v))
        print(f"  {v}: {feitas}/{corrida.tetos[v]} feitas; {len(pend)} pendentes dentro do teto ({total} candidatas)")
        for idioma, q in pend:
            print(f"      [{idioma}] {q}")


def registrar(corrida: Corrida, arquivo: Path) -> None:
    for it in json.loads(arquivo.read_text(encoding="utf-8")):
        try:
            corrida.buscas.registrar(it["produto"], it["varredura"], it["consulta"], it.get("idioma", ""),
                                     it.get("resultados", []), corrida.tetos[it["varredura"]], corrida.teto_total,
                                     it.get("provedor", "manual"))
            print(f"  ok {it['produto']} {it['varredura']} {it['consulta']} ({len(it.get('resultados', []))} resultados)")
        except TetoDeBuscas as e:
            print(f"  !! {e}")


def rodar(corrida: Corrida, slugs: list[str], referencia: Path | None) -> int:
    schema = carregar_schema(corrida.cfg)
    resultados = {}
    for slug in slugs:
        print(f"\n=== {slug} ===")
        if os.getenv("BUSCA_PROVIDER", "manual").lower() == "brave" and os.getenv("BRAVE_API_KEY"):
            print(f"    {buscar_por_api(corrida, slug)} buscas executadas na API")
        doc = montar_produto(corrida, slug)
        val = validar(doc, corrida, schema)
        arq = gravar_saida(corrida, slug, doc)
        rec = recall(doc, corrida, slug, referencia)
        gravar_json(corrida.saida / "_relatorio" / f"recall-{slug}.json", rec, indent=2)
        resultados[slug] = {"doc": doc, "validacao": val, "recall": rec}
        print(f"    {len(doc['achados'])} achados, {doc['meta']['buscas_usadas']} buscas, "
              f"{len(doc['meta']['bloqueados'])} bloqueios -> {arq}")
        print(f"    validador: {len(val['violacoes'])} violações, {len(val['avisos'])} avisos")
        for x in val["violacoes"][:15]:
            print(f"      ! {x['regra']}: {x['caminho']} {x['detalhe'][:80]}")
        if rec.get("referencia"):
            print(f"    recall contra {Path(rec['referencia']).name}: {len(rec['urls_em_comum'])} de {rec['urls_a_mao']} URLs, "
                  f"{len(rec['achados_novos_urls'])} URLs novas, {len(rec['perdidos'])} perdidas")
        else:
            print(f"    recall: {rec['motivo']}")
    rel = relatorio(corrida, resultados)
    rel["recall"] = {s: r["recall"] for s, r in resultados.items()}
    gravar_json(corrida.saida / "_relatorio" / "resumo.json", rel, indent=2)
    print(f"\n[relatório] {corrida.saida / '_relatorio' / 'resumo.json'}")
    print(f"[custo]     {rel['custo']}")
    return 1 if rel["total_violacoes"] else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--produto", action="append", help="slug do produto; pode repetir")
    ap.add_argument("--todos", action="store_true", help="roda os 15 produtos em sequência")
    ap.add_argument("--teto-buscas", type=int, help="teto de buscas por produto (máximo 30)")
    ap.add_argument("--saida", type=Path, help="pasta de saída (padrão dados/saida/duvidas_mercado)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o plano de buscas e não abre nenhuma página")
    ap.add_argument("--pendentes", action="store_true", help="lista as consultas ainda sem busca registrada")
    ap.add_argument("--registrar", type=Path, help="JSON com buscas executadas a registrar")
    ap.add_argument("--referencia", type=Path, help="pasta com achados à mão para o recall")
    ap.add_argument("--vertical", default="duvidas_mercado")
    args = ap.parse_args()

    cfg = carregar_config(args.vertical)
    if args.todos:
        slugs = list(cfg["produtos"])
    elif args.produto:
        desconhecidos = [s for s in args.produto if s not in cfg["produtos"]]
        if desconhecidos:
            ap.error(f"produto desconhecido: {', '.join(desconhecidos)}")
        slugs = args.produto
    else:
        ap.error("informe --produto <slug> ou --todos")

    corrida = Corrida(cfg, saida=args.saida, teto_buscas=args.teto_buscas, dry_run=args.dry_run)
    if args.registrar:
        registrar(corrida, args.registrar)
    if args.dry_run or args.pendentes:
        for s in slugs:
            plano(corrida, s)
        return
    sys.exit(rodar(corrida, slugs, args.referencia))


if __name__ == "__main__":
    main()
