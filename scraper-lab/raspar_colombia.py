"""
Coleta das afiliadas da ACEI (Colombia).

    uv run python -u raspar_colombia.py
"""

import time

from scraper_lab.colombia import coletar, exportar

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Listando afiliadas")
    afiliadas = coletar(delay=1.6)

    print("\n[2/3] Exportando")
    cj, cc = exportar(afiliadas)

    print("\n[3/3] Conferencia")
    ok = [a for a in afiliadas if a.nome]
    print("=" * 66)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com site ......... {sum(1 for a in ok if a.site)}")
    print(f"  com descricao .... {sum(1 for a in ok if a.descricao)}")
    print(f"  com email ........ {sum(1 for a in ok if a.email)}  "
          f"(a ACEI nao publica e-mail)")
    print(f"  nome a revisar ... {sum(1 for a in ok if a.revisar_nome)}")
    print(f"  erros ............ {sum(1 for a in afiliadas if a.erro)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 66)
    for a in ok:
        if a.revisar_nome or a.erro:
            print(f"    ? {a.nome[:22]:22} logo={a.arquivo_logo[:30]:30} "
                  f"{a.site[:40]}")
