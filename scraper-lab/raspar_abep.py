"""
Coleta do diretorio de filiados da ABEP.

    uv run python -u raspar_abep.py
"""

import time

from scraper_lab.abep import coletar, exportar, listar_filiados

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Listando filiados")
    urls = listar_filiados()
    print(f"      {len(urls)} empresas\n")

    print("[2/3] Coletando perfis")
    filiados = coletar(urls, delay=1.0)

    print("\n[3/3] Exportando")
    cj, cc = exportar(filiados)

    ok = [f for f in filiados if f.nome]
    print("\n" + "=" * 62)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com email ........ {sum(1 for f in ok if f.email)}")
    print(f"  com site ......... {sum(1 for f in ok if f.site)}")
    print(f"  com telefone ..... {sum(1 for f in ok if f.telefone)}")
    print(f"  com tipo ......... {sum(1 for f in ok if f.tipo_empresa)}")
    print(f"  UFs .............. {len({f.uf for f in ok if f.uf})}")
    print(f"  erros ............ {sum(1 for f in filiados if f.erro)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
