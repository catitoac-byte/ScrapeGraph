"""
Coleta das empresas do BVM (Alemanha): portal de anbieter + firmenmitglieder.

    uv run python -u raspar_bvm.py
"""

import time

from scraper_lab.bvm import coletar, exportar

if __name__ == "__main__":
    inicio = time.time()
    print("[1/2] Coletando")
    empresas = coletar(delay=1.6)

    print("\n[2/2] Exportando")
    cj, cc = exportar(empresas)

    portal = [e for e in empresas if e.origem == "portal_anbieter"]
    so_lista = [e for e in empresas if e.origem == "lista_firmenmitglieder"]
    print("\n" + "=" * 66)
    print(f"  empresas ......... {len(empresas)}")
    print(f"   do portal ....... {len(portal)}")
    print(f"   so da lista ..... {len(so_lista)} (nome, sem contato publicado)")
    print(f"  com email ........ {sum(1 for e in empresas if e.email)}")
    print(f"  com site ......... {sum(1 for e in empresas if e.site)}")
    print(f"  com telefone ..... {sum(1 for e in empresas if e.telefone)}")
    print(f"  com endereco ..... {sum(1 for e in empresas if e.endereco)}")
    print(f"  membros do BVM ... {sum(1 for e in empresas if e.membro_bvm == 'sim')}")
    print(f"  cidades .......... {len({e.cidade for e in empresas if e.cidade})}")
    print(f"  paises ........... {sorted({e.pais for e in portal})}")
    print(f"  erros ............ {sum(1 for e in empresas if e.erro)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 66)
