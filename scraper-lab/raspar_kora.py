"""
Coleta das associadas da KORA (Coreia do Sul).

    uv run python -u raspar_kora.py
    uv run python -u raspar_kora.py --sem-latino   # pula o site em ingles
"""

import sys
import time

from scraper_lab.kora import (
    _preparar_robots,
    anexar_nomes_latinos,
    codificacoes_detectadas,
    coletar,
    exportar,
    listar_membros,
)

if __name__ == "__main__":
    inicio = time.time()
    sem_latino = "--sem-latino" in sys.argv

    print("[1/5] Verificando robots.txt")
    for dominio, relato in _preparar_robots().items():
        print(f"      {dominio}: {relato}")

    print("\n[2/5] Listando associadas (ikora.or.kr/About)")
    membros = listar_membros()
    origens: dict[str, int] = {}
    for m in membros:
        origens[m["origem"]] = origens.get(m["origem"], 0) + 1
    print(f"      {len(membros)} no total; por origem: {origens}")

    print(f"\n[3/5] Coletando fichas")
    empresas = coletar(membros, delay=1.6)

    if sem_latino:
        casados, total_en = 0, 0
        print("\n[4/5] Nome latino pulado (--sem-latino)")
    else:
        print("\n[4/5] Casando nomes latinos (en.ikora.or.kr)")
        casados, total_en = anexar_nomes_latinos(empresas, delay=1.6)
        print(f"      {casados}/{len(empresas)} casados por e-mail ou dominio")

    print("\n[5/5] Exportando")
    cj, cc = exportar(empresas)

    com_ficha = [e for e in empresas if not e.erro]
    plenas = [e for e in empresas if e.tipo_associacao == "정회원사"]
    print("\n" + "=" * 64)
    print(f"  empresas listadas .... {len(empresas)}")
    print(f"    정회원사 (plenas) .. {len(plenas)}")
    print(f"    준회원사 (juniores)  {len(empresas) - len(plenas)}")
    print(f"  com ficha completa ... {len(com_ficha)}")
    print(f"  com email ............ {sum(1 for e in empresas if e.email)}")
    print(f"  com site ............. {sum(1 for e in empresas if e.site)}")
    print(f"  com telefone ......... {sum(1 for e in empresas if e.telefone)}")
    print(f"  com endereco ......... {sum(1 for e in empresas if e.endereco)}")
    print(f"  com nome latino ...... {sum(1 for e in empresas if e.nome_latino)}"
          f"  (de {total_en} itens em ingles)")
    print(f"  sem ficha publicada .. {sum(1 for e in empresas if e.erro)}")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 64)
