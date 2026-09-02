"""
Coleta do diretorio de institutos do VMÖ (Austria).

    uv run python -u raspar_vmoe.py
"""

import time
from collections import Counter

from scraper_lab import vmoe
from scraper_lab.vmoe import DELAY_PADRAO, coletar, exportar, listar_institutos

if __name__ == "__main__":
    inicio = time.time()

    print("[1/3] Listando itens da pagina /institute/")
    alvos, situacao_robots = listar_institutos()
    print()

    print("[2/3] Coletando fichas")
    institutos = coletar(alvos, delay=DELAY_PADRAO)

    print("\n[3/3] Exportando")
    cj, cc = exportar(institutos)

    ok = [i for i in institutos if i.nome]
    com_ficha = [i for i in ok if i.url_perfil]
    print("\n" + "=" * 68)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com ficha VMÖ .... {len(com_ficha)}")
    print(f"  com email ........ {sum(1 for i in ok if i.email)}")
    print(f"  com site ......... {sum(1 for i in ok if i.site)}")
    print(f"  com telefone ..... {sum(1 for i in ok if i.telefone)}")
    print(f"  com endereco ..... {sum(1 for i in ok if i.endereco)}")
    print(f"  com fundacao ..... {sum(1 for i in ok if i.ano_fundacao)}")
    print(f"  com nome de pessoa {sum(1 for i in ok if i.direcao or i.contato or i.membros_vmoe)}")
    print(f"  com descricao .... {sum(1 for i in ok if i.descricao)}")
    print(f"  cidades .......... {len({i.cidade for i in ok if i.cidade})}")
    for tipo, n in Counter(i.tipo_membro for i in ok).most_common():
        print(f"  {tipo:<16} . {n}")
    for pais, n in Counter(i.pais or "sem pais" for i in ok).most_common():
        print(f"  pais {pais:<11} . {n}")
    ambiguos = [i for i in com_ficha if i.alinhamento_tabela == "ambiguo"]
    print(f"  tabela ambigua ... {len(ambiguos)}"
          f"   (valores nao distribuidos no chute)")
    erros = [i for i in institutos if i.erro]
    print(f"  erros ............ {len(erros)}")
    for i in erros[:12]:
        print(f"     - {(i.nome or i.url_perfil)[:44]:44} :: {i.erro}")
    print(f"  robots.txt ....... {situacao_robots}")
    print(f"  codificacao ...... {vmoe.CODIFICACAO_DETECTADA}")
    print(f"  tempo ............ {time.time() - inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 68)
