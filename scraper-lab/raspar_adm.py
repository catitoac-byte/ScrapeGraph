"""
Coleta dos institutos filiados ao ADM (Alemanha).

    uv run python -u raspar_adm.py
"""

import time

from scraper_lab.adm import DELAY_PADRAO, coletar, exportar, listar_institutos, util

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Listando institutos")
    alvos = listar_institutos()
    print(f"      {len(alvos)} fichas a visitar\n")

    print("[2/3] Coletando fichas")
    institutos = coletar(alvos, delay=DELAY_PADRAO)

    print("\n[3/3] Exportando")
    validos = [i for i in institutos if util(i)]
    cj, cc = exportar(validos)

    descartados = [i for i in institutos if not util(i)]
    print("\n" + "=" * 66)
    print(f"  institutos ....... {len(validos)}")
    print(f"  com email ........ {sum(1 for i in validos if i.email)}")
    print(f"  com site ......... {sum(1 for i in validos if i.site)}")
    print(f"  com telefone ..... {sum(1 for i in validos if i.telefone)}")
    print(f"  com endereco ..... {sum(1 for i in validos if i.endereco)}")
    print(f"  cidades .......... {len({i.cidade for i in validos if i.cidade})}")
    print(f"  ordinarios ....... {sum(1 for i in validos if 'Ordentliche' in i.tipo_filiacao)}")
    print(f"  associados ....... {sum(1 for i in validos if 'Assoziierte' in i.tipo_filiacao)}")
    print(f"  descartados ...... {len(descartados)}")
    for i in descartados:
        print(f"     - {i.url_perfil} :: {i.erro or 'sem contato'}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 66)
