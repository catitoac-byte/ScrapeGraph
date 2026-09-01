"""
Coleta dos membros da expertise Etudes do Syntec Conseil (Franca).

    uv run python -u raspar_syntec.py
"""

import time

from scraper_lab.syntec import coletar, exportar

if __name__ == "__main__":
    inicio = time.time()
    print("[1/2] Coletando")
    empresas = coletar(delay=1.6)

    print("\n[2/2] Exportando")
    cj, cc = exportar(empresas)

    fora = [e for e in empresas if e.tambem_em_nos_membros == "nao"]
    print("\n" + "=" * 66)
    print(f"  empresas ......... {len(empresas)}")
    print(f"  com site ......... {sum(1 for e in empresas if e.site)}")
    print(f"  com email ........ {sum(1 for e in empresas if e.email)}  "
          f"(o Syntec nao publica e-mail)")
    print(f"  so na expertise .. {len(fora)} (ausentes do quadro geral)")
    for e in fora:
        print(f"     - {e.nome}")
    print(f"  erros ............ {sum(1 for e in empresas if e.erro)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 66)
