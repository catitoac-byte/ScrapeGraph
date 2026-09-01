"""
Executa todos os filtros pedidos, com cache global e retomada.

    uv run python -u rodar_filtros.py
"""

import time
from pathlib import Path

from scraper_lab.pipeline import (
    SAIDA,
    carregar_cache,
    executar,
    exportar_mestre,
    importar_json,
    salvar_cache,
)

FILTROS = [
    "https://directory.esomar.org/search/*?solution=6",
    "https://directory.esomar.org/search/*?solution=6&market=16&service=8",
    "https://directory.esomar.org/search/*?solution=6&solution=3&market=16",
    "https://directory.esomar.org/search/*?solution=3",
    "https://directory.esomar.org/search/*?solution=4",
    "https://directory.esomar.org/search/*?solution=7",
]

if __name__ == "__main__":
    inicio = time.time()

    # aproveita o que a corrida dos EUA ja coletou
    cache = carregar_cache()
    for antigo in ["esomar_eua.json", "esomar_pn4.json"]:
        n = importar_json(SAIDA / antigo, cache)
        if n:
            print(f"importado de {antigo}: {n} perfis")
    salvar_cache(cache)

    registros = executar(FILTROS, delay=2.0)
    cj, cc = exportar_mestre(registros)

    com_email = sum(1 for r in registros.values() if r.get("email"))
    contatos = sum(len(r.get("contatos") or []) for r in registros.values())
    paises = {r.get("pais", "") for r in registros.values()}

    print("\n" + "=" * 62)
    print(f"  empresas unicas .. {len(registros)}")
    print(f"  com email ........ {com_email}")
    print(f"  contatos ......... {contatos}")
    print(f"  paises ........... {len(paises)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
