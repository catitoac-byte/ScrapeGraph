"""
Coleta dos membros da CUBE (Belgica, ex-FEBELMAR + BAQMaR).

    uv run python -u raspar_cube.py
"""

import time
from collections import Counter

from scraper_lab import cube
from scraper_lab.cube import coletar, exportar, util

if __name__ == "__main__":
    inicio = time.time()

    print("[1/2] Lendo o CMS da CUBE pela API REST")
    membros, resumo = coletar()

    print("\n[2/2] Exportando")
    validos, descartados = [], []
    for m in membros:
        ok, motivo = util(m)
        (validos if ok else descartados).append((m, motivo))
    cj, cc = exportar([m for m, _ in validos])

    ok = [m for m, _ in validos]
    com_ficha = [m for m in ok if m.tem_ficha == "sim"]
    print("\n" + "=" * 70)
    print(f"  empresas ......... {len(ok)}")
    print(f"  com ficha propria  {len(com_ficha)}")
    print(f"  so na lista ...... {len(ok) - len(com_ficha)}")
    print(f"  com email ........ {sum(1 for m in ok if m.email)}")
    print(f"  com site ......... {sum(1 for m in ok if m.site)}")
    print(f"  com telefone ..... {sum(1 for m in ok if m.telefone)}")
    print(f"  com nome de pessoa {sum(1 for m in ok if m.contato_nome)}")
    print(f"  com cargo ........ {sum(1 for m in ok if m.contato_cargo)}")
    print(f"  com descricao .... {sum(1 for m in ok if m.descricao)}")
    print(f"  com endereco ..... {sum(1 for m in ok if m.endereco)}"
          f"   (a fonte nao publica endereco)")
    print("  onde aparece:")
    for onde, n in Counter(m.listado_em or "sem lista" for m in ok).most_common():
        print(f"    {n:>3}  {onde}")
    print(f"  paginas no CMS ... {resumo['paginas_cms']}"
          + (f" (CMS declara {resumo['total_declarado']})" if resumo["total_declarado"] else ""))
    erros = [m for m in ok if m.erro]
    print(f"  com aviso ........ {len(erros)}")
    for m in erros[:12]:
        print(f"     - {m.nome[:40]:40} :: {m.erro}")
    print(f"  descartados ...... {len(descartados)}")
    for m, motivo in descartados:
        print(f"     - {(m.nome or m.site)[:40]:40} :: {motivo}")
    print(f"  robots.txt ....... {resumo['situacao_robots']} (soft 404, sem regras reais)")
    print(f"  codificacao ...... {cube.CODIFICACAO_DETECTADA}")
    print(f"  tempo ............ {time.time() - inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 70)
