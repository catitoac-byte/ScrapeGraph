"""
Coleta da comunidade da PTBRiO (Polonia). Sao PESSOAS, nao empresas: a
fonte de empresas polonesas e a OFBOR (raspar_ofbor.py).

    uv run python -u raspar_ptbrio.py
    uv run python -u raspar_ptbrio.py --limite 20   # amostra, para teste
"""

import sys
import time

from scraper_lab.ptbrio import (
    LISTAGEM,
    codificacoes_detectadas,
    coletar,
    exportar,
    listar_perfis,
    situacao_robots,
    tem_letras_polonesas,
)

if __name__ == "__main__":
    inicio = time.time()
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])

    print("[1/3] Verificando robots.txt")
    print(f"      ptbrio.pl: {situacao_robots()}")
    print(f"      listagem : {LISTAGEM}")

    print("\n[2/3] Listando perfis")
    perfis = listar_perfis()
    if limite:
        perfis = perfis[:limite]
        print(f"      amostra de {len(perfis)} perfis (--limite)")

    print(f"\n[3/3] Coletando {len(perfis)} perfis")
    pessoas = coletar(perfis)

    cj, cc = exportar(pessoas)

    com_empresa = [p for p in pessoas if p.empresa]
    falhas = [p for p in pessoas if p.erro and "sem empresa declarada" not in p.erro]
    empresas = sorted({p.empresa for p in com_empresa})
    print("\n" + "=" * 64)
    print(f"  pessoas .............. {len(pessoas)}")
    print(f"  com empresa .......... {len(com_empresa)}")
    print(f"  empresas distintas ... {len(empresas)}")
    print(f"  com cargo ............ {sum(1 for p in pessoas if p.cargo)}")
    print(f"  com biografia ........ {sum(1 for p in pessoas if p.descricao)}")
    print(f"  com email ............ {sum(1 for p in pessoas if p.email)}"
          f"   (so quem publicou icone de contato)")
    print(f"  com site ............. {sum(1 for p in pessoas if p.site)}")
    print(f"  com LinkedIn anotado . {sum(1 for p in pessoas if p.linkedin)}"
          f"   (URL registrada, nunca acessada)")
    print(f"  com numero de socio .. {sum(1 for p in pessoas if p.numero_socio)}")
    print(f"  nomes com letra pl ... {sum(1 for p in pessoas if tem_letras_polonesas(p.nome))}")
    print(f"  falhas de coleta ..... {len(falhas)}")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 64)
