"""
Coleta do Ledenoverzicht do Data & Insights Network (Holanda, ex-MOA).

    uv run python -u raspar_din.py
"""

import time
from collections import Counter

# O modulo inteiro e importado porque CODIFICACAO_DETECTADA so tem valor
# depois da primeira requisicao; importar o nome fixaria a string vazia.
from scraper_lab import din
from scraper_lab.din import DELAY_PADRAO, coletar, exportar, listar_membros

if __name__ == "__main__":
    inicio = time.time()

    print("[1/3] Lendo o Ledenoverzicht")
    listagem = listar_membros()
    print()

    print("[2/3] Coletando fichas detalhadas")
    membros = coletar(listagem, delay=DELAY_PADRAO)

    print("\n[3/3] Exportando")
    cj, cc = exportar(membros)

    ok = [m for m in membros if m.nome]
    tipos = Counter(m.tipo_membro or "sem tipo" for m in ok)
    print("\n" + "=" * 68)
    print(f"  empresas ......... {len(ok)}")
    if listagem.total_declarado is not None:
        conferencia = "confere" if listagem.total_declarado == len(membros) else "DIVERGENCIA"
        print(f"  declarado no site  {listagem.total_declarado} ({conferencia})")
    print(f"  com email ........ {sum(1 for m in ok if m.email)}"
          f"   (a fonte nao publica e-mail)")
    print(f"  com site ......... {sum(1 for m in ok if m.site)}")
    print(f"  com telefone ..... {sum(1 for m in ok if m.telefone)}")
    print(f"  com endereco ..... {sum(1 for m in ok if m.endereco)}")
    print(f"  com descricao .... {sum(1 for m in ok if m.descricao)}")
    print(f"  com FTE .......... {sum(1 for m in ok if m.funcionarios)}")
    print(f"  com certificacao . {sum(1 for m in ok if m.certificacoes)}")
    print(f"  cidades .......... {len({m.cidade for m in ok if m.cidade})}")
    for tipo, n in tipos.most_common():
        print(f"  {tipo:<16} . {n}")
    print(f"  fornecedores ..... {sum(1 for m in ok if m.fornecedor_pesquisa == 'sim')}"
          f"   (Agency + Supplier)")
    print(f"  compradores ...... {sum(1 for m in ok if m.fornecedor_pesquisa == 'nao')}"
          f"   (Company: departamento interno)")
    print(f"  erros ............ {sum(1 for m in membros if m.erro)}")
    print(f"  robots.txt ....... {listagem.situacao_robots}")
    print(f"  codificacao ...... {din.CODIFICACAO_DETECTADA}")
    print(f"  tempo ............ {time.time() - inicio:.0f}s")
    print(f"  CSV .............. {cc}")
    print("=" * 68)
