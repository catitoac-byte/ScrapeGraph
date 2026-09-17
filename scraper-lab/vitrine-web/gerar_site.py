"""
Monta o site de uma vertical a partir do modelo em vitrine-web/.

    uv run python vitrine-web/gerar_site.py moda
    uv run python vitrine-web/gerar_site.py supermercados

Saida em scraper-lab/sites/<vertical>/ (fora do git: carrega dados coletados):
api/, middleware.js, package.json, vercel.json e public/ com a pagina comercial
preenchida com os numeros da vertical e o painel protegido em public/painel/.
Depois: cd sites/<vertical> && vercel deploy --prod --yes --scope cassiai
"""

import json
import shutil
import sys
from pathlib import Path

MODELO = Path(__file__).resolve().parent
LAB = MODELO.parent
VERTICAIS = LAB / "verticais"
PAINEL = LAB / "painel" / "index.html"
DADOS = LAB / "dados" / "saida" / "lojas_google" / "painel"
SITES = LAB / "sites"

# Idioma, tema e sair ficam no trilho lateral do proprio painel.

# Roda no head, antes da primeira pintura: claro por padrao, escuro so se o
# usuario escolheu. Sem isso o painel seguia o tema do sistema operacional.
TEMA_INICIAL = """<script>
(function(){
  var t = null;
  try { t = localStorage.getItem("vitrine-tema"); } catch (e) {}
  document.documentElement.setAttribute("data-theme", t === "dark" ? "dark" : "light");
})();
</script>
"""


EM_COLETA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{nome}</title><link rel="icon" href="/cassi-wordmark.svg">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Instrument+Sans:wght@300;400;500&display=swap">
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#F8FAFC;color:#0F172A;font:300 17px/1.6 "Instrument Sans",system-ui,sans-serif;padding-inline:20px}}
main{{max-width:560px;background:#fff;border:1px solid rgba(15,23,42,.08);border-radius:1rem;padding:36px}}
h1{{font:800 30px/1.1 "Syne",sans-serif;letter-spacing:-.025em;margin:14px 0 12px}}
.l{{font:700 12px "Syne",sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#2563EB}}
p{{color:#475569;margin:0 0 12px}} a{{color:#2563EB}}</style></head>
<body><main><span class="l">{cidade}</span><h1>Coleta em andamento</h1>
<p>O painel de {marcas} está sendo montado. A varredura das fichas públicas roda com pausas para respeitar os limites da fonte.</p>
<p>Assim que os dados forem conferidos, este endereço passa a mostrar o painel completo.</p>
<p><a href="/api/sair">Sair</a></p></main></body></html>
"""


def lista_pt(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def painel(cfg: dict) -> str:
    corpo = PAINEL.read_text(encoding="utf-8")
    fim_titulo = corpo.index("</title>") + len("</title>")
    resto = corpo[fim_titulo:]
    corte = resto.index('<div id="app"></div>')
    head = f"<title>{cfg['nome_pagina']}</title>"
    doc = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
        "<link rel=\"icon\" href=\"/cassi-wordmark.svg\">\n"
        f"{TEMA_INICIAL}{head}\n{resto[:corte]}\n</head>\n<body>\n{resto[corte:]}\n</body>\n</html>\n"
    )
    return doc.replace('<script src="data.js"></script>', '<script src="/painel/data.js"></script>')


def pagina(cfg: dict, dados: dict | None) -> str:
    site = cfg["site"]
    if dados:
        leituras = sum(1 for l in dados["lojas"] for d in l["pico"].values() for v in d.values() if v is not None)
        n_lojas, n_aval, n_leit = milhar(len(dados["lojas"])), milhar(len(dados["avaliacoes"])), milhar(leituras)
    else:
        n_lojas = n_aval = n_leit = "…"
    trocas = {
        "{{ROTULO_PILOTO}}": cfg["rotulo_piloto"] + ("" if dados else " · coleta em andamento"),
        "{{N_LOJAS}}": n_lojas,
        "{{N_MARCAS}}": milhar(len(cfg["marcas"])),
        "{{N_AVALIACOES}}": n_aval,
        "{{N_LEITURAS}}": n_leit,
        "{{N_TEMAS}}": milhar(len(cfg["temas"])),
        "{{TEMAS_LISTA}}": site["temas_lista"],
        "{{PERGUNTA_LOCAL}}": site["pergunta_local"],
        "{{COMPARACAO_LOCAL}}": site["comparacao_local"],
    }
    # Versoes em espanhol e ingles, trocadas no navegador pela escolha de idioma
    em_coleta = {"ES": " · recolección en curso", "EN": " · collection in progress"}
    for sufixo in ("ES", "EN"):
        tr = cfg["i18n"][sufixo.lower()]
        trocas[f"{{{{ROTULO_PILOTO_{sufixo}}}}}"] = tr["rotulo_piloto"] + ("" if dados else em_coleta[sufixo])
        for chave in ("temas_lista", "pergunta_local", "comparacao_local"):
            trocas[f"{{{{{chave.upper()}_{sufixo}}}}}"] = tr[chave]
    s = (MODELO / "template" / "index.html").read_text(encoding="utf-8")
    for k, v in sorted(trocas.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(k, v)
    assert "{{" not in s, "campo do modelo sem valor"
    return s


def main(vertical: str) -> None:
    cfg = json.loads((VERTICAIS / f"{vertical}.json").read_text(encoding="utf-8"))
    data_js = DADOS / cfg["id"] / "data.js"
    dados = None
    if data_js.exists():
        texto = data_js.read_text(encoding="utf-8")
        dados = json.loads(texto[texto.index("=") + 1:].rstrip().rstrip(";"))

    destino = SITES / cfg["id"]
    pub = destino / "public"
    (pub / "painel").mkdir(parents=True, exist_ok=True)
    for nome in ("middleware.js", "package.json", "package-lock.json", "vercel.json"):
        shutil.copy(MODELO / nome, destino / nome)
    shutil.copytree(MODELO / "api", destino / "api", dirs_exist_ok=True)
    for logo in ("cassi-wordmark.svg", "cassi-wordmark-reversed.svg"):
        shutil.copy(MODELO / "template" / logo, pub / logo)
    (pub / "index.html").write_text(pagina(cfg, dados), encoding="utf-8")
    if dados:
        (pub / "painel" / "index.html").write_text(painel(cfg), encoding="utf-8")
        shutil.copy(data_js, pub / "painel" / "data.js")
    else:
        (pub / "painel" / "index.html").write_text(EM_COLETA.format(nome=cfg["nome_pagina"],
            marcas=lista_pt([m["nome"] for m in cfg["marcas"]]), cidade=cfg["cidade"]), encoding="utf-8")
    print("ok:", destino)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "moda")
