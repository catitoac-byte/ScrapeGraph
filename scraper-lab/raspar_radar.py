"""
Coleta do radar de mercado (sem LLM). Tres comandos:

    uv run --no-sync python raspar_radar.py coletar --config radar.config.json --categoria synthetic \
        --janela 90 --saida dados/saida/radar [--teto-paginas 40] [--teto-buscas 20] [--dry-run]
    uv run --no-sync python raspar_radar.py conferir sinais.json
    uv run --no-sync python raspar_radar.py feeds --config radar.config.json [--atualizar]
    uv run --no-sync python raspar_radar.py registrar-buscas buscas.json

Saida de coletar: <saida>/candidatos-<categoria>.json. conferir grava <arquivo>.conferencia.json
e sai com codigo 1 se alguma citacao nao estiver literalmente na pagina.
"""

import argparse
import json
import sys
from pathlib import Path

from scraper_lab import radar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta do radar de mercado")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("coletar")
    c.add_argument("--config", required=True, type=Path)
    c.add_argument("--categoria", required=True)
    c.add_argument("--janela", required=True, type=int, help="dias")
    c.add_argument("--saida", required=True, type=Path)
    c.add_argument("--teto-paginas", type=int, default=radar.TETO_PAGINAS_PADRAO)
    c.add_argument("--teto-buscas", type=int, default=radar.TETO_BUSCAS_PADRAO)
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--navegador", action="store_true", help="renderiza com Chromium paginas que respondem 200 quase vazias")

    f = sub.add_parser("conferir")
    f.add_argument("arquivo", type=Path)
    f.add_argument("--navegador", action="store_true")

    d = sub.add_parser("feeds")
    d.add_argument("--config", required=True, type=Path)
    d.add_argument("--janela", type=int, default=90)
    d.add_argument("--atualizar", action="store_true", help="grava o status de cada fonte de volta no config")

    r = sub.add_parser("registrar-buscas")
    r.add_argument("arquivo", type=Path, help="lista de {categoria, consulta, idioma, resultados:[{url,titulo}]}")

    a = ap.parse_args(argv)

    if a.cmd == "coletar":
        doc = radar.coletar(a.config, a.categoria, a.janela, a.saida, teto_paginas=a.teto_paginas,
                            teto_buscas=a.teto_buscas, dry_run=a.dry_run, navegador=a.navegador)
        m = doc["meta"]
        print(f"\nfontes lidas {m['fontes_lidas']} | itens na janela {m['itens_na_janela']} | itens de feed {m['itens_de_feed']} | "
              f"com vocabulário {m['itens_com_vocabulario']} | páginas abertas {m['paginas_abertas']} (cache {m['paginas_do_cache']}) | "
              f"candidatos {len(doc['candidatos'])} | consultas usadas {m['consultas_usadas']} | bloqueados {len(m['bloqueados'])}")
        if not a.dry_run:
            print(f"-> {a.saida / ('candidatos-' + a.categoria + '.json')}")
        return 0

    if a.cmd == "conferir":
        res = radar.conferir(a.arquivo, navegador=a.navegador)
        for v in res["violacoes"]:
            print(f"VIOLAÇÃO sinal {v['sinal']} evidência {v['evidencia']}: {v['motivo']} | {v['url']} | {str(v['valor'])[:100]}")
        print(f"{res['evidencias_verificadas']} evidências verificadas, {len(res['violacoes'])} violações -> {a.arquivo}.conferencia.json")
        return 0 if res["ok"] else 1

    if a.cmd == "feeds":
        linhas = radar.checar_fontes(a.config, janela_dias=a.janela, atualizar=a.atualizar)
        vivos = sum(1 for l in linhas if l["estado"] == "vivo")
        print(f"\n{vivos}/{len(linhas)} fontes vivas")
        return 0

    if a.cmd == "registrar-buscas":
        n = radar.registrar_buscas(radar.CACHE_RADAR, json.loads(a.arquivo.read_text(encoding="utf-8")))
        print(f"{n} buscas registradas")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
