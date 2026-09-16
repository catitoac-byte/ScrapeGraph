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

BARRA = """<style>
.vg-bar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 24px;background:#0F172A;color:#E2E8F0;font:500 13px/1.2 "Figtree",system-ui,sans-serif}
.vg-bar a{color:#E2E8F0;text-decoration:none}
.vg-bar img{height:18px;display:block;filter:invert(1) brightness(2)}
.vg-bar .l{display:flex;align-items:center;gap:12px}
.vg-bar .sair{border:1px solid rgba(226,232,240,.35);border-radius:8px;padding:6px 12px;background:none;color:#E2E8F0;font:inherit;cursor:pointer}
.vg-bar .sair:hover{border-color:#E2E8F0}
@media (max-width:640px){.vg-bar{padding-inline:16px}}
</style>
<div class="vg-bar"><span class="l"><a href="/"><img src="/cassi-wordmark.svg" alt="Cassi.ai"></a><span>Vitrine · painel do cliente</span></span>
<span class="l"><button type="button" class="sair" id="vg-tema" aria-pressed="false">Tema escuro</button><a class="sair" href="/api/sair">Sair</a></span></div>
<script>
(function(){
  var b = document.getElementById("vg-tema");
  function pinta(){
    var escuro = document.documentElement.getAttribute("data-theme") === "dark";
    b.textContent = escuro ? "Tema claro" : "Tema escuro";
    b.setAttribute("aria-pressed", String(escuro));
  }
  b.addEventListener("click", function(){
    var novo = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", novo);
    try { localStorage.setItem("vitrine-tema", novo); } catch (e) {}
    pinta();
  });
  pinta();
})();
</script>
"""

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
        f"{TEMA_INICIAL}{head}\n{resto[:corte]}\n</head>\n<body>\n{BARRA}\n{resto[corte:]}\n</body>\n</html>\n"
    )
    return doc.replace('<script src="data.js"></script>', '<script src="/painel/data.js"></script>')


def pagina(cfg: dict, dados: dict) -> str:
    leituras = sum(1 for l in dados["lojas"] for d in l["pico"].values() for v in d.values() if v is not None)
    site = cfg["site"]
    trocas = {
        "{{ROTULO_PILOTO}}": cfg["rotulo_piloto"],
        "{{N_LOJAS}}": milhar(len(dados["lojas"])),
        "{{N_MARCAS}}": milhar(len(cfg["marcas"])),
        "{{N_AVALIACOES}}": milhar(len(dados["avaliacoes"])),
        "{{N_LEITURAS}}": milhar(leituras),
        "{{N_TEMAS}}": milhar(len(cfg["temas"])),
        "{{TEMAS_LISTA}}": site["temas_lista"],
        "{{PERGUNTA_LOCAL}}": site["pergunta_local"],
        "{{COMPARACAO_LOCAL}}": site["comparacao_local"],
    }
    s = (MODELO / "template" / "index.html").read_text(encoding="utf-8")
    for k, v in trocas.items():
        s = s.replace(k, v)
    assert "{{" not in s, "campo do modelo sem valor"
    return s


def main(vertical: str) -> None:
    cfg = json.loads((VERTICAIS / f"{vertical}.json").read_text(encoding="utf-8"))
    data_js = DADOS / cfg["id"] / "data.js"
    texto = data_js.read_text(encoding="utf-8")
    dados = json.loads(texto[texto.index("=") + 1:].rstrip().rstrip(";"))

    destino = SITES / cfg["id"]
    pub = destino / "public"
    (pub / "painel").mkdir(parents=True, exist_ok=True)
    for nome in ("middleware.js", "package.json", "package-lock.json", "vercel.json"):
        shutil.copy(MODELO / nome, destino / nome)
    shutil.copytree(MODELO / "api", destino / "api", dirs_exist_ok=True)
    shutil.copy(MODELO / "template" / "cassi-wordmark.svg", pub / "cassi-wordmark.svg")
    (pub / "index.html").write_text(pagina(cfg, dados), encoding="utf-8")
    (pub / "painel" / "index.html").write_text(painel(cfg), encoding="utf-8")
    shutil.copy(data_js, pub / "painel" / "data.js")
    print("ok:", destino)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "moda")
