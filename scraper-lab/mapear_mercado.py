"""
Mapa do mercado de uma vertical no Google Maps, antes de escolher as marcas.

    uv run python mapear_mercado.py --vertical imobiliarias
    uv run python mapear_mercado.py --vertical imobiliarias --top 40
    uv run python mapear_mercado.py --vertical imobiliarias --completar

Le o bloco "mercado" de verticais/<id>.json: consultas por bairro com
{cidade}, a expressao das categorias que contam e a caixa de coordenadas da
cidade. So le os cartoes da lista de resultados (nome, nota, total de
avaliacoes, categoria, telefone), sem abrir fichas, entao nao gasta o limite
de avaliacoes do Google e pode rodar sem janela.

Saida em dados/saida/lojas_google/<saida>_mercado.json e .csv, com uma
coluna "na_cidade" pela caixa de coordenadas. A confirmacao pelo CEP fica
para a coleta das fichas, como nas outras verticais.
"""

import argparse
import csv
import json
import re
from dataclasses import asdict
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.lojas_google import SAIDA, Negocio, _sem_acento, abrir_navegador, mapear

VERTICAIS = Path(__file__).resolve().parent / "verticais"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", required=True)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--top", type=int, default=30, help="quantos mostrar no ranking")
    ap.add_argument("--janela", action="store_true", help="abre o Chromium visivel")
    ap.add_argument("--so-ranking", action="store_true", help="nao busca, so reimprime o ranking salvo")
    ap.add_argument("--completar", action="store_true",
                    help="refaz as consultas que deixaram negocio sem nota ou total de avaliacoes")
    args = ap.parse_args()

    cfg = json.loads((VERTICAIS / f"{args.vertical}.json").read_text(encoding="utf-8"))
    merc = cfg["mercado"]
    cidade = cfg["cidade"]
    json_saida = SAIDA / f"{cfg['saida']}_mercado.json"
    SAIDA.mkdir(parents=True, exist_ok=True)

    achados: dict[str, Negocio] = {}
    if json_saida.exists():
        # Retoma: consultas ja feitas nao rodam de novo
        for d in json.loads(json_saida.read_text(encoding="utf-8")):
            d.pop("na_cidade", None)
            d.pop("conta", None)
            achados[d["place_id"]] = Negocio(**d)
    feitas = {q for n in achados.values() for q in n.consultas}
    consultas = [c.format(cidade=cidade) for c in merc["consultas"]]
    faltam = [q for q in consultas if q not in feitas]
    if args.completar:
        vazias = {q for n in achados.values() if n.total_avaliacoes is None for q in n.consultas}
        faltam += [q for q in consultas if q in vazias]

    if faltam and not args.so_ranking:
        print(f"{len(faltam)} consultas a fazer, {len(consultas) - len(faltam)} ja feitas")
        with sync_playwright() as pw:
            browser, page = abrir_navegador(pw, headless=not args.janela)
            try:
                # Grava a cada consulta para uma parada no meio nao perder nada
                for q in faltam:
                    mapear(page, [q], args.delay, achados)
                    gravar(json_saida, achados, merc)
            finally:
                browser.close()

    linhas = gravar(json_saida, achados, merc)
    contam = [l for l in linhas if l["conta"] and l["na_cidade"]]
    print(f"\n{len(linhas)} negocios encontrados, {len(contam)} da categoria e dentro da cidade")
    print(f"{'#':>3} {'avaliacoes':>10} {'nota':>4}  {'categoria':<32} nome")
    for i, l in enumerate(sorted(contam, key=lambda x: -(x["total_avaliacoes"] or 0))[:args.top], 1):
        print(f"{i:>3} {l['total_avaliacoes'] or 0:>10} {l['nota'] or '':>4}  {l['categoria'][:32]:<32} {l['nome'][:70]}")
    print(f"\n{json_saida}")


def gravar(caminho: Path, achados: dict[str, Negocio], merc: dict) -> list[dict]:
    cat = re.compile(merc["categorias"])
    lat0, lat1, lng0, lng1 = merc["caixa"]
    linhas = []
    for n in achados.values():
        d = asdict(n)
        d["conta"] = bool(cat.search(_sem_acento(n.categoria)))
        d["na_cidade"] = (n.latitude is not None and lat0 <= n.latitude <= lat1
                          and lng0 <= n.longitude <= lng1)
        linhas.append(d)
    linhas.sort(key=lambda x: -(x["total_avaliacoes"] or 0))
    caminho.write_text(json.dumps(linhas, ensure_ascii=False, indent=1), encoding="utf-8")
    with caminho.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()) if linhas else ["nome"])
        w.writeheader()
        for l in linhas:
            w.writerow({**l, "consultas": " | ".join(l["consultas"])})
    return linhas


if __name__ == "__main__":
    main()
