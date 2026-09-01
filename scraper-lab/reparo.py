"""
Etapa de reparo e verificacao.

Motivo: a sondagem de IDs usou espera de 1.8s, curta demais para o app
Angular renderizar a contagem. Isso gerou falsos negativos (India, from=18,
com 71 empresas, foi marcada como vazia). Aqui resondamos com espera maior
e retentativa, depois conferimos empresa a empresa contra a faceta.

    uv run python -u reparo.py
"""

import json
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.pipeline import carregar_cache, executar, exportar_mestre, salvar_cache

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
BASE = "https://directory.esomar.org/search/*?from="
TETO = 260          # Virgin Islands esta em 248
ESPERA_MS = 4000    # era 1800: a causa dos falsos negativos


def esperar(*processos: str, timeout: float = 36000) -> None:
    limite = time.time() + timeout
    for nome in processos:
        avisou = False
        while time.time() < limite:
            if not subprocess.run(["pgrep", "-f", nome], capture_output=True,
                                  text=True).stdout.strip():
                if avisou:
                    print(f"      {nome} concluido")
                break
            if not avisou:
                print(f"[0/4] Aguardando {nome}...")
                avisou = True
            time.sleep(20)
    print()


def sondar(pg, ident: int) -> tuple[str, int]:
    """Devolve (pais, total). Retenta uma vez antes de dar como vazio."""
    for tentativa in (1, 2):
        pg.goto(f"{BASE}{ident}", wait_until="networkidle", timeout=60_000)
        pg.wait_for_timeout(ESPERA_MS if tentativa == 1 else ESPERA_MS * 2)
        corpo = pg.inner_text("body")
        m = re.search(r"([\d,]+)\s+Compan", corpo)
        if m:
            pais = pg.title().split("|")[0].replace("Market research in", "").strip()
            # Titulo generico = pagina de navegacao, nao um pais real.
            if pais.upper().startswith("BROWSE"):
                return "", 0
            return pais, int(m.group(1).replace(",", ""))
    return "", 0


def resondar_tudo() -> list[dict]:
    pronto = DADOS / "paises_ids_completo.json"
    if pronto.exists():
        dados = json.loads(pronto.read_text())
        print(f"sondagem completa reaproveitada: {len(dados)} paises")
        return dados
    conhecidos = {d["id"]: d for d in json.loads((DADOS / "paises_ids.json").read_text())}
    for d in json.loads((DADOS / "paises_faltantes.json").read_text()):
        conhecidos.setdefault(d["id"], d)

    alvos = [i for i in range(1, TETO + 1) if i not in conhecidos]
    print("=" * 62)
    print(f"FASE 1  resondando {len(alvos)} IDs com espera de {ESPERA_MS}ms")
    print("=" * 62)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        try:
            for ident in alvos:
                pais, total = sondar(pg, ident)
                if total > 0 and pais:
                    conhecidos[ident] = {"id": ident, "pais": pais, "total": total}
                    print(f"  RECUPERADO from={ident:>4} {pais[:30]:30} {total:>5}")
        finally:
            b.close()

    todos = sorted(conhecidos.values(), key=lambda d: d["id"])
    (DADOS / "paises_ids_completo.json").write_text(
        json.dumps(todos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(todos)} paises | soma {sum(d['total'] for d in todos)}")
    return todos


def conferir(paises: list[dict]) -> None:
    """Compara o coletado por pais contra o esperado de cada filtro."""
    cache = carregar_cache()
    ok = [v for v in cache.values() if v.get("nome")]
    print("\n" + "=" * 62)
    print("FASE 3  conferencia por pais")
    print("=" * 62)
    por_pais: dict[str, int] = {}
    for v in ok:
        por_pais[v.get("pais", "")] = por_pais.get(v.get("pais", ""), 0) + 1

    faltas = []
    for d in sorted(paises, key=lambda x: -x["total"]):
        obtido = por_pais.get(d["pais"], 0)
        if obtido < d["total"]:
            faltas.append((d["pais"], d["total"], obtido))
    if faltas:
        print(f"{len(faltas)} paises abaixo do esperado:")
        for pais, esp, obt in faltas[:25]:
            print(f"   {pais[:30]:30} esperado {esp:>4} | obtido {obt:>4}")
    else:
        print("todos os paises bateram ou superaram o esperado")


if __name__ == "__main__":
    inicio = time.time()
    esperar("fila.py", "varredura_paises.py", "maximizar.py")

    paises = resondar_tudo()

    antes = len([v for v in carregar_cache().values() if v.get("nome")])
    print(f"\nperfis ja coletados: {antes}")

    print("\n" + "=" * 62)
    print("FASE 2  coletando o que faltou")
    print("=" * 62)
    executar([f"{BASE}{d['id']}" for d in paises], delay=2.0)

    cache = carregar_cache()
    completo = {k: v for k, v in cache.items() if v.get("nome")}
    salvar_cache(cache)
    conferir(paises)
    cj, cc = exportar_mestre(completo, "esomar_mestre")

    com_email = sum(1 for r in completo.values() if r.get("email"))
    com_site = sum(1 for r in completo.values() if r.get("site"))
    contatos = sum(len(r.get("contatos") or []) for r in completo.values())
    npaises = {r.get("pais") for r in completo.values() if r.get("pais")}

    print("\n" + "=" * 62)
    print("  RESULTADO FINAL")
    print(f"  empresas totais .. {len(completo)}")
    print(f"  novas no reparo .. {len(completo) - antes}")
    print(f"  com email ........ {com_email}")
    print(f"  com site ......... {com_site}")
    print(f"  contatos ......... {contatos}")
    print(f"  paises ........... {len(npaises)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
