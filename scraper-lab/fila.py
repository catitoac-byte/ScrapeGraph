"""
Fila completa: espera o job em andamento, importa o que ele produziu e
processa todos os filtros ate o fim, sem intervencao.

    uv run python -u fila.py
"""

import subprocess
import sys
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

# O filtro dos EUA entra na fila para o mestre sair unificado. Seus perfis
# ja estarao em cache, entao so a listagem (barata) roda de novo.
FILA = [
    "https://directory.esomar.org/search/*?from=2",
    "https://directory.esomar.org/search/*?solution=6",
    "https://directory.esomar.org/search/*?solution=6&market=16&service=8",
    "https://directory.esomar.org/search/*?solution=6&solution=3&market=16",
    "https://directory.esomar.org/search/*?solution=3",
    "https://directory.esomar.org/search/*?solution=4",
    "https://directory.esomar.org/search/*?solution=7",
]


def esperar_job_anterior(timeout: float = 2400) -> None:
    """Aguarda o raspar_esomar.py em andamento terminar, se houver."""
    limite = time.time() + timeout
    primeiro = True
    while time.time() < limite:
        vivo = subprocess.run(
            ["pgrep", "-f", "raspar_esomar.py"],
            capture_output=True, text=True,
        ).stdout.strip()
        if not vivo:
            if not primeiro:
                print("      job anterior concluido")
            return
        if primeiro:
            print("[0/3] Aguardando o job dos EUA terminar...")
            primeiro = False
        time.sleep(15)
    print("      timeout na espera; seguindo assim mesmo", file=sys.stderr)


if __name__ == "__main__":
    inicio = time.time()

    esperar_job_anterior()

    cache = carregar_cache()
    total_importado = 0
    for antigo in ["esomar_eua.json", "esomar_pn4.json"]:
        n = importar_json(SAIDA / antigo, cache)
        total_importado += n
        if n:
            print(f"      importado de {antigo}: {n} perfis")
    salvar_cache(cache)
    print(f"      cache apos importacao: {len(cache)} perfis\n")

    registros = executar(FILA, delay=2.0)
    cj, cc = exportar_mestre(registros)

    com_email = sum(1 for r in registros.values() if r.get("email"))
    com_site = sum(1 for r in registros.values() if r.get("site"))
    contatos = sum(len(r.get("contatos") or []) for r in registros.values())
    paises = {r.get("pais") for r in registros.values() if r.get("pais")}

    print("\n" + "=" * 62)
    print("  FILA CONCLUIDA")
    print(f"  empresas unicas .. {len(registros)}")
    print(f"  com email ........ {com_email}")
    print(f"  com site ......... {com_site}")
    print(f"  contatos ......... {contatos}")
    print(f"  paises ........... {len(paises)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  JSON ............. {cj}")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
