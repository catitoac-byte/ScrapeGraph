"""
Coleta do diretorio de asociadas da AMAI (Mexico).

O robots.txt da AMAI pede Crawl-delay: 30, entao a coleta leva cerca de
meia hora. Rode com -u para acompanhar o progresso.

    uv run python -u raspar_mexico.py
"""

import time

from scraper_lab.mexico import PAUSA_ROBOTS, coletar, exportar, listar_asociadas

if __name__ == "__main__":
    inicio = time.time()
    print(f"[1/3] Listando asociadas (pausa de {PAUSA_ROBOTS:.0f}s por robots.txt)")
    itens = listar_asociadas()
    print(f"      {len(itens)} empresas\n")

    print(f"[2/3] Coletando fichas (~{len(itens) * PAUSA_ROBOTS / 60:.0f} min)")
    regs = coletar(itens)

    print("\n[3/3] Exportando")
    cj, cc = exportar(regs)

    ok = [r for r in regs if r.nome and not r.erro]
    print("\n" + "=" * 66)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com email ........ {sum(1 for r in ok if r.email)}")
    print(f"  com site ......... {sum(1 for r in ok if r.site)}")
    print(f"  com telefone ..... {sum(1 for r in ok if r.telefone)}")
    print(f"  com endereco ..... {sum(1 for r in ok if r.endereco)}")
    print(f"  com contato ...... {sum(1 for r in ok if r.contato)}")
    print(f"  certificadas ..... {sum(1 for r in ok if r.certificados)}")
    print(f"  estados .......... {len({r.estado for r in ok if r.estado})}")
    print(f"  erros ............ {sum(1 for r in regs if r.erro)}")
    for r in regs:
        if r.erro:
            print(f"    ! {r.id_socio} {r.nome[:28]:28} {r.erro[:60]}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 66)
