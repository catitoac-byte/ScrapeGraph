"""
Coleta dos associados da JMRA (Japao).

    uv run python -u raspar_jmra.py
    uv run python -u raspar_jmra.py --so-regulares   # apenas 正会員
"""

import sys
import time

from scraper_lab.jmra import (
    _preparar_robots,
    codificacoes_detectadas,
    coletar,
    contagem_declarada,
    exportar,
    listar_empresas,
)

if __name__ == "__main__":
    inicio = time.time()
    so_regulares = "--so-regulares" in sys.argv

    print("[1/4] Verificando robots.txt")
    print(f"      {_preparar_robots()}")

    print("\n[2/4] Listando membros")
    alvos = listar_empresas(incluir_sanjo=not so_regulares)
    time.sleep(1.6)
    oficial = contagem_declarada()
    print(f"      contagem declarada pela JMRA: {oficial}")

    coletados = {}
    for _, _, tipo in alvos:
        coletados[tipo] = coletados.get(tipo, 0) + 1
    for tipo, n in coletados.items():
        esperado = oficial.get(tipo)
        marca = "ok" if esperado == n else f"DIVERGE (site diz {esperado})"
        print(f"      {tipo}: {n} listados -> {marca}")

    print(f"\n[3/4] Coletando {len(alvos)} fichas")
    empresas = coletar(alvos, delay=1.6)

    print("\n[4/4] Exportando")
    cj, cc = exportar(empresas)

    ok = [e for e in empresas if e.nome and not e.erro]
    reg = [e for e in ok if e.tipo_associacao == "正会員"]
    print("\n" + "=" * 64)
    print(f"  empresas ............. {len(ok)}")
    print(f"    正会員 (pesquisa) .. {len(reg)}")
    print(f"    賛助法人会員 ....... {len(ok) - len(reg)}")
    print(f"  com email ............ {sum(1 for e in ok if e.email)}")
    print(f"  com site ............. {sum(1 for e in ok if e.site)}")
    print(f"  com telefone ......... {sum(1 for e in ok if e.telefone)}")
    print(f"  com endereco ......... {sum(1 for e in ok if e.endereco)}")
    print(f"  com descricao ........ {sum(1 for e in ok if e.descricao)}")
    print(f"  so form. de contato .. {sum(1 for e in ok if not e.email and e.contato_url)}")
    print(f"  erros ................ {sum(1 for e in empresas if e.erro)}")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 64)
