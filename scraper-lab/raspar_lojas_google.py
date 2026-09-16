"""
Runner da varredura de lojas no Google Maps (projeto C&A scrape).

    uv run python raspar_lojas_google.py                       # C&A, Renner e Riachuelo em Goiania
    uv run python raspar_lojas_google.py --marcas cea --max-avaliacoes 50
    uv run python raspar_lojas_google.py --cidade "Anapolis, GO" --saida anapolis

Abre uma janela do Chromium: em modo headless o Google nao entrega o
grafico de horarios de pico.
"""

import argparse
import time

from scraper_lab.lojas_google import exportar, varrer

MARCAS = {
    "cea": {
        "nome": "C&A",
        "padrao": r"^c\s*&\s*a\b|^c&a\b|\bc&a modas\b",
        "consultas": ["C&A {cidade}", "C&A Modas {cidade}", "loja C&A shopping {cidade}"],
    },
    "renner": {
        "nome": "Renner",
        "padrao": r"\brenner\b",
        "consultas": ["Lojas Renner {cidade}", "Renner {cidade}", "Renner shopping {cidade}"],
    },
    "riachuelo": {
        "nome": "Riachuelo",
        "padrao": r"\briachuelo\b",
        "consultas": ["Riachuelo {cidade}", "Lojas Riachuelo {cidade}", "Riachuelo shopping {cidade}"],
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cidade", default="Goiânia, GO")
    ap.add_argument("--marcas", default="cea,renner,riachuelo")
    ap.add_argument("--max-avaliacoes", type=int, default=300,
                    help="avaliacoes por loja, das mais recentes (0 desliga)")
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--headless", action="store_true", help="mais rapido, mas sem horarios de pico")
    ap.add_argument("--incluir-vizinhas", action="store_true",
                    help="mantem lojas de outros municipios que aparecerem na busca")
    ap.add_argument("--saida", default="lojas_goiania")
    args = ap.parse_args()

    escolhidas = {MARCAS[m]["nome"]: MARCAS[m] for m in args.marcas.split(",")}
    inicio = time.time()
    lojas = varrer(escolhidas, args.cidade, args.max_avaliacoes,
                   headless=args.headless, delay=args.delay,
                   so_cidade=not args.incluir_vizinhas)
    arquivos = exportar(lojas, args.saida)

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
