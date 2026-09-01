"""
Busca os socios das empresas de pesquisa de mercado no CNPJ da Receita.

Foco nas ATIVAS com CNAE 7320-3/00 como atividade principal, que sao as
empresas de pesquisa de fato, e nao as que apenas registraram o codigo
como atividade secundaria.

    uv run python -u raspar_socios.py
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

from scraper_lab.receita import (
    SAIDA, TEMP, Socio, baixar, filtrar_socios,
)

MES = "2026-08"
PARCIAIS = SAIDA.parent / "cache" / "receita"

if __name__ == "__main__":
    inicio = time.time()
    PARCIAIS.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)

    est = json.loads((SAIDA / "receita_cnae7320.json").read_text(encoding="utf-8"))
    alvo = [r for r in est if r["situacao"] == "02" and r["cnae_origem"] == "principal"]
    bases = {r["cnpj_basico"] for r in alvo}
    print(f"[1/2] Alvo: {len(alvo)} estabelecimentos ativos com CNAE principal")
    print(f"      {len(bases)} CNPJ base\n")

    todos: list[Socio] = []
    for i in range(10):
        nome = f"Socios{i}"
        p = PARCIAIS / f"{nome}.json"
        if p.exists():
            regs = [Socio(**r) for r in json.loads(p.read_text(encoding="utf-8"))]
            todos += regs
            print(f"   {nome}: {len(regs)} (cache)")
            continue
        zp = TEMP / f"{nome}.zip"
        try:
            baixar(MES, f"{nome}.zip", zp)
            regs = filtrar_socios(zp, bases)
            p.write_text(json.dumps([asdict(r) for r in regs], ensure_ascii=False),
                         encoding="utf-8")
            todos += regs
            print(f"   {nome}: {len(regs)} socios | acumulado {len(todos)}")
        except Exception as exc:
            print(f"   {nome}: FALHOU {type(exc).__name__}: {str(exc)[:60]}")
        finally:
            zp.unlink(missing_ok=True)

    print(f"\n[2/2] Cruzando com as empresas")
    por_base: dict[str, list[Socio]] = {}
    for s in todos:
        por_base.setdefault(s.cnpj_basico, []).append(s)

    import csv
    linhas = []
    for r in alvo:
        socios = por_base.get(r["cnpj_basico"], [])
        decisores = [s for s in socios if s.decisor and s.tipo == "fisica"]
        outros = [s for s in socios if not s.decisor and s.tipo == "fisica"]
        linhas.append({
            "razao_social": r["razao_social"],
            "nome_fantasia": r["nome_fantasia"],
            "cnpj": r["cnpj"],
            "email": r["email"],
            "telefone": r["telefone"],
            "uf": r["uf"],
            "municipio": r["municipio"],
            "porte": r["porte"],
            "inicio_atividade": r["inicio_atividade"],
            "decisores": " | ".join(f"{s.nome} ({s.qualificacao})" for s in decisores),
            "qtd_decisores": len(decisores),
            "outros_socios": " | ".join(f"{s.nome} ({s.qualificacao})" for s in outros),
            "qtd_socios": len(socios),
            "endereco": r["endereco"],
            "cep": r["cep"],
        })

    cc = SAIDA / "brasil_pesquisa_socios.csv"
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    (SAIDA / "brasil_pesquisa_socios.json").write_text(
        json.dumps(linhas, ensure_ascii=False, indent=1), encoding="utf-8")

    com_dec = sum(1 for l in linhas if l["qtd_decisores"])
    print(f"\n{'='*58}")
    print(f"  empresas ............... {len(linhas)}")
    print(f"  com ao menos 1 decisor . {com_dec}")
    print(f"  socios mapeados ........ {len(todos)}")
    print(f"  com email .............. {sum(1 for l in linhas if l['email'])}")
    print(f"  com telefone ........... {sum(1 for l in linhas if l['telefone'])}")
    print(f"  tempo .................. {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV .................... {cc}")
    print(f"{'='*58}")
