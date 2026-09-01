"""
Valida os e-mails da base. Camadas 1 a 3 por padrao (DNS puro, sem tocar
em servidor de correio). Passe --smtp para a sondagem opcional.

    uv run python -u validar_base.py [--smtp] [arquivo.json]
"""

import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from scraper_lab.validar_email import validar

SAIDA = Path("dados/saida")


def rodar(arquivo: str, campo: str, com_smtp: bool, nome_saida: str) -> None:
    regs = json.loads((SAIDA / arquivo).read_text(encoding="utf-8"))
    emails = sorted({(r.get(campo) or "").strip().lower() for r in regs if r.get(campo)})
    print(f"{arquivo}: {len(regs)} registros | {len(emails)} e-mails unicos")
    print(f"camadas: sintaxe + MX + classificacao" + (" + SMTP" if com_smtp else ""))

    with ThreadPoolExecutor(max_workers=8) as ex:
        resultados = list(ex.map(lambda e: validar(e, smtp=com_smtp), emails))
    por_email = {r.email: r for r in resultados}

    destino = SAIDA / nome_saida
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(resultados[0]).keys()))
        w.writeheader()
        for r in resultados:
            w.writerow(asdict(r))

    import collections
    v = collections.Counter(r.veredito for r in resultados)
    print(f"\n{'='*54}")
    for k in ["valido", "provavel", "indeterminado", "invalido"]:
        if v.get(k):
            print(f"  {k:12} {v[k]:>6}  ({100*v[k]//len(resultados)}%)")
    print(f"  {'-'*40}")
    print(f"  sem MX ..... {sum(1 for r in resultados if not r.tem_mx):>6}")
    print(f"  gratuito ... {sum(1 for r in resultados if r.gratuito):>6}")
    print(f"  de funcao .. {sum(1 for r in resultados if r.papel):>6}")
    print(f"  descartavel  {sum(1 for r in resultados if r.descartavel):>6}")
    print(f"  CSV: {destino}")
    print(f"{'='*54}")

    motivos = collections.Counter(r.motivo for r in resultados if r.veredito == "invalido")
    if motivos:
        print("\n  invalidos por motivo:")
        for m, n in motivos.most_common(6):
            print(f"    {n:>5}  {m}")
    return por_email


if __name__ == "__main__":
    smtp = "--smtp" in sys.argv
    rodar("brasil_leads_pesquisa.json", "email_principal", smtp,
          "validacao_brasil.csv")
