"""
Coleta dos Corporate Member da SWISS INSIGHTS (Suica, ex-vsms/asms).

    uv run python -u raspar_swiss_insights.py
"""

import time
from collections import Counter

from scraper_lab import swiss_insights
from scraper_lab.swiss_insights import coletar, exportar

if __name__ == "__main__":
    inicio = time.time()

    print("[1/2] Lendo a pagina de Corporate Member")
    membros, situacao_robots = coletar()

    print("\n[2/2] Exportando")
    cj, cc = exportar(membros)

    ok = [m for m in membros if m.nome]
    print("\n" + "=" * 70)
    print(f"  empresas ......... {len(ok)}")
    print(f"  declarado no site  a fonte nao publica total, sem conferencia possivel")
    print(f"  com email ........ {sum(1 for m in ok if m.email)}")
    print(f"  com site ......... {sum(1 for m in ok if m.site)}")
    print(f"  com endereco ..... {sum(1 for m in ok if m.endereco)}")
    print(f"  com telefone ..... {sum(1 for m in ok if m.telefone)}"
          f"   (a fonte nao publica telefone)")
    print(f"  com nome de pessoa 0   (a fonte nao publica pessoa de contato)")
    print(f"  cidades .......... {len({m.cidade for m in ok if m.cidade})}")
    print("  origem do nome:")
    for origem, n in Counter(m.nome_origem or "sem nome" for m in membros).most_common():
        print(f"    {origem:<10} {n}")
    print("  selo declarado pela associacao:")
    for selo, n in Counter(m.selos or "sem selo" for m in membros).most_common():
        print(f"    {n:>3}  {selo}")
    print(f"  fornecedores ..... {sum(1 for m in ok if m.fornecedor_pesquisa == 'sim')}"
          f"   (selo Market and Social Research)")
    print(f"  indefinidos ...... {sum(1 for m in ok if m.fornecedor_pesquisa != 'sim')}"
          f"   (a fonte nao classifica)")
    erros = [m for m in membros if m.erro]
    print(f"  erros ............ {len(erros)}")
    for m in erros[:10]:
        print(f"     - {(m.dominio or m.logo)[:52]:52} :: {m.erro}")
    print(f"  robots.txt ....... {situacao_robots}")
    print(f"  codificacao ...... {swiss_insights.CODIFICACAO_DETECTADA}")
    print(f"  tempo ............ {time.time() - inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 70)
