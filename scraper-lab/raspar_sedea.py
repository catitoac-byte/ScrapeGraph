"""
Coleta das empresas associadas ao SEDEA (Grecia).

    uv run python -u raspar_sedea.py
"""

import time

from scraper_lab.sedea import (
    PAGINA_CARTOES,
    PAGINA_TABELA,
    codificacoes_detectadas,
    coletar,
    exportar,
    situacao_robots,
    tem_letras_gregas,
)

if __name__ == "__main__":
    inicio = time.time()

    print("[1/3] Verificando robots.txt")
    print(f"      sedea.gr: {situacao_robots()}")
    print(f"      tabela  : {PAGINA_TABELA}")
    print(f"      cartoes : {PAGINA_CARTOES}")

    print("\n[2/3] Coletando")
    empresas, resumo = coletar()
    for chave, valor in resumo.items():
        print(f"      {chave:22} {valor}")

    print("\n[3/3] Exportando")
    cj, cc = exportar(empresas)

    com_pessoa = [e for e in empresas if e.pessoas]
    gregos = sum(1 for e in empresas if tem_letras_gregas(e.nome))
    print("\n" + "=" * 64)
    print(f"  empresas ............. {len(empresas)}")
    for rotulo in sorted({e.tipo_associacao for e in empresas if e.tipo_associacao}):
        print(f"    {rotulo[:34]:34} {sum(1 for e in empresas if e.tipo_associacao == rotulo)}")
    print(f"  com email ............ {sum(1 for e in empresas if e.email)}")
    print(f"  com site ............. {sum(1 for e in empresas if e.site)}")
    print(f"  com telefone ......... {sum(1 for e in empresas if e.telefone)}")
    print(f"  com endereco ......... {sum(1 for e in empresas if e.endereco)}")
    print(f"  com nome de pessoa ... {len(com_pessoa)} "
          f"({sum(len(e.pessoas) for e in empresas)} pessoas)")
    print(f"  com nome latino ...... {sum(1 for e in empresas if e.nome_latino)}")
    print(f"  certificacao PESS .... {sum(1 for e in empresas if e.certificacao_pess.upper() == 'ΝΑΙ')}")
    print(f"  razao social em grego  {gregos}/{len(empresas)}  (prova de codificacao)")
    print(f"  divergencias ......... {sum(1 for e in empresas if e.erro)}")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 64)
