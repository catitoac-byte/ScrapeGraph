"""
Coleta do diretorio de asociadas da APEIM (Peru).

    uv run python -u raspar_peru.py
"""

import time

from scraper_lab.peru import coletar, exportar, listar_asociadas, total_declarado

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Listando asociadas")
    itens = listar_asociadas()
    declarado = total_declarado()
    print(f"      {len(itens)} empresas na listagem "
          f"(o site declara {declarado or '?'})\n")

    print("[2/3] Coletando fichas")
    regs = coletar(itens, delay=1.6)

    print("\n[3/3] Exportando")
    cj, cc = exportar(regs)

    ok = [r for r in regs if r.nome]
    print("\n" + "=" * 62)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com email ........ {sum(1 for r in ok if r.email)}")
    print(f"  com site ......... {sum(1 for r in ok if r.site)}")
    print(f"  com telefone ..... {sum(1 for r in ok if r.telefone)}")
    print(f"  com endereco ..... {sum(1 for r in ok if r.endereco)}")
    print(f"  com contato ...... {sum(1 for r in ok if r.contato)}")
    print(f"  erros ............ {sum(1 for r in regs if r.erro)}")
    if declarado and declarado != len(ok):
        print(f"  ATENCAO .......... site declara {declarado}, coletamos {len(ok)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
