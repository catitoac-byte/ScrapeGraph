"""
Cruza a base de empresas com a rede do usuario no LinkedIn.

Marca, para cada empresa, se ha alguem conhecido la dentro e quem e o
melhor ponto de entrada. Lead com contato interno nao e abordagem fria.

    uv run python -u cruzar_linkedin.py
"""

import csv
import json
from pathlib import Path

from scraper_lab.linkedin_export import Conexao, carregar, indexar, normalizar

SAIDA = Path("dados/saida")
EXPORT = Path("/Users/cassianoalbuquerque/Downloads/"
              "Basic_LinkedInDataExport_08-31-2026.zip/Connections.csv")


def melhor(cs: list[Conexao]) -> Conexao:
    """Decisor da area primeiro, depois decisor, depois quem tiver e-mail."""
    return sorted(cs, key=lambda c: (
        not (c.decisor and c.da_area), not c.decisor, not c.email, c.nome_completo
    ))[0]


def cruzar(regs: list[dict], campo_nome: str, idx: dict, rotulo: str) -> list[dict]:
    saida, casadas = [], 0
    for r in regs:
        chave = normalizar(r.get(campo_nome, ""))
        cs = idx.get(chave, []) if len(chave) >= 5 else []
        linha = dict(r)
        if cs:
            casadas += 1
            b = melhor(cs)
            linha.update({
                "li_contatos": len(cs),
                "li_melhor_contato": b.nome_completo,
                "li_cargo": b.cargo,
                "li_url": b.url,
                "li_email": b.email,
                "li_decisor": b.decisor,
                "li_outros": " | ".join(
                    f"{c.nome_completo} ({c.cargo[:34]})" for c in cs[:5] if c is not b),
            })
        else:
            linha.update({"li_contatos": 0, "li_melhor_contato": "", "li_cargo": "",
                          "li_url": "", "li_email": "", "li_decisor": False,
                          "li_outros": ""})
        saida.append(linha)
    print(f"  {rotulo}: {casadas}/{len(regs)} empresas com contato na rede")
    return saida


if __name__ == "__main__":
    conexoes = carregar(EXPORT)
    idx = indexar(conexoes)
    print(f"rede: {len(conexoes)} conexoes | {len(idx)} empresas\n")

    for arquivo, campo, nome_saida, rotulo in [
        ("base_unificada.csv", "nome", "base_unificada_linkedin.csv", "internacional"),
        ("brasil_leads_pesquisa.csv", "razao_social", "brasil_leads_linkedin.csv", "brasil"),
    ]:
        regs = list(csv.DictReader(open(SAIDA / arquivo, encoding="utf-8-sig")))
        # no Brasil o nome fantasia costuma casar melhor que a razao social
        if rotulo == "brasil":
            for r in regs:
                if r.get("nome_fantasia"):
                    r["_alt"] = r["nome_fantasia"]
        cruzado = cruzar(regs, campo, idx, rotulo)
        if rotulo == "brasil":
            recuperadas = 0
            for linha, r in zip(cruzado, regs):
                if not linha["li_contatos"] and r.get("nome_fantasia"):
                    cs = idx.get(normalizar(r["nome_fantasia"]), [])
                    if cs:
                        b = melhor(cs)
                        linha.update({"li_contatos": len(cs),
                                      "li_melhor_contato": b.nome_completo,
                                      "li_cargo": b.cargo, "li_url": b.url,
                                      "li_email": b.email, "li_decisor": b.decisor})
                        recuperadas += 1
            if recuperadas:
                print(f"     +{recuperadas} pelo nome fantasia")

        destino = SAIDA / nome_saida
        with destino.open("w", newline="", encoding="utf-8-sig") as fh:
            campos = [c for c in cruzado[0] if not c.startswith("_")]
            w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
            w.writeheader(); w.writerows(cruzado)
        com = sum(1 for l in cruzado if l["li_contatos"])
        dec = sum(1 for l in cruzado if l["li_decisor"])
        print(f"     -> {destino.name}: {com} com contato, {dec} com decisor\n")

    # a rede sozinha tambem e um ativo: decisores da area de pesquisa
    alvo = [c for c in conexoes if c.decisor and c.da_area]
    d = SAIDA / "linkedin_decisores_pesquisa.csv"
    with d.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["nome", "cargo", "empresa", "email", "url", "conectado_em"])
        for c in sorted(alvo, key=lambda x: x.empresa):
            w.writerow([c.nome_completo, c.cargo, c.empresa, c.email, c.url, c.conectado_em])
    print(f"  decisores de pesquisa na rede: {len(alvo)} -> {d.name}")
