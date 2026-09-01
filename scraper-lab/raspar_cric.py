"""
Coleta do diretorio de membros do CRIC (Canada).

    uv run python -u raspar_cric.py
"""

import time

from scraper_lab.cric import (
    buscar_rvs,
    cruzar_com_rvs,
    exportar,
    listar_membros,
)

if __name__ == "__main__":
    inicio = time.time()

    print("[1/3] Lendo /member-directory/")
    membros = listar_membros()
    print(f"      {len(membros)} empresas apos deduplicar\n")

    print("[2/3] Cruzando com o Research Verification Service")
    try:
        time.sleep(1.6)
        membros = cruzar_com_rvs(membros, buscar_rvs())
    except Exception as exc:
        # Fonte complementar indisponivel nao invalida o diretorio principal.
        print(f"      RVS indisponivel ({type(exc).__name__}); "
              f"seguindo so com o diretorio")

    print("\n[3/3] Exportando")
    cj, cc = exportar(membros)

    do_diretorio = [m for m in membros if m.fonte.startswith("member-directory")]
    print("\n" + "=" * 64)
    print(f"  empresas ......... {len(membros)}")
    print(f"  no diretorio ..... {len(do_diretorio)}")
    print(f"  so no RVS ........ {sum(1 for m in membros if m.fonte == 'rvs')}")
    print(f"  com site ......... {sum(1 for m in membros if m.site)}")
    print(f"  com email ........ {sum(1 for m in membros if m.email)}")
    print(f"  credenciadas ..... {sum(1 for m in membros if m.credenciada)}")
    print(f"  erros ............ {sum(1 for m in membros if m.erro)}")
    print(f"  tempo ............ {time.time() - inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 64)
