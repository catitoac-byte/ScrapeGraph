"""
Pipeline multi-filtro do diretorio Esomar.

Os filtros se sobrepoem muito (soma bruta 1400 para um diretorio de 1300),
entao raspar cada um isoladamente visitaria o mesmo perfil varias vezes.

Aqui a listagem e por filtro, porem o perfil e visitado UMA vez e guardado
em cache no disco. Cada empresa carrega a lista de filtros que casaram com
ela. O cache torna a execucao retomavel: se cair no meio, recomeca de onde
parou sem repetir requisicao.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.esomar import BASE, COLUNAS, Empresa, extrair_empresa, listar_urls

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "dados" / "cache" / "perfis.json"
SAIDA = RAIZ / "dados" / "saida"

_ID = re.compile(r"/company/(\d+)/")


def id_da_url(url: str) -> str:
    m = _ID.search(url)
    return m.group(1) if m else url


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def carregar_cache() -> dict[str, dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def salvar_cache(cache: dict[str, dict]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CACHE)  # troca atomica: nunca deixa o cache pela metade


def importar_json(caminho: Path, cache: dict[str, dict]) -> int:
    """Traz resultados de uma execucao anterior para dentro do cache."""
    if not caminho.exists():
        return 0
    novos = 0
    for reg in json.loads(caminho.read_text(encoding="utf-8")):
        ident = id_da_url(reg.get("url_perfil", ""))
        if ident and ident not in cache and not reg.get("erro"):
            reg.setdefault("filtros", [])
            cache[ident] = reg
            novos += 1
    return novos


# --------------------------------------------------------------------------
# Execucao
# --------------------------------------------------------------------------

def executar(
    filtros: list[str],
    *,
    delay: float = 2.0,
    salvar_a_cada: int = 10,
    headless: bool = True,
) -> dict[str, dict]:
    cache = carregar_cache()
    print(f"cache inicial: {len(cache)} perfis\n")

    # ---- Fase A: listagem por filtro -------------------------------------
    print("=" * 62)
    print("FASE A  listagem por filtro")
    print("=" * 62)
    membros: dict[str, list[str]] = {}
    for i, f in enumerate(filtros, 1):
        rotulo = f.split("?", 1)[1] if "?" in f else f
        print(f"\n[{i}/{len(filtros)}] {rotulo}")
        try:
            urls = listar_urls(f, max_paginas=90, delay=delay, headless=headless)
        except Exception as exc:
            print(f"        !! filtro falhou ({type(exc).__name__}); seguindo")
            continue
        print(f"        -> {len(urls)} empresas")
        for u in urls:
            membros.setdefault(id_da_url(u), []).append(rotulo)
        # guarda a url canonica de cada id
        for u in urls:
            cache.setdefault(id_da_url(u), {}).setdefault("url_perfil", u)
        salvar_cache(cache)

    print(f"\nuniao dos filtros: {len(membros)} empresas unicas")

    # ---- Fase B: perfis ainda nao coletados ------------------------------
    pendentes = [
        (ident, cache[ident]["url_perfil"])
        for ident in membros
        if not cache.get(ident, {}).get("nome")
    ]
    print(f"ja em cache: {len(membros) - len(pendentes)} | a coletar: {len(pendentes)}")

    if pendentes:
        print("\n" + "=" * 62)
        print("FASE B  coleta de perfis")
        print("=" * 62)
        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=headless)
            page = navegador.new_page()
            try:
                for n, (ident, url) in enumerate(pendentes, 1):
                    emp = extrair_empresa(page, url)
                    registro = asdict(emp)
                    registro["filtros"] = membros.get(ident, [])
                    cache[ident] = registro
                    marca = "!" if emp.erro else "."
                    print(f"  [{n:>4}/{len(pendentes)}] {marca} {emp.nome[:38]:38} | "
                          f"{emp.email[:30]:30} | {len(emp.contatos)}c")
                    if n % salvar_a_cada == 0:
                        salvar_cache(cache)
                    if n < len(pendentes):
                        time.sleep(delay)
            finally:
                navegador.close()
                salvar_cache(cache)

    # anexa a lista de filtros tambem aos que ja estavam em cache
    for ident, fs in membros.items():
        if ident in cache:
            atuais = set(cache[ident].get("filtros") or [])
            cache[ident]["filtros"] = sorted(atuais | set(fs))
    salvar_cache(cache)
    return {i: cache[i] for i in membros if cache.get(i, {}).get("nome")}


# --------------------------------------------------------------------------
# Saida
# --------------------------------------------------------------------------

def exportar_mestre(registros: dict[str, dict], nome: str = "esomar_mestre") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj = SAIDA / f"{nome}.json"
    cc = SAIDA / f"{nome}.csv"

    dados = sorted(registros.values(), key=lambda r: r.get("nome", ""))
    cj.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    colunas = [c for c in COLUNAS if c != "erro"] + ["filtros"]
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=colunas)
        w.writeheader()
        for r in dados:
            linha = dict(r)
            linha["tipos"] = " | ".join(linha.get("tipos") or [])
            linha["filtros"] = " | ".join(linha.get("filtros") or [])
            linha["contatos"] = " | ".join(
                c["nome"] + (f" ({c['cargo']})" if c.get("cargo") else "")
                for c in (linha.get("contatos") or [])
            )
            w.writerow({k: linha.get(k, "") for k in colunas})
    return cj, cc
