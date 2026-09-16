"""
Runner da varredura de lojas no Google Maps (projeto C&A scrape).

    uv run python raspar_lojas_google.py                           # vertical moda (verticais/moda.json)
    uv run python raspar_lojas_google.py --vertical supermercados
    uv run python raspar_lojas_google.py --marcas Renner --max-avaliacoes 50
    uv run python raspar_lojas_google.py --cidade "Anapolis, GO" --saida anapolis

Abre uma janela do Chromium: em modo headless o Google nao entrega o
grafico de horarios de pico.
"""

import argparse
import json
import time
from pathlib import Path

from scraper_lab.lojas_google import AcessoLimitado, exportar, varrer

VERTICAIS = Path(__file__).resolve().parent / "verticais"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", default="moda", help="arquivo em verticais/<nome>.json")
    ap.add_argument("--cidade", help="sobrescreve a cidade da vertical")
    ap.add_argument("--marcas", help="nomes separados por virgula (padrao: todas da vertical)")
    ap.add_argument("--max-avaliacoes", type=int, default=300,
                    help="avaliacoes por loja, das mais recentes (0 desliga)")
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--headless", action="store_true", help="mais rapido, mas sem horarios de pico")
    ap.add_argument("--incluir-vizinhas", action="store_true",
                    help="mantem lojas de outros municipios que aparecerem na busca")
    ap.add_argument("--saida", help="nome base dos arquivos (padrao: o da vertical)")
    args = ap.parse_args()

    cfg = json.loads((VERTICAIS / f"{args.vertical}.json").read_text(encoding="utf-8"))
    cidade = args.cidade or cfg["cidade"]
    saida = args.saida or cfg["saida"]
    filtro = {m.strip().lower() for m in args.marcas.split(",")} if args.marcas else None
    escolhidas = {m["nome"]: m for m in cfg["marcas"] if not filtro or m["nome"].lower() in filtro}

    inicio = time.time()
    lojas = []
    try:
        varrer(escolhidas, cidade, args.max_avaliacoes, headless=args.headless,
               delay=args.delay, so_cidade=not args.incluir_vizinhas, lojas=lojas)
    except AcessoLimitado as e:
        print(f"\nPARADA: {e}. Nada foi forcado; rode de novo mais tarde.")
        if not lojas:
            raise SystemExit(2)
        saida += "_parcial"
    arquivos = exportar(lojas, saida)

    print(f"\n{'='*60}")
    for marca in escolhidas:
        da_marca = [l for l in lojas if l.marca == marca]
        print(f"  {marca:<10} lojas={len(da_marca):>3}  com pico={sum(1 for l in da_marca if l.horarios_pico):>3}"
              f"  avaliacoes={sum(len(l.avaliacoes) for l in da_marca):>5}  erros={sum(1 for l in da_marca if l.erro)}")
    print(f"  tempo ....... {time.time()-inicio:.0f}s")
    print(f"  planilha .... {arquivos.get('xlsx', arquivos['json'])}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
