"""
Normalizacao final: corrige o campo pais e reprocessa pendencias.

Bug corrigido aqui: _pais_do_endereco pegava o ultimo trecho apos virgula.
Isso trunca paises cujo nome contem virgula ("Korea, Republic of" virava
"Republic of") e transforma sufixos de cidade em pais ("Shanghai").

A fonte confiavel e o proprio filtro que trouxe a empresa: se ela veio de
from=3, o pais e o que o mapa de IDs diz para o 3. O endereco vira apenas
fallback, e agora casado contra a lista conhecida de paises.

    uv run python -u normalizar.py
"""

import json
import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from playwright.sync_api import sync_playwright

from scraper_lab.esomar import extrair_empresa
from scraper_lab.pipeline import carregar_cache, exportar_mestre, salvar_cache

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"


def esperar(*processos: str, timeout: float = 28800) -> None:
    limite = time.time() + timeout
    for nome in processos:
        avisou = False
        while time.time() < limite:
            if not subprocess.run(["pgrep", "-f", nome], capture_output=True,
                                  text=True).stdout.strip():
                if avisou:
                    print(f"      {nome} concluido")
                break
            if not avisou:
                print(f"[0/4] Aguardando {nome}...")
                avisou = True
            time.sleep(20)
    print()


def retentar_pendentes(cache: dict) -> int:
    pend = [(k, v.get("url_perfil")) for k, v in cache.items()
            if not v.get("nome") and v.get("url_perfil")]
    if not pend:
        print("nenhuma pendencia")
        return 0
    print("=" * 62)
    print(f"FASE 1  retentando {len(pend)} perfis pendentes")
    print("=" * 62)
    recuperados = 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        try:
            for ident, url in pend:
                filtros = cache[ident].get("filtros") or []
                emp = extrair_empresa(page, url)
                if emp.nome:
                    reg = asdict(emp)
                    reg["filtros"] = filtros
                    cache[ident] = reg
                    recuperados += 1
                    print(f"  OK  {emp.nome[:40]:40} | {emp.email[:30]}")
                else:
                    print(f"  --  ainda falhando: {url[-40:]}")
                time.sleep(2)
        finally:
            b.close()
    return recuperados


def normalizar_paises(cache: dict) -> int:
    mapa = {d["id"]: d["pais"]
            for d in json.loads((DADOS / "paises_ids_completo.json").read_text())}
    conhecidos = sorted(set(mapa.values()), key=len, reverse=True)

    print("\n" + "=" * 62)
    print("FASE 2  normalizando o campo pais")
    print("=" * 62)

    alterados = 0
    for v in cache.values():
        if not v.get("nome"):
            continue
        antigo = v.get("pais", "")
        novo = ""

        # 1) o endereco e a verdade por empresa. Uma empresa pode constar de
        #    VARIOS filtros de pais (ex.: from=41 e from=51), entao escolher
        #    pelo filtro rotulava uma agencia de Dubai como Arabia Saudita.
        #    Casamos o fim do endereco contra a lista conhecida, do nome mais
        #    longo para o mais curto, para que "Korea, Republic of" ganhe de
        #    um eventual sufixo mais curto.
        end = (v.get("endereco") or "").strip().rstrip(".").lower()
        for pais in conhecidos:
            if end.endswith(pais.lower()):
                novo = pais
                break

        # 2) endereco sem pais reconhecivel: cai para o filtro de origem
        if not novo:
            for f in v.get("filtros") or []:
                m = re.fullmatch(r"from=(\d+)", f.strip())
                if m and int(m.group(1)) in mapa:
                    novo = mapa[int(m.group(1))]
                    break

        if novo and novo != antigo:
            v["pais"] = novo
            alterados += 1
    print(f"{alterados} registros com pais corrigido")
    return alterados


def conferir(cache: dict) -> None:
    esperado = {d["pais"]: d["total"]
                for d in json.loads((DADOS / "paises_ids_completo.json").read_text())}
    ok = [v for v in cache.values() if v.get("nome")]
    obtido: dict[str, int] = {}
    for v in ok:
        obtido[v.get("pais", "")] = obtido.get(v.get("pais", ""), 0) + 1

    print("\n" + "=" * 62)
    print("FASE 3  conferencia por pais")
    print("=" * 62)
    faltas = [(p, e, obtido.get(p, 0)) for p, e in esperado.items() if obtido.get(p, 0) < e]
    if faltas:
        print(f"{len(faltas)} paises abaixo do esperado "
              f"({sum(e - o for _, e, o in faltas)} empresas):")
        for p, e, o in sorted(faltas, key=lambda x: -(x[1] - x[2])):
            print(f"   {p[:34]:34} esperado {e:>4} | obtido {o:>4}")
    else:
        print("todos os paises bateram o esperado")
    desconhecidos = {p: n for p, n in obtido.items() if p not in esperado}
    if desconhecidos:
        print(f"\nrotulos fora do mapa de paises: {desconhecidos}")


if __name__ == "__main__":
    inicio = time.time()
    esperar("maximizar.py", "reparo.py")

    cache = carregar_cache()
    rec = retentar_pendentes(cache)
    salvar_cache(cache)

    normalizar_paises(cache)
    salvar_cache(cache)

    conferir(cache)

    completo = {k: v for k, v in cache.items() if v.get("nome")}
    cj, cc = exportar_mestre(completo, "esomar_mestre")

    print("\n" + "=" * 62)
    print("  RESULTADO FINAL")
    print(f"  empresas ......... {len(completo)}")
    print(f"  recuperadas ...... {rec}")
    print(f"  com email ........ {sum(1 for r in completo.values() if r.get('email'))}")
    print(f"  com site ......... {sum(1 for r in completo.values() if r.get('site'))}")
    print(f"  contatos ......... {sum(len(r.get('contatos') or []) for r in completo.values())}")
    print(f"  paises ........... {len({r.get('pais') for r in completo.values() if r.get('pais')})}")
    print(f"  tempo ............ {(time.time()-inicio)/60:.1f} min")
    print(f"  CSV .............. {cc}")
    print("=" * 62)
