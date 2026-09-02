"""
Enriquece por site TODA empresa da base sem e-mail, em qualquer pais.

Substitui os dois runners anteriores (Brasil e EUA), que repetiam a mesma
logica com filtro de pais diferente. A chave do cache e o DOMINIO do site,
nao o nome: nome de empresa colide entre paises e ja me fez atribuir o
mesmo e-mail a empresas distintas.

    uv run python -u raspar_enriquecimento_global.py
"""

import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from scraper_lab.enriquecer import Enriquecido, enriquecer, usar_navegador

S = Path("dados/saida")
CACHE = S.parent / "cache" / "enriquecimento_global.json"
TRABALHADORES = 12
trava = threading.Lock()


def dominio(url: str) -> str:
    u = url if url.startswith("http") else "https://" + url
    return urlparse(u).netloc.replace("www.", "").lower()


def salvar(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE)


if __name__ == "__main__":
    inicio = time.time()
    usar_navegador(False)   # fase HTTP; SPA fica para uma segunda passada

    regs = list(csv.DictReader(open(S / "base_total_classificada.csv",
                                    encoding="utf-8-sig")))
    # Um dominio por empresa: varias linhas podem apontar para o mesmo site.
    alvos: dict[str, dict] = {}
    for r in regs:
        if r["email"] or not r["site"]:
            continue
        d = dominio(r["site"])
        if d:
            alvos.setdefault(d, r)
    print(f"[1/1] {len(alvos)} dominios sem e-mail a visitar")

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    pendentes = [(d, r) for d, r in alvos.items() if d not in cache]
    print(f"      {len(cache)} em cache | {len(pendentes)} a fazer\n")

    feitos = 0

    def tarefa(par):
        d, r = par
        try:
            return d, enriquecer(d, r["nome"], "", "x@" + d, delay=0.2)
        except Exception as exc:
            return d, Enriquecido(cnpj=d, erro=f"{type(exc).__name__}"[:40])

    with ThreadPoolExecutor(max_workers=TRABALHADORES) as ex:
        for f in as_completed([ex.submit(tarefa, p) for p in pendentes]):
            d, e = f.result()
            with trava:
                cache[d] = asdict(e)
                feitos += 1
                if feitos % 100 == 0:
                    cm = sum(1 for v in cache.values() if v["email_comercial"])
                    print(f"      {feitos}/{len(pendentes)} | com e-mail {cm} | "
                          f"{(time.time()-inicio)/60:.0f} min")
                    salvar(cache)
    salvar(cache)

    cm = sum(1 for v in cache.values() if v["email_comercial"])
    print(f"\n{'='*52}")
    print(f"  dominios visitados . {len(cache)}")
    print(f"  com e-mail ......... {cm}  ({100*cm//max(len(cache),1)}%)")
    print(f"  tempo .............. {(time.time()-inicio)/60:.0f} min")
    print(f"{'='*52}")
