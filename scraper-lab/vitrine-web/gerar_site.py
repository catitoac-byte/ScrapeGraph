"""
Monta o site unico do Review Pulse com todas as verticais piloto.

    uv run python vitrine-web/gerar_site.py
    uv run python vitrine-web/gerar_site.py --redirecionamentos

Saida em scraper-lab/sites/rivalpulse/ (fora do git: carrega dados coletados):
api/, middleware.js, package.json, vercel.json e public/ com
  /              pagina comercial com os numeros somados das verticais
  /painel        escolha de vertical (so mostra as que o usuario pode abrir)
  /v/<id>/       painel de cada vertical, com o data.js ao lado
O acesso de cada usuario sai de RIVAL_USUARIOS (ver usuarios.py).
Depois: cd sites/rivalpulse && vercel deploy --prod --yes --scope cassiai

Com --redirecionamentos, monta tambem sites/redir-<id>/, que mandam os
enderecos antigos de cada vertical para o dominio novo.
"""

import json
import re
import shutil
import sys
from pathlib import Path

import seo

MODELO = Path(__file__).resolve().parent
LAB = MODELO.parent
VERTICAIS = LAB / "verticais"
PAINEL = LAB / "painel" / "index.html"
DADOS = LAB / "dados" / "saida" / "lojas_google" / "painel"
SITES = LAB / "sites"
PRODUTO = json.loads((MODELO / "produto.json").read_text(encoding="utf-8"))

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


def lista(itens: list[str], e: str = "e") -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + f" {e} " + itens[-1]


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def carregar_verticais() -> list[tuple[dict, dict]]:
    """Verticais com painel gerado, na ordem do nome do arquivo."""
    out = []
    for arq in sorted(VERTICAIS.glob("*.json")):
        cfg = json.loads(arq.read_text(encoding="utf-8"))
        data_js = DADOS / cfg["id"] / "data.js"
        if not data_js.exists():
            print(f"sem dados, fica de fora: {cfg['id']}")
            continue
        texto = data_js.read_text(encoding="utf-8")
        out.append((cfg, json.loads(texto[texto.index("=") + 1:].rstrip().rstrip(";"))))
    return out


def nome_vertical(cfg: dict, idioma: str) -> str:
    r = cfg["rotulo_piloto"] if idioma == "pt" else cfg["i18n"][idioma]["rotulo_piloto"]
    return r[0].upper() + r[1:]


def painel(cfg: dict) -> str:
    corpo = PAINEL.read_text(encoding="utf-8")
    fim_titulo = corpo.index("</title>") + len("</title>")
    resto = corpo[fim_titulo:]
    corte = resto.index('<div id="app"></div>')
    head = f"<title>{PRODUTO['nome']} · {nome_vertical(cfg, 'pt')} · {cfg['cidade'].split(',')[0]}</title>"
    doc = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
        "<link rel=\"icon\" type=\"image/png\" sizes=\"64x64\" href=\"/favicon.png\">\n"
        f"{TEMA_INICIAL}{head}\n{resto[:corte]}\n</head>\n<body>\n{resto[corte:]}\n</body>\n</html>\n"
    )
    return doc.replace('<script src="data.js"></script>', f'<script src="/v/{cfg["id"]}/data.js"></script>')


