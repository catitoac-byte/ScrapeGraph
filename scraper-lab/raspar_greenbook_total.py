"""Coleta o diretorio inteiro da Greenbook a partir do sitemap, com retomada."""

import json
import time
from pathlib import Path

from dataclasses import asdict
from scraper_lab.greenbook import (
    Empresa, SAIDA, _baixar, exportar, extrair_empresa, listar_do_sitemap,
)

CACHE = SAIDA.parent / "cache" / "greenbook.json"

if __name__ == "__main__":
    inicio = time.time()
    print("[1/3] Lendo o sitemap")
    urls = listar_do_sitemap()
    print(f"      {len(urls)} empresas permitidas pelo robots.txt\n")

    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"      cache: {len(cache)} ja coletadas\n")
    # aproveita a coleta anterior da categoria full-service
    anterior = SAIDA / "greenbook.json"
    if anterior.exists():
        for r in json.loads(anterior.read_text(encoding="utf-8")):
            if r.get("nome"):
                cache.setdefault(r["url_perfil"], r)

    pendentes = [u for u in urls if u not in cache]
    print(f"[2/3] Coletando {len(pendentes)} novas (de {len(urls)})")
    for i, u in enumerate(pendentes, 1):
        try:
            e = extrair_empresa(_baixar(u), u)
        except Exception as exc:
            e = Empresa(url_perfil=u, erro=f"{type(exc).__name__}"[:60])
        cache[u] = asdict(e)
        print(f"  [{i:>4}/{len(pendentes)}] {'!' if e.erro else '.'} "
              f"{e.nome[:32]:32} | {e.pais[:16]:16} | {e.telefone[:16]}")
        if i % 25 == 0:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(1.2)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    print("\n[3/3] Exportando")
    empresas = [Empresa(**{k: v for k, v in r.items() if k in Empresa.__annotations__})
                for r in cache.values()]
    cj, cc = exportar(empresas, "greenbook")
    ok = [e for e in empresas if e.nome]
    import collections
    br = [e for e in ok if e.pais == "Brazil"]
    print(f"\n{'='*58}")
    print(f"  empresas ......... {len(ok)}")
    print(f"  brasileiras ...... {len(br)}")
    print(f"  paises ........... {len({e.pais for e in ok if e.pais})}")
    print(f"  com site ......... {sum(1 for e in ok if e.site)}")
    print(f"  com telefone ..... {sum(1 for e in ok if e.telefone)}")
    print(f"  erros ............ {sum(1 for e in empresas if e.erro)}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  CSV .............. {cc}")
    print(f"{'='*58}")
