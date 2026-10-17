"""
Runner da vertical sinteticos (dados e personas sinteticas em pesquisa).

    uv run python raspar_sinteticos.py tudo                      # V4, V2, V3, V1, V5 e conferencias
    uv run python raspar_sinteticos.py tudo --piloto 10 --teto 8 # corrida pequena
    uv run python raspar_sinteticos.py v4 | v2 | v3 | v1 | v5    # uma varredura
    uv run python raspar_sinteticos.py validar | recall | relatorio

Buscas (o teto de cada varredura vale para todas as formas):

    uv run python raspar_sinteticos.py buscas pendentes --varredura V4
    uv run python raspar_sinteticos.py buscas registrar --arquivo resultados.json
    uv run python raspar_sinteticos.py buscas api --varredura V4   # BUSCA_PROVIDER=brave

resultados.json e uma lista de
    {"varredura": "V4", "consulta": "...", "idioma": "en",
     "resultados": [{"url": "...", "titulo": "..."}]}

Saida em dados/saida/sinteticos/ (ou .../sinteticos/piloto/ com --piloto).
Cache de paginas, buscas e fichas em dados/cache/sinteticos/.
A corrida termina com codigo 1 se o validador achar violacao ou o recall falhar.
"""

import argparse
import json
import sys
from pathlib import Path

from scraper_lab.sinteticos import (
    VARRER,
    VARREDURAS,
    Corrida,
    TetoDeBuscas,
    buscar_por_api,
    carregar_config,
    escrever_resumo,
    recall,
    relatorio,
    validar,
)


def conferir(corrida: Corrida) -> int:
    print("\n[validador] quotes contra as páginas guardadas")
    val = validar(corrida)
    print(f"            {val['total_violacoes']} violações; contagem {val['contagem'].get('literal', 0)} literais, "
          f"{val['contagem'].get('inferido', 0)} inferidos, {val['contagem'].get('not found', 0)} not found, "
          f"{val['contagem'].get('not accessible', 0)} not accessible")
    for v in val["violacoes"][:15]:
        print(f"            ! {v['regra']}: {v['caminho']}")
    print("[recall]    base inicial contra empresas.json")
    rec = recall(corrida)
    print(f"            {rec['presentes']} presentes, {rec['justificadas']} justificadas, "
          f"{len(rec['sem_motivo'])} sem motivo")
    rel = relatorio(corrida, val, rec)
    resumo = escrever_resumo(corrida, rel)
    print(f"[relatório] {corrida.saida / 'relatorio.json'}")
    print(f"[resumo]    {resumo}")
    return 0 if val["total_violacoes"] == 0 and rec["passou"] else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["tudo", "v1", "v2", "v3", "v4", "v5", "validar", "recall",
                                        "relatorio", "buscas"])
    ap.add_argument("acao", nargs="?", choices=["pendentes", "registrar", "api"])
    ap.add_argument("--vertical", default="sinteticos")
    ap.add_argument("--piloto", type=int, help="limita a N empresas e grava em .../piloto/")
    ap.add_argument("--teto", type=int, help="teto de buscas por varredura nesta corrida")
    ap.add_argument("--varredura", choices=["V1", "V2", "V3", "V4"])
    ap.add_argument("--arquivo", type=Path, help="JSON com buscas executadas a registrar")
    args = ap.parse_args()

    cfg = carregar_config(args.vertical)
    corrida = Corrida(cfg, piloto=args.piloto, teto=args.teto)
    corrida.saida.mkdir(parents=True, exist_ok=True)

    if args.comando == "buscas":
        if args.acao == "pendentes":
            for v in ([args.varredura] if args.varredura else ["V4", "V2", "V3", "V1"]):
                pend = corrida.buscas.pendentes(v, cfg, corrida.teto(v))
                print(f"{v}: {corrida.buscas.usadas(v)} de {corrida.teto(v)} usadas; {len(pend)} pendentes")
                for idioma, q in pend:
                    print(f"   [{idioma}] {q}")
        elif args.acao == "registrar":
            itens = json.loads(args.arquivo.read_text(encoding="utf-8"))
            for it in itens:
                try:
                    corrida.buscas.registrar(it["varredura"], it["consulta"], it.get("idioma", ""),
                                             it.get("resultados", []), corrida.teto(it["varredura"]),
                                             it.get("provedor", "manual"))
                    print(f"  ok {it['varredura']} {it['consulta']} ({len(it.get('resultados', []))} resultados)")
                except TetoDeBuscas as e:
                    print(f"  !! {e}")
        elif args.acao == "api":
            print(f"{buscar_por_api(corrida, args.varredura or 'V4')} buscas executadas")
        else:
            ap.error("buscas exige pendentes, registrar ou api")
        return

    if args.comando in ("validar", "recall", "relatorio"):
        sys.exit(conferir(corrida))

    alvo = VARREDURAS if args.comando == "tudo" else (args.comando.upper(),)
    for v in alvo:
        print(f"\n=== {v} ===")
        saida = VARRER[v](corrida)
        print(f"    {saida['meta'].get('total')} registros -> {corrida.arquivo(v)}")
    sys.exit(conferir(corrida))


if __name__ == "__main__":
    main()
