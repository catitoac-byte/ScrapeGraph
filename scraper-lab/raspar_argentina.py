"""
Coleta das socias da CEIM (Argentina) e reconferencia da SAIMO.

    uv run python -u raspar_argentina.py
"""

import time

from scraper_lab.argentina import (
    coletar, estado_diretorio_saimo, exportar, total_declarado,
)

if __name__ == "__main__":
    inicio = time.time()
    print("[1/4] Conferindo a SAIMO")
    print(f"      {estado_diretorio_saimo()}\n")

    print("[2/4] Listando socias da CEIM")
    socias = coletar(delay=1.6)
    declarado = total_declarado()

    print("\n[3/4] Exportando")
    cj, cc = exportar(socias)

    print("\n[4/4] Conferencia")
    ok = [s for s in socias if s.nome]
    print("=" * 66)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com site ......... {sum(1 for s in ok if s.site)}")
    print(f"  com email ........ {sum(1 for s in ok if s.email)}  "
          f"(a CEIM nao publica e-mail)")
    print(f"  nome a revisar ... {sum(1 for s in ok if s.revisar_nome)}")
    print(f"  so rede social ... {sum(1 for s in ok if s.perfil_social)}")
    if declarado and declarado != len(ok):
        print(f"  ATENCAO .......... site declara {declarado}, coletamos {len(ok)}")
    else:
        print(f"  total declarado .. {declarado} (confere)")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 66)
    for s in ok:
        if s.revisar_nome or s.erro:
            print(f"    ? {s.nome[:24]:24} logo={s.arquivo_logo[:26]:26} "
                  f"{(s.site or s.perfil_social)[:44]}")
