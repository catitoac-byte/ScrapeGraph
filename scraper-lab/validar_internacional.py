"""
Valida os e-mails da base internacional, nas mesmas camadas usadas no Brasil.

    uv run python -u validar_internacional.py
"""

import collections
import csv
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from scraper_lab.validar_email import validar

S = Path("dados/saida")

if __name__ == "__main__":
    inicio = time.time()
    base = list(csv.DictReader(open(S / "base_unificada.csv", encoding="utf-8-sig")))
    por_email: dict[str, dict] = {}
    for r in base:
        e = r["email"].strip().lower()
        if e:
            por_email.setdefault(e, r)
    emails = sorted(por_email)
    print(f"{len(emails)} e-mails unicos | camadas: sintaxe + MX + classificacao\n")

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(validar, emails))

    destino = S / "validacao_internacional.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        campos = list(asdict(res[0]).keys()) + ["empresa", "pais"]
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        for x in res:
            d = asdict(x)
            r = por_email[x.email]
            d["empresa"], d["pais"] = r["nome"], r["pais"]
            w.writerow(d)

    v = collections.Counter(x.veredito for x in res)
    print(f"{'='*54}")
    for k in ["provavel", "indeterminado", "invalido"]:
        if v.get(k):
            print(f"  {k:14} {v[k]:>5}  ({100*v[k]//len(res)}%)")
    print(f"  {'-'*40}")
    print(f"  sem MX ....... {sum(1 for x in res if x.mx_situacao == 'sem_mx'):>5}")
    print(f"  gratuito ..... {sum(1 for x in res if x.gratuito):>5}")
    print(f"  de funcao .... {sum(1 for x in res if x.papel):>5}")
    print(f"  tempo ........ {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV .......... {destino}")
    print(f"{'='*54}")

    ruins = [x for x in res if x.veredito == "invalido"]
    if ruins:
        print("\n  invalidos por pais:")
        c = collections.Counter(por_email[x.email]["pais"] for x in ruins)
        for p, n in c.most_common(8):
            print(f"    {n:>4}  {p}")
