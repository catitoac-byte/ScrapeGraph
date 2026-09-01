"""
Enriquece as empresas americanas com e-mail do proprio site.

Nenhuma das fontes dos EUA publica e-mail (a Greenbook proibe o endpoint
no robots.txt, Quirk's nao publica, USAspending nao tem o campo). Em
compensacao 991 delas trazem site, e e de la que o contato sai.

    uv run python -u raspar_enriquecimento_eua.py
"""

import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from scraper_lab.enriquecer import Enriquecido, _emails, enriquecer, usar_navegador

SAIDA = Path("dados/saida")
CACHE = SAIDA.parent / "cache" / "enriquecimento_eua.json"
TRABALHADORES = 12
trava = threading.Lock()


def salvar(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE)


if __name__ == "__main__":
    inicio = time.time()
    usar_navegador(False)

    regs = list(csv.DictReader(open(SAIDA / "base_unificada.csv", encoding="utf-8-sig")))
    alvo = [r for r in regs
            if r["pais"] == "United States" and r["site"] and not r["email"]]
    print(f"[1/2] {len(alvo)} empresas americanas com site e sem e-mail")

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    pendentes = [r for r in alvo if r["nome"] not in cache]
    print(f"      {len(cache)} em cache | {len(pendentes)} a fazer\n")

    feitos = 0

    def tarefa(r):
        try:
            # o site ja e conhecido: passamos como se fosse dominio proprio
            return enriquecer(r["nome"], r["nome"], "",
                              "x@" + r["site"].split("//")[-1].split("/")[0].replace("www.", ""),
                              delay=0.2)
        except Exception as exc:
            return Enriquecido(cnpj=r["nome"], erro=f"{type(exc).__name__}"[:40])

    with ThreadPoolExecutor(max_workers=TRABALHADORES) as ex:
        futuros = {ex.submit(tarefa, r): r for r in pendentes}
        for f in as_completed(futuros):
            r = futuros[f]
            with trava:
                cache[r["nome"]] = asdict(f.result())
                feitos += 1
                if feitos % 100 == 0:
                    cm = sum(1 for v in cache.values() if v["email_comercial"])
                    print(f"      {feitos}/{len(pendentes)} | com e-mail {cm} | "
                          f"{(time.time()-inicio)/60:.0f} min")
                    salvar(cache)
    salvar(cache)

    cm = sum(1 for v in cache.values() if v["email_comercial"])
    print(f"\n{'='*54}")
    print(f"  processadas ....... {len(cache)}")
    print(f"  com e-mail do site  {cm}")
    print(f"  tempo ............. {(time.time()-inicio)/60:.0f} min")
    print(f"{'='*54}")
