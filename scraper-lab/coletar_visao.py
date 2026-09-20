"""
Coleta automatica da visao geral (sem avaliacoes) das fichas ja descobertas.

    uv run python coletar_visao.py --vertical imobiliarias
    uv run python coletar_visao.py --vertical imobiliarias --refazer

So a aba de Avaliacoes tem o limite de visualizacao sem login (5 avaliacoes).
Nome, endereco, telefone, site, nota, total, categoria, horario de
funcionamento, distribuicao de estrelas, topicos e a aba Sobre (atributos)
sao publicos e saem sem login. Sem grafico de pico (vertical com "pico":
false) tambem nao precisa de janela visivel, entao roda headless.

Nao toca na fila nem em "feitas" do estado da coleta assistida: so junta
numa vitrine paralela, dados/saida/lojas_google/<saida>_visao.json, por
place_id. A importacao da coleta assistida (coleta-assistida/importar.py)
completa com isso os campos que o favorito Salvar dados da loja nao le
(Sobre, destaques, fotos), sem atrapalhar o fluxo de avaliacoes.
"""

import argparse
import json
import time
from dataclasses import asdict

from playwright.sync_api import sync_playwright

from coleta_em_lotes import VERTICAIS, carregar
from scraper_lab.lojas_google import SAIDA, _chave, _sem_acento, abrir_navegador, raspar_loja


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", required=True)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--refazer", action="store_true", help="repete mesmo quem ja esta no cache")
    args = ap.parse_args()

    cfg = json.loads((VERTICAIS / f"{args.vertical}.json").read_text(encoding="utf-8"))
    estado = carregar(SAIDA / f"{cfg['saida']}_estado.json")
    cache_path = SAIDA / f"{cfg['saida']}_visao.json"
    cache: dict[str, dict] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    alvo = _sem_acento(cfg["cidade"].split(",")[0].strip())
    pendentes = [it for it in estado["fila"] if args.refazer or _chave(it["url"]) not in cache]
    print(f"{len(pendentes)} fichas sem visao geral automatica, de {len(estado['fila'])} na fila")
    if not pendentes:
        return

    with sync_playwright() as pw:
        browser, page = abrir_navegador(pw, headless=not cfg.get("pico", True))
        try:
            for i, it in enumerate(pendentes, 1):
                loja = raspar_loja(page, it["marca"], it["url"], max_avaliacoes=0, cidade_alvo=alvo)
                cache[_chave(it["url"])] = asdict(loja)
                fora = " FORA DA CIDADE" if loja.cidade and _sem_acento(loja.cidade) != alvo else ""
                print(f"   {i:>2}/{len(pendentes)} {loja.marca:<10} {loja.nome[:35]:<35} "
                      f"nota={loja.nota} aval={loja.total_avaliacoes} tel={loja.telefone or '-'}{fora}")
                cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
                time.sleep(args.delay)
        finally:
            browser.close()
    print(f"\n{cache_path}")


if __name__ == "__main__":
    main()
