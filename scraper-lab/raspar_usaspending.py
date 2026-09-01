"""Varredura dos fornecedores federais com NAICS 541910 (pesquisa de mercado)."""

import json
import time
from dataclasses import asdict
from pathlib import Path

from scraper_lab.usaspending import (
    Fornecedor, detalhar, exportar, listar_fornecedores,
)

CACHE = Path("dados/cache/usaspending.json")

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Listando destinatarios (NAICS 541910)")
    fs = listar_fornecedores()
    print(f"      {len(fs)} fornecedores\n")

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    print(f"[2/3] Detalhando ({len(cache)} em cache)")
    for i, f in enumerate(fs, 1):
        if f.recipient_id in cache:
            for k, v in cache[f.recipient_id].items():
                setattr(f, k, v)
            continue
        detalhar(f)
        cache[f.recipient_id] = asdict(f)
        if i % 50 == 0:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"      {i}/{len(fs)} | {(time.time()-inicio)/60:.0f} min")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    print("\n[3/3] Exportando")
    cj, cc = exportar(fs)
    eua = [f for f in fs if f.estado]
    print(f"\n{'='*58}")
    print(f"  fornecedores ..... {len(fs)}")
    print(f"  com endereco ..... {sum(1 for f in fs if f.endereco)}")
    print(f"  estados .......... {len({f.estado for f in eua})}")
    print(f"  pequeno porte .... {sum(1 for f in fs if 'small_business' in f.tipos_negocio)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV .............. {cc}")
    print(f"{'='*58}")
