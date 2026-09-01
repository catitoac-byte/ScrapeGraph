"""
Varredura pais a pais do diretorio Esomar.

A busca sem filtro nao devolve resultados: o site exige ao menos uma faceta.
Como cada empresa tem exatamente um pais de sede, a particao por pais e a que
da cobertura sem sobreposicao artificial.

Roda depois da fila de filtros e compartilha o mesmo cache, entao so coleta
perfis ainda desconhecidos.

    uv run python -u varredura_paises.py
"""

import json
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.pipeline import (
    carregar_cache,
    executar,
    exportar_mestre,
    salvar_cache,
)

RAIZ = Path(__file__).resolve().parent
MAPA = RAIZ / "dados" / "paises_ids.json"
BASE = "https://directory.esomar.org/search/*?from="

# Sondamos com folga: 108 paises listados na faceta, IDs sequenciais desde 1.
TETO_ID = 140
MAX_VAZIOS_SEGUIDOS = 12


def esperar(nome_processo: str, timeout: float = 14400) -> None:
    limite = time.time() + timeout
    avisou = False
    while time.time() < limite:
        vivo = subprocess.run(["pgrep", "-f", nome_processo],
                              capture_output=True, text=True).stdout.strip()
        if not vivo:
            if avisou:
                print(f"      {nome_processo} concluido\n")
            return
        if not avisou:
            print(f"[0/3] Aguardando {nome_processo} terminar...")
            avisou = True
        time.sleep(20)


def descobrir_paises() -> list[dict]:
    """Sonda from=1.. e devolve [{id, pais, total}] dos IDs validos."""
    if MAPA.exists():
        dados = json.loads(MAPA.read_text(encoding="utf-8"))
        print(f"mapa de paises em cache: {len(dados)} paises")
        return dados

    print("=" * 62)
    print("FASE 0  descobrindo IDs de pais")
    print("=" * 62)
    achados: list[dict] = []
    vazios = 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        try:
            for i in range(1, TETO_ID + 1):
                pg.goto(f"{BASE}{i}", wait_until="networkidle", timeout=60_000)
                pg.wait_for_timeout(1800)
                titulo = pg.title().split("|")[0]
                pais = titulo.replace("Market research in", "").strip()
                m = re.search(r"([\d,]+)\s+Compan", pg.inner_text("body"))
                total = int(m.group(1).replace(",", "")) if m else 0

                valido = bool(pais) and pais.upper() != "BROWSE RESEARCH COMPANIES" and total > 0
                if valido:
                    achados.append({"id": i, "pais": pais, "total": total})
                    vazios = 0
                    print(f"  from={i:>3} {pais[:34]:34} {total:>5}")
                else:
                    vazios += 1
                    if vazios >= MAX_VAZIOS_SEGUIDOS:
                        print(f"  {vazios} IDs vazios seguidos; parando em {i}")
                        break
        finally:
            b.close()

    MAPA.parent.mkdir(parents=True, exist_ok=True)
    MAPA.write_text(json.dumps(achados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(achados)} paises | soma {sum(a['total'] for a in achados)}")
    return achados


if __name__ == "__main__":
    inicio = time.time()
    esperar("fila.py")

    paises = descobrir_paises()
    filtros = [f"{BASE}{p['id']}" for p in paises]

    antes = len([v for v in carregar_cache().values() if v.get("nome")])
    print(f"\nperfis ja coletados antes da varredura: {antes}")

    registros = executar(filtros, delay=2.0)

    # o mestre precisa unir varredura de paises E os filtros de solution
    cache = carregar_cache()
    completo = {k: v for k, v in cache.items() if v.get("nome")}
    salvar_cache(cache)
    cj, cc = exportar_mestre(completo, "esomar_mestre")

    com_email = sum(1 for r in completo.values() if r.get("email"))
    com_site = sum(1 for r in completo.values() if r.get("site"))
    contatos = sum(len(r.get("contatos") or []) for r in completo.values())
    paises_ok = {r.get("pais") for r in completo.values() if r.get("pais")}

    print("\n" + "=" * 62)
    print("  VARREDURA CONCLUIDA")
    print(f"  empresas totais .. {len(completo)}")
    print(f"  novas nesta etapa. {len(completo) - antes}")
    print(f"  com email ........ {com_email}")
    print(f"  com site ......... {com_site}")
    print(f"  contatos ......... {contatos}")
    print(f"  paises ........... {len(paises_ok)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
