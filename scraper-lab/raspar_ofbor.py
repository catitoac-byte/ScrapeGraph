"""
Coleta das empresas associadas a OFBOR (Polonia).

    uv run python -u raspar_ofbor.py
"""

import time

from scraper_lab.ofbor import (
    HOME,
    codificacoes_detectadas,
    coletar,
    exportar,
    situacao_robots,
    tem_letras_polonesas,
)

if __name__ == "__main__":
    inicio = time.time()

    print("[1/3] Verificando robots.txt")
    print(f"      ofbor.pl: {situacao_robots()}  ({HOME}robots.txt)")

    print("\n[2/3] Coletando")
    empresas, resumo = coletar()
    for chave, valor in resumo.items():
        print(f"      {chave:24} {valor}")
    if not resumo["bate_com_o_declarado"]:
        print("      [aviso] a contagem coletada nao bate com X-WP-Total")

    print("\n[3/3] Exportando")
    cj, cc = exportar(empresas)

    print("\n" + "=" * 64)
    print(f"  empresas ............. {len(empresas)}")
    print(f"  com email ............ {sum(1 for e in empresas if e.email)}"
          f"   (a OFBOR nao publica e-mail de associada)")
    print(f"  com site ............. {sum(1 for e in empresas if e.site)}")
    print(f"  com telefone ......... {sum(1 for e in empresas if e.telefone)}")
    print(f"  com nome de pessoa ... 0   (a fonte nao traz contato pessoal)")
    print(f"  nomes com letra pl ... {sum(1 for e in empresas if tem_letras_polonesas(e.nome))}")
    print(f"  sem site ............. {sum(1 for e in empresas if not e.site)}")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 64)