def trocas_de_texto(verticais: list[tuple[dict, dict]]) -> dict:
    """Numeros somados das verticais e os rotulos em cada idioma."""
    lojas = sum(len(d["lojas"]) for _, d in verticais)
    aval = sum(len(d["avaliacoes"]) for _, d in verticais)
    leituras = sum(1 for _, d in verticais for l in d["lojas"] for dia in l["pico"].values() for v in dia.values() if v is not None)
    marcas = sum(len(c["marcas"]) for c, _ in verticais)
    temas = len({t["id"] for c, _ in verticais for t in c["temas"]})
    conectivo = {"pt": "e", "es": "y", "en": "and"}
    trocas = {
        "{{N_LOJAS}}": milhar(lojas),
        "{{N_MARCAS}}": milhar(marcas),
        "{{N_AVALIACOES}}": milhar(aval),
        "{{N_LEITURAS}}": milhar(leituras),
        "{{N_TEMAS}}": milhar(temas),
    }
    for idioma, sufixo in (("pt", ""), ("es", "_ES"), ("en", "_EN")):
        rotulos = [c["rotulo_piloto"] if idioma == "pt" else c["i18n"][idioma]["rotulo_piloto"] for c, _ in verticais]
        trocas[f"{{{{ROTULO_PILOTO{sufixo}}}}}"] = lista(rotulos, conectivo[idioma])
        for chave, valor in PRODUTO["textos"][idioma].items():
            trocas[f"{{{{{chave.upper()}{sufixo}}}}}"] = valor
    return trocas


def aplicar(texto: str, trocas: dict) -> str:
    """As chaves com sufixo de idioma trocam antes das sem sufixo."""
    for k, v in sorted(trocas.items(), key=lambda kv: -len(kv[0])):
        texto = texto.replace(k, v)
    return texto


# Um elemento com data-t pode conter outras tags dentro, então o fechamento
# certo é achado contando abertura e fechamento da mesma tag.
ABRE = re.compile(r'<(\w+)([^>]*\sdata-t="([^"]+)"[^>]*)>')


def traduzir(html: str, dic: dict) -> str:
    """Aplica o dicionário no HTML, como o navegador faria em tempo de leitura.

    A página passa a existir traduzida no próprio arquivo: é o que buscador e
    motor de resposta leem, porque nenhum dos dois executa a troca em JS.
    """
    saida = []
    pos = 0
    while True:
        m = ABRE.search(html, pos)
        if not m:
            saida.append(html[pos:])
            return "".join(saida)
        tag, chave = m.group(1), m.group(3)
        fim_abertura = m.end()
        nivel = 1
        i = fim_abertura
        while nivel:
            prox = re.compile(f"</?{tag}\\b", re.I).search(html, i)
            assert prox, f"tag {tag} sem fechamento"
            nivel += -1 if html[prox.start() + 1] == "/" else 1
            i = prox.end()
        fim_conteudo = html.rindex(f"</{tag}", fim_abertura, i)
        novo = dic.get(chave)
        saida.append(html[pos:fim_abertura])
        saida.append(novo if novo else html[fim_abertura:fim_conteudo])
        pos = fim_conteudo
    

def dicionarios(modelo: str) -> dict:
    """Os dicionários de es e en que o próprio modelo carrega."""
    bruto = re.search(r"var DIC = (\{.*?\n\});", modelo, re.S).group(1)
    return json.loads(bruto)


def pagina(modelo: str, idioma: str, trocas: dict, dic: dict) -> str:
    """Página comercial de um idioma, com SEO, perguntas e dados estruturados."""
    s = modelo
    if idioma != "pt":
        s = traduzir(s, dic[idioma])
        s = s.replace('<html lang="pt-BR" data-idioma="pt">', f'<html lang="{seo.HTML_LANG[idioma]}" data-idioma="{idioma}">', 1)
    s = s.replace("{{FAQ}}", seo.faq_html(idioma), 1)
    s = s.replace("{{JSONLD}}", seo.jsonld(idioma, trocas), 1)
    s = aplicar(s, seo.cabeca(idioma))
    s = aplicar(s, trocas)
    assert "{{" not in s, f"campo do modelo sem valor em {idioma}"
    return s


def escolha(verticais: list[tuple[dict, dict]]) -> str:
    cartoes = []
    for cfg, d in verticais:
        cartoes.append({
            "id": cfg["id"],
            "nome": {i: nome_vertical(cfg, i) for i in ("pt", "es", "en")},
            "titulo": {"pt": cfg["titulo"], "es": cfg["i18n"]["es"]["titulo"], "en": cfg["i18n"]["en"]["titulo"]},
            "cidade": cfg["cidade"],
            "marcas": [m["nome"] for m in cfg["marcas"]],
            "cores": cfg.get("cores", {}).get("light") or [],
            "lojas": len(d["lojas"]),
            "avaliacoes": len(d["avaliacoes"]),
            "coleta": d.get("coleta", ""),
        })
    s = (MODELO / "template" / "painel.html").read_text(encoding="utf-8")
    s = s.replace("<head>\n", "<head>\n" + TEMA_INICIAL, 1)
    return s.replace("__VERTICAIS__", json.dumps(cartoes, ensure_ascii=False))


