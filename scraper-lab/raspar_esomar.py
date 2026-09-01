"""
Runner do diretorio Esomar.

    uv run python raspar_esomar.py --url "<url de busca>" [--paginas N] [--saida nome]
    uv run python raspar_esomar.py --url "<url>" --so-listar
"""

import argparse
import time

from scraper_lab.esomar import exportar, listar_urls, raspar_perfis


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="URL de busca do diretorio")
    ap.add_argument("--paginas", type=int, default=30, help="teto de paginas a percorrer")
    ap.add_argument("--saida", default="esomar", help="nome base dos arquivos de saida")
    ap.add_argument("--delay", type=float, default=2.0, help="pausa entre requisicoes (s)")
    ap.add_argument("--so-listar", action="store_true", help="apenas listar URLs, sem abrir perfis")
    args = ap.parse_args()

    inicio = time.time()

    print("[1/3] Listando empresas")
    urls = listar_urls(args.url, max_paginas=args.paginas, delay=args.delay)
    print(f"      {len(urls)} empresas unicas")

    if args.so_listar:
        for u in urls:
            print("   ", u)
        return

    print(f"\n[2/3] Abrindo {len(urls)} perfis")
    empresas = raspar_perfis(urls, delay=args.delay)

    print("\n[3/3] Exportando")
    cj, cc = exportar(empresas, args.saida)

    com_email = sum(1 for e in empresas if e.email)
    com_site = sum(1 for e in empresas if e.site)
    contatos = sum(len(e.contatos) for e in empresas)
    erros = sum(1 for e in empresas if e.erro)

    print(f"\n{'='*58}")
    print(f"  empresas ...... {len(empresas)}")
    print(f"  com email ..... {com_email}")
    print(f"  com site ...... {com_site}")
    print(f"  contatos ...... {contatos}")
    print(f"  erros ......... {erros}")
    print(f"  tempo ......... {time.time()-inicio:.0f}s")
    print(f"  JSON .......... {cj}")
    print(f"  CSV ........... {cc}")
    print(f"{'='*58}")


if __name__ == "__main__":
    main()
