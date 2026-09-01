"""Coleta dos socios da AIM Chile, com enriquecimento no site de cada empresa."""

import time

from scraper_lab.aim import enriquecer, exportar, listar_socios

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Lista da AIM")
    socios = listar_socios()
    print(f"      {len(socios)} empresas | {sum(1 for s in socios if s.nome)} com nome na AIM\n")

    print("[2/3] Visitando o site de cada empresa")
    for s in socios:
        enriquecer(s, delay=1.0)
        time.sleep(1.0)

    print("\n[3/3] Exportando")
    cj, cc = exportar(socios)
    print(f"\n{'='*58}")
    print(f"  empresas ......... {len(socios)}")
    print(f"  com nome ......... {sum(1 for s in socios if s.nome)}")
    print(f"  com email ........ {sum(1 for s in socios if s.email)}")
    print(f"  bloqueadas robots. {sum(1 for s in socios if 'robots' in s.erro)}")
    print(f"  com erro ......... {sum(1 for s in socios if s.erro)}")
    print(f"  tempo ............ {time.time()-inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print(f"{'='*58}")
