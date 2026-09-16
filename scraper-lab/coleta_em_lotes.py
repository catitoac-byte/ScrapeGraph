"""
Coleta em lotes pequenos, retomavel, para respeitar o limite do Google.

    uv run python coleta_em_lotes.py --vertical supermercados --tamanho 4
    uv run python coleta_em_lotes.py --vertical supermercados --tamanho 4 --publicar
    uv run python coleta_em_lotes.py --vertical supermercados --status

Cada execucao faz UM lote: na primeira, descobre as lojas de todas as marcas;
nas seguintes, abre as proximas N fichas ainda nao coletadas. O estado fica em
dados/saida/lojas_google/<saida>_estado.json. Se o Google entrar em
visualizacao limitada, o lote para sem forcar e a loja volta para a fila.

Ao fim de cada lote o JSON e a planilha da vertical sao regravados com tudo
que ja foi coletado. Com --publicar, o painel e o site sao montados e o deploy
de producao roda na Vercel.

Codigos de saida: 0 lote feito, 3 fila vazia (coleta completa), 2 limite do Google.
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.lojas_google import (
    SAIDA, Avaliacao, Loja, _sem_acento, abrir_navegador, acesso_liberado,
    descobrir, exportar, raspar_loja,
)

LAB = Path(__file__).resolve().parent
VERTICAIS = LAB / "verticais"


def carregar(caminho: Path) -> dict:
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {"fila": [], "feitas": {}, "fora": [], "descoberta": None, "lotes": []}


def salvar(caminho: Path, estado: dict) -> None:
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    tmp.replace(caminho)


def para_loja(d: dict) -> Loja:
    d = dict(d)
    av = [Avaliacao(**a) for a in d.pop("avaliacoes", [])]
    return Loja(**d, avaliacoes=av)


def completa(d: dict) -> bool:
    return not d.get("erro")


def status(cfg: dict, estado: dict) -> None:
    feitas = estado["feitas"]
    print(f"vertical ........ {cfg['id']}  ({cfg['cidade']})")
    print(f"descoberta ...... {estado['descoberta'] or 'ainda nao'}")
    print(f"na fila ......... {len(estado['fila'])}")
    print(f"completas ....... {sum(1 for d in feitas.values() if completa(d))}")
    print(f"parciais ........ {sum(1 for d in feitas.values() if not completa(d))}")
    print(f"fora da cidade .. {len(estado['fora'])}")
    for m in cfg["marcas"]:
        n = [d for d in feitas.values() if d["marca"] == m["nome"]]
        f = sum(1 for x in estado["fila"] if x["marca"] == m["nome"])
        print(f"  {m['nome']:<16} coletadas={len(n):>3}  na fila={f:>3}  avaliacoes={sum(len(d['avaliacoes']) for d in n):>5}")
    for l in estado["lotes"][-5:]:
        print(f"  lote {l['quando'][:16]}  {l['resultado']}")


def publicar(cfg: dict) -> None:
    py = [sys.executable]
    subprocess.run(py + [str(LAB / "painel" / "gerar_dados.py"), cfg["id"]], check=True)
    subprocess.run(py + [str(LAB / "vitrine-web" / "gerar_site.py"), cfg["id"]], check=True)
    subprocess.run(["vercel", "deploy", "--prod", "--yes", "--scope", "cassiai"],
                   cwd=LAB / "sites" / cfg["id"], check=True, stdout=subprocess.DEVNULL)
    print(f"publicado: https://{cfg['site']['dominio']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", required=True)
    ap.add_argument("--tamanho", type=int, default=4, help="fichas por lote")
    ap.add_argument("--max-avaliacoes", type=int, default=300)
    ap.add_argument("--delay", type=float, default=6.0)
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--busca-completa", action="store_true",
                    help="usa todas as consultas da vertical; o padrao e so a primeira, para gastar menos acesso")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    cfg = json.loads((VERTICAIS / f"{args.vertical}.json").read_text(encoding="utf-8"))
    caminho = SAIDA / f"{cfg['saida']}_estado.json"
    SAIDA.mkdir(parents=True, exist_ok=True)
    estado = carregar(caminho)
    if args.status:
        status(cfg, estado)
        return 0

    alvo = _sem_acento(cfg["cidade"].split(",")[0].strip())
    resultado, codigo, novas = "", 0, 0
    with sync_playwright() as pw:
        browser, page = abrir_navegador(pw)
        try:
            if not estado["descoberta"]:
                # Lote zero: so descobre as lojas de todas as marcas
                conhecidas = set()
                for m in cfg["marcas"]:
                    consultas = [c.format(cidade=cfg["cidade"]) for c in m["consultas"]]
                    if not args.busca_completa:
                        consultas = consultas[:1]
                    for url in descobrir(page, m["nome"], m["padrao"], consultas, args.delay):
                        if url not in conhecidas:
                            conhecidas.add(url)
                            estado["fila"].append({"marca": m["nome"], "url": url})
                    print(f"[{m['nome']}] {sum(1 for x in estado['fila'] if x['marca'] == m['nome'])} fichas")
                estado["descoberta"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                resultado = f"descoberta: {len(estado['fila'])} fichas na fila"
            elif not estado["fila"]:
                resultado, codigo = "fila vazia, coleta completa", 3
            elif not acesso_liberado(page, estado["fila"][0]["url"]):
                resultado, codigo = "Google limitado antes do lote, nada foi aberto", 2
            else:
                for _ in range(min(args.tamanho, len(estado["fila"]))):
                    item = estado["fila"].pop(0)
                    loja = raspar_loja(page, item["marca"], item["url"], args.max_avaliacoes, cidade_alvo=alvo)
                    if loja.cidade and _sem_acento(loja.cidade) != alvo:
                        estado["fora"].append({**item, "cidade": loja.cidade})
                        print(f"   fora da cidade: {loja.nome} ({loja.cidade})")
                    elif loja.erro.startswith("visualizacao limitada"):
                        # Volta para o fim da fila, mas guarda o que veio da ficha
                        estado["fila"].append(item)
                        anterior = estado["feitas"].get(loja.place_id)
                        if not anterior or not completa(anterior):
                            estado["feitas"][loja.place_id] = asdict(loja)
                        resultado, codigo = f"Google limitou em {loja.nome}, lote interrompido", 2
                        print(f"   limitado: {loja.nome}")
                        salvar(caminho, estado)
                        break
                    else:
                        estado["feitas"][loja.place_id] = asdict(loja)
                        novas += 1
                        print(f"   ok: {loja.marca} · {loja.nome} · pico={len(loja.horarios_pico)}d · aval={len(loja.avaliacoes)}")
                    salvar(caminho, estado)
                    time.sleep(args.delay)
                resultado = resultado or f"{novas} lojas coletadas, {len(estado['fila'])} na fila"
        finally:
            browser.close()

    estado["lotes"].append({"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"), "resultado": resultado})
    salvar(caminho, estado)
    print(resultado)

    lojas = [para_loja(d) for d in estado["feitas"].values()]
    if lojas:
        exportar(lojas, cfg["saida"])
        if args.publicar and (novas or codigo == 3):
            publicar(cfg)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
