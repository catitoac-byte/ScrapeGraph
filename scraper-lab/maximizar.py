"""
Etapa final: varre as demais dimensoes de faceta para maximizar cobertura.

A particao por pais alcanca quem tem sede declarada. Empresas sem pais
tagueado ficariam de fora, mas podem aparecer em market / solution / service.
Aqui varremos essas dimensoes e ficamos com a UNIAO de tudo.

O cache e compartilhado, entao perfil ja conhecido nao e visitado de novo:
o custo real desta etapa e quase so listagem.

    uv run python -u maximizar.py
"""

import json
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.pipeline import carregar_cache, executar, exportar_mestre, salvar_cache

RAIZ = Path(__file__).resolve().parent
MAPA = RAIZ / "dados" / "facetas_ids.json"
BUSCA = "https://directory.esomar.org/search/*?"

DIMENSOES = {"solution": 40, "market": 40, "service": 60}
MAX_VAZIOS = 10


def esperar(*processos: str, timeout: float = 28800) -> None:
    limite = time.time() + timeout
    for nome in processos:
        avisou = False
        while time.time() < limite:
            vivo = subprocess.run(["pgrep", "-f", nome],
                                  capture_output=True, text=True).stdout.strip()
            if not vivo:
                if avisou:
                    print(f"      {nome} concluido")
                break
            if not avisou:
                print(f"[0/3] Aguardando {nome}...")
                avisou = True
            time.sleep(20)
    print()


def descobrir() -> dict[str, list[dict]]:
    """Sonda IDs de cada dimensao. Validade pelo numero de resultados."""
    if MAPA.exists():
        d = json.loads(MAPA.read_text(encoding="utf-8"))
        print(f"mapa de facetas em cache: "
              f"{sum(len(v) for v in d.values())} valores")
        return d

    print("=" * 62)
    print("FASE 0  descobrindo IDs das facetas")
    print("=" * 62)
    achados: dict[str, list[dict]] = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        try:
            for dim, teto in DIMENSOES.items():
                achados[dim] = []
                vazios = 0
                print(f"\n-- {dim} --")
                for i in range(1, teto + 1):
                    # 4s com retentativa: 1.7s dava falso negativo porque o
                    # Angular ainda nao tinha renderizado a contagem.
                    total = 0
                    for tentativa in (1, 2):
                        pg.goto(f"{BUSCA}{dim}={i}", wait_until="networkidle", timeout=60_000)
                        pg.wait_for_timeout(4000 if tentativa == 1 else 8000)
                        m = re.search(r"([\d,]+)\s+Compan", pg.inner_text("body"))
                        if m:
                            total = int(m.group(1).replace(",", ""))
                            break
                    if total > 0:
                        rotulo = pg.title().split("|")[0].strip()[:44]
                        achados[dim].append({"id": i, "total": total, "rotulo": rotulo})
                        vazios = 0
                        print(f"  {dim}={i:>3} {total:>5}  {rotulo}")
                    else:
                        vazios += 1
                        if vazios >= MAX_VAZIOS:
                            print(f"  parando em {i} ({vazios} vazios seguidos)")
                            break
        finally:
            b.close()

    MAPA.parent.mkdir(parents=True, exist_ok=True)
    MAPA.write_text(json.dumps(achados, ensure_ascii=False, indent=1), encoding="utf-8")
    return achados


if __name__ == "__main__":
    inicio = time.time()
    esperar("fila.py", "varredura_paises.py", "reparo.py")

    mapa = descobrir()
    # maiores primeiro: cobrem mais cedo, e o cache poupa o resto
    filtros = [
        f"{BUSCA}{dim}={v['id']}"
        for dim, vals in mapa.items()
        for v in sorted(vals, key=lambda x: -x["total"])
    ]
    print(f"\n{len(filtros)} filtros de faceta a percorrer")

    antes = len([v for v in carregar_cache().values() if v.get("nome")])
    print(f"perfis ja coletados: {antes}\n")

    executar(filtros, delay=2.0)

    cache = carregar_cache()
    completo = {k: v for k, v in cache.items() if v.get("nome")}
    salvar_cache(cache)
    cj, cc = exportar_mestre(completo, "esomar_mestre")

    com_email = sum(1 for r in completo.values() if r.get("email"))
    com_site = sum(1 for r in completo.values() if r.get("site"))
    contatos = sum(len(r.get("contatos") or []) for r in completo.values())
    paises = {r.get("pais") for r in completo.values() if r.get("pais")}

    print("\n" + "=" * 62)
    print("  COBERTURA MAXIMA ATINGIDA")
    print(f"  empresas totais .. {len(completo)}")
    print(f"  novas nesta etapa. {len(completo) - antes}")
    print(f"  com email ........ {com_email}")
    print(f"  com site ......... {com_site}")
    print(f"  contatos ......... {contatos}")
    print(f"  paises ........... {len(paises)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  JSON ............. {cj}")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
