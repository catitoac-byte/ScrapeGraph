"""
Enriquece as empresas brasileiras de pesquisa com dados do proprio site.

Duas fases, porque o custo delas e muito diferente:
  1. varredura HTTP em paralelo, ~1s por empresa;
  2. renderizacao com UM navegador compartilhado, so para os sites que a
     fase 1 encontrou mas cujo HTML nao trazia e-mail (tipicamente SPA).

A primeira versao abria um Chromium por site e projetava 28 horas.

    uv run python -u raspar_enriquecimento.py
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from scraper_lab.enriquecer import (
    Enriquecido, _emails, enriquecer, usar_navegador,
)
from scraper_lab.receita import SAIDA

CACHE = SAIDA.parent / "cache" / "enriquecimento.json"
TRABALHADORES = 12
trava = threading.Lock()


def salvar(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE)


def fase_navegador(cache: dict, alvo_por_cnpj: dict) -> int:
    """Um navegador so, reaproveitado para todos os sites sem e-mail."""
    from playwright.sync_api import sync_playwright
    from urllib.parse import urlparse

    pend = [v for v in cache.values() if v["site"] and not v["email_comercial"]]
    if not pend:
        return 0
    print(f"\n[2/2] Renderizando {len(pend)} sites sem e-mail no HTML")
    recuperados = 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        try:
            for i, v in enumerate(pend, 1):
                dominio = urlparse(v["site"]).netloc.replace("www.", "")
                try:
                    pg.goto(v["site"], wait_until="domcontentloaded", timeout=15_000)
                    pg.wait_for_timeout(2500)
                    achados = _emails(pg.content(), dominio)
                except Exception:
                    achados = []
                if achados:
                    v["emails_site"] = achados
                    v["email_comercial"] = achados[0]
                    v["origem_site"] += "+render"
                    recuperados += 1
                if i % 25 == 0:
                    print(f"      {i}/{len(pend)} | recuperados {recuperados}")
                    salvar(cache)
        finally:
            b.close()
    salvar(cache)
    return recuperados


if __name__ == "__main__":
    inicio = time.time()
    usar_navegador(False)   # fase 1 e so HTTP

    est = json.loads((SAIDA / "receita_cnae7320.json").read_text(encoding="utf-8"))
    alvo = [r for r in est if r["situacao"] == "02" and r["cnae_origem"] == "principal"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    pendentes = [r for r in alvo if r["cnpj"] not in cache]
    print(f"[1/2] {len(alvo)} empresas | {len(cache)} em cache | {len(pendentes)} a fazer")
    print(f"      varredura HTTP com {TRABALHADORES} trabalhadores\n")

    feitos = 0

    def tarefa(r):
        try:
            return enriquecer(r["cnpj"], r["razao_social"], r["nome_fantasia"],
                              r["email"], delay=0.2)
        except Exception as exc:
            return Enriquecido(cnpj=r["cnpj"], erro=f"{type(exc).__name__}"[:40])

    with ThreadPoolExecutor(max_workers=TRABALHADORES) as ex:
        futuros = {ex.submit(tarefa, r): r for r in pendentes}
        for f in as_completed(futuros):
            r = futuros[f]
            e = f.result()
            with trava:
                cache[r["cnpj"]] = asdict(e)
                feitos += 1
                if feitos % 100 == 0:
                    com_site = sum(1 for v in cache.values() if v["site"])
                    print(f"      {feitos}/{len(pendentes)} | com site {com_site} | "
                          f"{(time.time()-inicio)/60:.0f} min")
                    salvar(cache)
    salvar(cache)

    rec = fase_navegador(cache, {r["cnpj"]: r for r in alvo})

    com_site = sum(1 for v in cache.values() if v["site"])
    com_mail = sum(1 for v in cache.values() if v["email_comercial"])
    palpite = sum(1 for v in cache.values() if v["origem_site"].startswith("palpite"))
    print(f"\n{'='*58}")
    print(f"  processadas ............ {len(cache)}")
    print(f"  com site ............... {com_site}")
    print(f"    achado por palpite ... {palpite}")
    print(f"  com e-mail do site ..... {com_mail}")
    print(f"    recuperados no render  {rec}")
    print(f"  tempo .................. {(time.time()-inicio)/60:.0f} min")
    print(f"{'='*58}")
