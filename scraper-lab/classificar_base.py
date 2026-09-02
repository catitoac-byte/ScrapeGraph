"""
Consolida internacional e Brasil num arquivo unico, ja classificado.

    uv run python -u classificar_base.py
"""

import collections
import csv
from pathlib import Path

from scraper_lab.classificar import TIERS, alcance, tier, tipo_email

S = Path("dados/saida")

COLUNAS = [
    "tier", "tipo_email", "alcance_email", "mx_ok", "smtp",
    "nome", "email", "site", "pais", "uf", "telefone",
    "decisores", "contatos", "endereco", "fonte", "url_perfil", "restricao_fonte",
]


def carregar_validacoes() -> tuple[dict, dict]:
    mx, smtp = {}, {}
    for arq in ["validacao_internacional.csv", "validacao_brasil.csv"]:
        p = S / arq
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8-sig")):
                mx[r["email"].lower()] = r.get("mx_situacao", "") == "ok"
    for arq in ["validacao_smtp_internacional.csv", "validacao_smtp_brasil.csv"]:
        p = S / arq
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8-sig")):
                smtp[r["email"].lower()] = r["smtp"]
    return mx, smtp


if __name__ == "__main__":
    mx, smtp = carregar_validacoes()
    print(f"validacoes carregadas: {len(mx)} MX | {len(smtp)} SMTP\n")

    linhas = []

    for r in csv.DictReader(open(S / "base_unificada.csv", encoding="utf-8-sig")):
        e = r["email"].strip().lower()
        linhas.append({
            "nome": r["nome"], "email": e, "site": r["site"], "pais": r["pais"],
            "uf": r["uf"], "telefone": r["telefone"], "decisores": "",
            "contatos": r["contatos"], "endereco": r["endereco"],
            "fonte": r["fonte"], "url_perfil": r["url_perfil"],
            "restricao_fonte": r.get("restricao_fonte", ""),
        })

    for r in csv.DictReader(open(S / "brasil_leads_pesquisa.csv", encoding="utf-8-sig")):
        e = r["email_principal"].strip().lower()
        linhas.append({
            "nome": r["razao_social"] or r["nome_fantasia"], "email": e,
            "site": r["site"], "pais": "Brazil", "uf": r["uf"],
            "telefone": r["telefone"], "decisores": r["decisores"],
            "contatos": "", "endereco": r["endereco"],
            "fonte": "receita", "url_perfil": "",
            "restricao_fonte": "robots.txt do dominio declara Disallow: / (dado aberto por lei)",
        })

    # A base internacional ja tem 118 brasileiras vindas de diretorio; o
    # cruzamento por (pais, e-mail) evita contar a mesma empresa duas vezes.
    vistos, unicas = set(), []
    for l in linhas:
        chave = (l["pais"], l["email"]) if l["email"] else ("", l["nome"].lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        unicas.append(l)

    for l in unicas:
        e = l["email"]
        l["tipo_email"] = tipo_email(e)
        l["alcance_email"] = alcance(e)
        l["mx_ok"] = "" if e not in mx else ("sim" if mx[e] else "nao")
        l["smtp"] = smtp.get(e, "")
        l["tier"] = tier(e, mx_ok=mx.get(e))

    unicas.sort(key=lambda x: (x["tier"], x["pais"], x["nome"]))
    destino = S / "base_total_classificada.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(unicas)

    print(f"{'='*58}")
    print(f"  BASE TOTAL: {len(unicas)} empresas | {len(linhas)-len(unicas)} duplicatas removidas")
    print(f"{'='*58}")
    c = collections.Counter(l["tier"] for l in unicas)
    for k in "ABCDE":
        n = c.get(k, 0)
        print(f"  {k}  {TIERS[k]:24} {n:>5}  ({100*n//len(unicas)}%)")
    print(f"  {'-'*50}")
    acionaveis = c.get("A", 0) + c.get("B", 0)
    print(f"  acionaveis (A+B) ................. {acionaveis}")
    print(f"  com decisor nomeado .............. {sum(1 for l in unicas if l['decisores'] or l['contatos'])}")
    print(f"  paises ........................... {len({l['pais'] for l in unicas if l['pais']})}")
    print(f"  CSV .............................. {destino}")
    print(f"{'='*58}")

    print("\n  A+B por pais:")
    ab = [l for l in unicas if l["tier"] in "AB"]
    for p, n in collections.Counter(l["pais"] for l in ab).most_common(8):
        print(f"    {n:>5}  {p}")
