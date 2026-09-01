"""Coleta do Research Buyers Guide da MRS."""

import time

from scraper_lab.mrs import coletar, exportar, listar_empresas

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Listando (rolagem infinita)")
    urls = listar_empresas()
    print(f"      {len(urls)} perfis\n")

    print("[2/3] Coletando")
    empresas = coletar(urls, delay=1.5)

    print("\n[3/3] Exportando")
    cj, cc = exportar(empresas)
    ok = [e for e in empresas if e.nome]
    print(f"\n{'='*58}")
    print(f"  empresas ......... {len(ok)}")
    print(f"  com email ........ {sum(1 for e in ok if e.email)}")
    print(f"  com site ......... {sum(1 for e in ok if e.site)}")
    print(f"  com telefone ..... {sum(1 for e in ok if e.telefone)}")
    print(f"  paises ........... {len({e.pais for e in ok if e.pais})}")
    print(f"  erros ............ {sum(1 for e in empresas if e.erro)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print(f"{'='*58}")