def montar() -> None:
    verticais = carregar_verticais()
    assert verticais, "nenhuma vertical com dados"
    destino = SITES / PRODUTO["projeto"]
    pub = destino / "public"
    if pub.exists():
        shutil.rmtree(pub)
    (pub / "painel").mkdir(parents=True)
    for nome in ("middleware.js", "package.json", "package-lock.json", "vercel.json"):
        shutil.copy(MODELO / nome, destino / nome)
    if (destino / "api").exists():
        shutil.rmtree(destino / "api")
    shutil.copytree(MODELO / "api", destino / "api")
    for logo in ("cassi-wordmark.svg", "cassi-wordmark-reversed.svg", "favicon.png", "og.png"):
        shutil.copy(MODELO / "template" / logo, pub / logo)
    modelo = (MODELO / "template" / "index.html").read_text(encoding="utf-8")
    trocas = trocas_de_texto(verticais)
    dic = dicionarios(modelo)
    coleta = max((d.get("coleta", "") for _, d in verticais), default="")[:10]
    for idioma in seo.IDIOMAS:
        destino_idioma = pub if idioma == "en" else pub / idioma
        destino_idioma.mkdir(parents=True, exist_ok=True)
        (destino_idioma / "index.html").write_text(pagina(modelo, idioma, trocas, dic), encoding="utf-8")
        (destino_idioma / "index.md").write_text(aplicar(seo.markdown(idioma), trocas), encoding="utf-8")
    (pub / "robots.txt").write_text(seo.robots(), encoding="utf-8")
    (pub / "sitemap.xml").write_text(seo.sitemap(coleta or "2026-09-17"), encoding="utf-8")
    (pub / "llms.txt").write_text(seo.llms(), encoding="utf-8")
    (pub / "painel" / "index.html").write_text(escolha(verticais), encoding="utf-8")
    for cfg, _ in verticais:
        alvo = pub / "v" / cfg["id"]
        alvo.mkdir(parents=True)
        (alvo / "index.html").write_text(painel(cfg), encoding="utf-8")
        shutil.copy(DADOS / cfg["id"] / "data.js", alvo / "data.js")
    print("ok:", destino, "·", ", ".join(c["id"] for c, _ in verticais))


def redirecionamentos() -> None:
    """Enderecos antigos (um projeto Vercel por vertical) passam a apontar para o dominio novo."""
    novo = f"https://{PRODUTO['dominio']}"
    for vertical in PRODUTO["dominios_antigos"]:
        destino = SITES / f"redir-{vertical}"
        (destino / "public").mkdir(parents=True, exist_ok=True)
        antigo = SITES / vertical / ".vercel"
        if antigo.exists() and not (destino / ".vercel").exists():
            shutil.copytree(antigo, destino / ".vercel")
        (destino / "public" / "index.html").write_text(f'<meta http-equiv="refresh" content="0;url={novo}/">', encoding="utf-8")
        conf = {
            "$schema": "https://openapi.vercel.sh/vercel.json",
            "framework": None, "buildCommand": "", "outputDirectory": "public",
            "redirects": [
                {"source": "/painel(/.*)?", "destination": f"{novo}/v/{vertical}", "permanent": True},
                {"source": "/", "destination": f"{novo}/", "permanent": True},
                {"source": "/(.*)", "destination": f"{novo}/$1", "permanent": True},
            ],
        }
        (destino / "vercel.json").write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")
        print("ok:", destino)


if __name__ == "__main__":
    montar()
    if "--redirecionamentos" in sys.argv:
        redirecionamentos()
