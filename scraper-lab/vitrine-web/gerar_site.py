"""
Monta public/painel/ para o deploy na Vercel.

    uv run python vitrine-web/gerar_site.py

Envolve painel/index.html num documento completo (charset, barra com Sair) e
copia o data.js gerado por painel/gerar_dados.py. public/painel/ fica fora do
git: carrega texto de avaliacoes. O acesso e protegido pelo middleware.js.
"""

import shutil
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LAB = AQUI.parent
FONTE = LAB / "painel" / "index.html"
DADOS = LAB / "dados" / "saida" / "lojas_google" / "painel" / "data.js"
DESTINO = AQUI / "public" / "painel"

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


def main() -> None:
    corpo = FONTE.read_text(encoding="utf-8")
    titulo_fim = corpo.index("</title>") + len("</title>")
    head = corpo[:titulo_fim]
    resto = corpo[titulo_fim:]
    # tudo antes do primeiro <div id="app"> e head (meta, fontes, estilo)
    corte = resto.index('<div id="app"></div>')
    doc = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
        "<link rel=\"icon\" href=\"/cassi-wordmark.svg\">\n"
        f"{TEMA_INICIAL}{head}\n{resto[:corte]}\n</head>\n<body>\n{BARRA}\n{resto[corte:]}\n</body>\n</html>\n"
    )
    # data.js relativo a /painel/ (cleanUrls serve /painel sem barra)
    doc = doc.replace('<script src="data.js"></script>', '<script src="/painel/data.js"></script>')
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "index.html").write_text(doc, encoding="utf-8")
    shutil.copy(DADOS, DESTINO / "data.js")
    print("ok:", DESTINO)


if __name__ == "__main__":
    main()
