"""Varredura do Sourcebook da Quirk's. Padrao: Estados Unidos."""

import sys
import time

from scraper_lab.quirks import coletar, exportar, listar_por_pais

if __name__ == "__main__":
    pais = sys.argv[1] if len(sys.argv) > 1 else "united-states"
    inicio = time.time()
    print(f"[1/3] Listando ({pais})")
    urls = listar_por_pais(pais)
    print(f"      {len(urls)} perfis\n")

    print("[2/3] Coletando")
    empresas = coletar(urls, delay=1.2)

    print("\n[3/3] Exportando")
    cj, cc = exportar(empresas, f"quirks_{pais.replace('-', '_')}")
    ok = [e for e in empresas if e.nome]
    print(f"\n{'='*58}")
    print(f"  empresas ......... {len(ok)}")
    print(f"  com site ......... {sum(1 for e in ok if e.site)}")
    print(f"  com cidade ....... {sum(1 for e in ok if e.cidade)}")
    print(f"  estados .......... {len({e.estado for e in ok if e.estado})}")
    print(f"  erros ............ {sum(1 for e in empresas if e.erro)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV .............. {cc}")
    print(f"{'='*58}")
