"""
Coleta do elenco de aziende associate da ASSIRM (Italia).

    uv run python -u raspar_assirm.py
"""

import time

from scraper_lab.assirm import (
    _total_declarado,
    coletar,
    exportar,
    listar_associadas,
)

if __name__ == "__main__":
    inicio = time.time()

    print("[1/3] Listando associadas (tres abas de categoria)")
    pares = listar_associadas()
    declarado = _total_declarado()
    print(f"      {len(pares)} fichas italianas")
    if declarado:
        # O CPT soma fichas italianas e traducoes em ingles. Se a coleta nao
        # ficar perto da metade do declarado, alguma aba veio truncada.
        print(f"      CMS declara {declarado} posts (italiano + traducao en); "
              f"esperado ~{declarado // 2}")
    print()

    print("[2/3] Coletando fichas")
    registros = coletar(pares, delay=1.6)

    print("\n[3/3] Exportando")
    cj, cc = exportar(registros)

    ok = [r for r in registros if r.nome]
    print("\n" + "=" * 64)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com email ........ {sum(1 for r in ok if r.email)}")
    print(f"  com site ......... {sum(1 for r in ok if r.site)}")
    print(f"  com telefone ..... {sum(1 for r in ok if r.telefone)}")
    print(f"  com endereco ..... {sum(1 for r in ok if r.endereco)}")
    print(f"  com descricao .... {sum(1 for r in ok if r.descricao)}")
    print(f"  cidades .......... {len({r.cidade for r in ok if r.cidade})}")
    print(f"  erros ............ {sum(1 for r in registros if r.erro)}")
    print(f"  tempo ............ {time.time() - inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 64)
