"""
Verifica as caixas da base por servico externo.

    uv run python -u validar_com_servico.py [arquivo.csv] [coluna]

Sem VALIDADOR no .env, explica o que falta e nao consome nada.
"""

import collections
import csv
import sys
import time
from dataclasses import asdict
from pathlib import Path

from scraper_lab.validacao_servico import SemChave, provedor_configurado, verificar_lote

S = Path("dados/saida")

if __name__ == "__main__":
    arquivo = sys.argv[1] if len(sys.argv) > 1 else "base_unificada.csv"
    coluna = sys.argv[2] if len(sys.argv) > 2 else "email"

    try:
        nome_prov, _ = provedor_configurado()
    except SemChave as e:
        print(e)
        raise SystemExit(1)

    regs = list(csv.DictReader(open(S / arquivo, encoding="utf-8-sig")))
    emails = sorted({r[coluna].strip().lower() for r in regs if r.get(coluna, "").strip()})
    print(f"{arquivo}: {len(regs)} registros | {len(emails)} e-mails unicos")
    print(f"custo estimado: ~US$ {len(emails)*0.004:.2f} a US$ {len(emails)*0.008:.2f}\n")

    inicio = time.time()
    res = verificar_lote(emails)

    destino = S / f"validacao_servico_{Path(arquivo).stem}.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(res[0]).keys()))
        w.writeheader()
        w.writerows(asdict(x) for x in res)

    c = collections.Counter(x.status for x in res)
    print(f"\n{'='*52}")
    for k in ["valido", "arriscado", "invalido", "indeterminado"]:
        if c.get(k):
            print(f"  {k:14} {c[k]:>5}  ({100*c[k]//len(res)}%)")
    print(f"  {'-'*38}")
    print(f"  catch-all .... {sum(1 for x in res if x.catch_all):>5}")
    print(f"  descartavel .. {sum(1 for x in res if x.descartavel):>5}")
    print(f"  de funcao .... {sum(1 for x in res if x.papel):>5}")
    print(f"  tempo ........ {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV .......... {destino}")
    print(f"{'='*52}")
