"""Confere o SEO e o GEO do Review Pulse, no pacote gerado ou no ar.

    python3 vitrine-web/verificar_seo.py                 # sites/rivalpulse/public
    python3 vitrine-web/verificar_seo.py --ar            # https://reviewpulse.cassiai.com

O que ele cobra, em cada idioma: titulo e descricao proprios, canonico certo,
hreflang para os tres idiomas, espelho em markdown declarado e existente,
perguntas na pagina e no JSON-LD, dados estruturados validos, imagem de
compartilhamento, e a parte privada (painel e dados) fora do indice.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seo

PUBLICO = Path(__file__).resolve().parent.parent / "sites" / "rivalpulse" / "public"
falhas: list[str] = []


def ler(caminho: str, no_ar: bool) -> tuple[str, dict]:
    if no_ar:
        # curl porque o Python desta máquina não carrega a cadeia de
        # certificados do sistema.
        binario = caminho.endswith((".png", ".jpg", ".svg", ".ico"))
        cmd = ["curl", "-sS", "-A", "cassi-verificador", "--max-time", "30"]
        cmd += ["-I"] if binario else ["-D", "-"]
        r = subprocess.run(cmd + [seo.SITE + caminho], capture_output=True, text=True, check=True)
        # text=True normaliza \r\n em \n, então a divisão é por linha em branco.
        cabecalho, _, corpo = r.stdout.partition("\n\n")
        linhas = cabecalho.splitlines()
        status = linhas[0] if linhas else ""
        cabecalhos = {}
        for linha in linhas[1:]:
            nome, _, valor = linha.partition(":")
            cabecalhos[nome.strip().lower()] = valor.strip()
        cabecalhos["status"] = status
        return corpo, cabecalhos
    arquivo = PUBLICO / caminho.lstrip("/")
    if arquivo.is_dir() or caminho.endswith("/"):
        arquivo = PUBLICO / caminho.strip("/") / "index.html"
    return arquivo.read_text(encoding="utf-8"), {}


def exige(condicao: bool, mensagem: str) -> None:
    if not condicao:
        falhas.append(mensagem)


def pagina(idioma: str, no_ar: bool) -> None:
    caminho = seo.CAMINHO[idioma]
    html, _ = ler(caminho, no_ar)
    onde = f"{caminho} [{idioma}]"
    cabeca = html.split("</head>")[0]

    exige(f"<title>{seo.META[idioma]['titulo']}</title>" in html, f"{onde}: título fora do previsto")
    exige(seo.META[idioma]["descricao"][:60] in cabeca, f"{onde}: descrição fora do previsto")
    exige(f'rel="canonical" href="{seo.SITE}{caminho}"' in cabeca, f"{onde}: canônico errado")
    exige("noindex" not in cabeca, f"{onde}: página pública com noindex")
    exige(f'data-idioma="{idioma}"' in html, f"{onde}: idioma não declarado no html")
    for outro in seo.IDIOMAS:
        exige(
            f'hreflang="{seo.HREFLANG[outro]}" href="{seo.SITE}{seo.CAMINHO[outro]}"' in cabeca,
            f"{onde}: falta hreflang de {outro}",
        )
    exige('hreflang="x-default"' in cabeca, f"{onde}: falta hreflang x-default")
    exige(f'type="text/markdown" href="{caminho}index.md"' in cabeca, f"{onde}: falta o espelho em markdown")
    for marca in ('property="og:title"', 'property="og:image"', 'name="twitter:card"'):
        exige(marca in cabeca, f"{onde}: falta {marca}")

    perguntas = re.findall(r'<details class="fq"[^>]*><summary><h3>([^<]+)</h3>', html)
    esperadas = [p for p, _ in seo.FAQ[idioma]]
    exige(perguntas == esperadas, f"{onde}: perguntas da página diferem do seo.py")

    bruto = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    exige(bool(bruto), f"{onde}: sem dados estruturados")
    if bruto:
        grafo = json.loads(bruto.group(1))["@graph"]
        tipos = {n["@type"] for n in grafo}
        for tipo in ("Organization", "WebSite", "SoftwareApplication", "WebPage", "FAQPage", "BreadcrumbList"):
            exige(tipo in tipos, f"{onde}: falta {tipo} no JSON-LD")
        faq = next(n for n in grafo if n["@type"] == "FAQPage")
        exige(
            [q["name"] for q in faq["mainEntity"]] == esperadas,
            f"{onde}: perguntas do JSON-LD diferem da página",
        )
        exige(
            all(len(q["acceptedAnswer"]["text"]) > 80 for q in faq["mainEntity"]),
            f"{onde}: resposta curta demais para ser citada",
        )

    md, cabecalhos = ler(f"{caminho}index.md", no_ar)
    exige(md.startswith("# "), f"{caminho}index.md: não começa por título")
    exige("{{" not in md and "{N_" not in md, f"{caminho}index.md: campo sem valor")
    exige("cassiai.com" in md, f"{caminho}index.md: sem link para a Cassi.ai")
    if no_ar:
        exige("markdown" in cabecalhos.get("content-type", ""), f"{caminho}index.md: servido fora de text/markdown")


def raiz(no_ar: bool) -> None:
    robots, _ = ler("/robots.txt", no_ar)
    exige("Disallow: /painel" in robots and "Disallow: /v/" in robots, "robots.txt: parte privada liberada")
    exige(f"Sitemap: {seo.SITE}/sitemap.xml" in robots, "robots.txt: sem sitemap")

    mapa, _ = ler("/sitemap.xml", no_ar)
    for idioma in seo.IDIOMAS:
        exige(f"<loc>{seo.SITE}{seo.CAMINHO[idioma]}</loc>" in mapa, f"sitemap.xml: falta {idioma}")
    exige("painel" not in mapa and "/v/" not in mapa, "sitemap.xml: endereço privado listado")

    llms, _ = ler("/llms.txt", no_ar)
    exige(llms.startswith("# Review Pulse"), "llms.txt: sem título")
    exige("index.md" in llms and "cassiai.com" in llms, "llms.txt: sem os espelhos ou sem a Cassi.ai")

    if no_ar:
        for privado in ("/painel/", "/v/moda/"):
            try:
                _, cab = ler(privado, True)
                exige("noindex" in cab.get("x-robots-tag", ""), f"{privado}: sem X-Robots-Tag noindex")
            except Exception as e:  # rota protegida pode responder erro, e isso basta
                print(f"  {privado}: {e}")
        try:
            _, cab = ler("/og.png", True)
            exige(cab.get("content-type", "").startswith("image/"), "/og.png: não é imagem")
        except Exception as e:
            falhas.append(f"/og.png: {e}")
    else:
        exige((PUBLICO / "og.png").exists(), "og.png: não gerado")


def main() -> None:
    no_ar = "--ar" in sys.argv
    print("conferindo", seo.SITE if no_ar else PUBLICO)
    raiz(no_ar)
    for idioma in seo.IDIOMAS:
        pagina(idioma, no_ar)
    if falhas:
        print(f"\n{len(falhas)} falha(s):")
        for f in falhas:
            print(" -", f)
        sys.exit(1)
    print("ok: SEO e GEO conferidos nos três idiomas")


if __name__ == "__main__":
    main()
