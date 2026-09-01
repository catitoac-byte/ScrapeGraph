"""
Coleta do diretorio de associadas da MRSI (India).

    uv run python -u raspar_mrsi.py
    uv run python -u raspar_mrsi.py --tipo 2   # aba educacional
"""

import sys
import time
from collections import Counter

from scraper_lab.mrsi import (
    TIPO_CORPORATIVO,
    Sessao,
    _preparar_robots,
    codificacoes_detectadas,
    coletar,
    exportar,
    listar_empresas,
)

if __name__ == "__main__":
    inicio = time.time()
    tipo = TIPO_CORPORATIVO
    if "--tipo" in sys.argv:
        tipo = int(sys.argv[sys.argv.index("--tipo") + 1])

    print("[1/4] Verificando robots.txt")
    print(f"      {_preparar_robots()}")

    print("\n[2/4] Abrindo o diretorio e paginando")
    sessao = Sessao()
    cartoes, declarado = listar_empresas(sessao, tipo=tipo)
    marca = "ok" if len(cartoes) == declarado else f"DIVERGE (site diz {declarado})"
    print(f"      {len(cartoes)} empresas listadas -> {marca}")

    print(f"\n[3/4] Coletando {len(cartoes)} fichas")
    empresas = coletar(sessao, cartoes, tipo=tipo, delay=1.6)

    print("\n[4/4] Exportando")
    nome_saida = "mrsi" if tipo == TIPO_CORPORATIVO else f"mrsi_tipo{tipo}"
    cj, cc = exportar(empresas, nome_saida)

    ok = [e for e in empresas if e.nome and not e.erro]
    atividades = Counter(e.tipo_atividade for e in ok if e.tipo_atividade)
    print("\n" + "=" * 66)
    print(f"  empresas ............. {len(ok)} (de {declarado} declaradas)")
    print(f"  com email ............ {sum(1 for e in ok if e.email)}")
    print(f"  com site ............. {sum(1 for e in ok if e.site)}")
    print(f"  com endereco ......... {sum(1 for e in ok if e.endereco)}")
    print(f"  com descricao ........ {sum(1 for e in ok if e.descricao)}")
    print(f"  com contatos ......... {sum(1 for e in ok if e.contatos)}")
    print(f"  categorias ........... {dict(Counter(e.tipo_associacao for e in ok))}")
    print("  tipo de atividade:")
    for atividade, n in atividades.most_common():
        print(f"      {atividade[:44]:46} {n}")
    print(f"  erros ................ {sum(1 for e in empresas if e.erro)}")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 66)
