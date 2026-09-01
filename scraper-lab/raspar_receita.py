"""
Extrai do CNPJ da Receita todas as empresas com CNAE 7320-3/00.

Processa um zip por vez: baixa, filtra, apaga. Retomavel: cada arquivo
concluido grava seu resultado parcial, entao uma queda nao repete o que
ja foi feito.

    uv run python -u raspar_receita.py
"""

import json
import time
from dataclasses import asdict
from pathlib import Path

from scraper_lab.receita import (
    SAIDA, TEMP, Estabelecimento, baixar, completar_empresas,
    filtrar_estabelecimentos,
)

MES = "2026-08"
PARCIAIS = SAIDA.parent / "cache" / "receita"


def parcial(nome: str) -> Path:
    return PARCIAIS / f"{nome}.json"


if __name__ == "__main__":
    inicio = time.time()
    PARCIAIS.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] Estabelecimentos com CNAE 7320300 ({MES})")
    todos: list[Estabelecimento] = []
    for i in range(10):
        nome = f"Estabelecimentos{i}"
        p = parcial(nome)
        if p.exists():
            regs = [Estabelecimento(**r) for r in json.loads(p.read_text(encoding="utf-8"))]
            todos += regs
            print(f"   {nome}: {len(regs)} (do cache)")
            continue
        zp = TEMP / f"{nome}.zip"
        try:
            baixar(MES, f"{nome}.zip", zp)
            regs = filtrar_estabelecimentos(zp)
            p.write_text(json.dumps([asdict(r) for r in regs], ensure_ascii=False),
                         encoding="utf-8")
            todos += regs
            print(f"   {nome}: {len(regs)} encontrados | acumulado {len(todos)}")
        except Exception as exc:
            print(f"   {nome}: FALHOU {type(exc).__name__}: {str(exc)[:60]}")
        finally:
            zp.unlink(missing_ok=True)

    print(f"\n      total de estabelecimentos: {len(todos)}")

    print(f"\n[2/3] Razao social e porte (arquivos Empresas)")
    por_base: dict[str, list[Estabelecimento]] = {}
    for e in todos:
        por_base.setdefault(e.cnpj_basico, []).append(e)
    print(f"      {len(por_base)} CNPJ base a resolver")

    for i in range(10):
        nome = f"Empresas{i}"
        marca = parcial(f"{nome}.done")
        if marca.exists():
            print(f"   {nome}: ja processado")
            continue
        zp = TEMP / f"{nome}.zip"
        try:
            baixar(MES, f"{nome}.zip", zp)
            n = completar_empresas(zp, por_base)
            marca.write_text("ok", encoding="utf-8")
            resolvidos = sum(1 for e in todos if e.razao_social)
            print(f"   {nome}: +{n} bases | com razao social: {resolvidos}/{len(todos)}")
        except Exception as exc:
            print(f"   {nome}: FALHOU {type(exc).__name__}: {str(exc)[:60]}")
        finally:
            zp.unlink(missing_ok=True)

    print("\n[3/3] Exportando")
    import csv
    SAIDA.mkdir(parents=True, exist_ok=True)
    colunas = list(asdict(todos[0]).keys()) if todos else []
    cj = SAIDA / "receita_cnae7320.json"
    cc = SAIDA / "receita_cnae7320.csv"
    cj.write_text(json.dumps([asdict(e) for e in todos], ensure_ascii=False, indent=1),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=colunas)
        w.writeheader()
        for e in todos:
            w.writerow(asdict(e))

    ativas = [e for e in todos if e.situacao == "02"]
    princ = [e for e in ativas if e.cnae_origem == "principal"]
    com_email = [e for e in princ if e.email]
    print(f"\n{'='*60}")
    print(f"  estabelecimentos ....... {len(todos)}")
    print(f"  ativos ................. {len(ativas)}")
    print(f"  ativos, CNAE principal . {len(princ)}")
    print(f"  destes, com e-mail ..... {len(com_email)}")
    print(f"  UFs .................... {len({e.uf for e in ativas if e.uf})}")
    print(f"  tempo .................. {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV .................... {cc}")
    print(f"{'='*60}")
