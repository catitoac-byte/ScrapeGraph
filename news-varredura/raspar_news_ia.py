"""Varredura recorrente de novidades em IA.

Le feeds RSS e Atom das fontes primarias do setor mais o arXiv, filtra por janela
de tempo e por palavras chave, e grava um digest datado em dados/saida/.

Sem dependencia externa. So biblioteca padrao.

Uso:
    python3 raspar_news_ia.py                 # varredura dos ultimos 14 dias
    python3 raspar_news_ia.py --dias 30       # janela maior
    python3 raspar_news_ia.py --verificar     # so testa se os feeds respondem
    python3 raspar_news_ia.py --tudo          # sem filtro de palavra chave
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SAIDA = RAIZ / "dados" / "saida"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"

TEMPO_LIMITE = 25

# nome, categoria, url do feed. Lista verificada em 2026-09-02.
FEEDS: list[tuple[str, str, str]] = [
    # Laboratorios
    ("OpenAI", "lab", "https://openai.com/news/rss.xml"),
    ("Google DeepMind", "lab", "https://deepmind.google/blog/rss.xml"),
    ("Google Research", "lab", "https://research.google/blog/rss/"),
    ("Hugging Face", "lab", "https://huggingface.co/blog/feed.xml"),
    ("Allen Institute for AI", "lab", "https://medium.com/feed/ai2-blog"),

    # Analise independente
    ("Epoch AI", "analise", "https://epochai.substack.com/feed"),
    ("Simon Willison", "analise", "https://simonwillison.net/atom/everything/"),
    ("Sebastian Raschka, Ahead of AI", "analise", "https://magazine.sebastianraschka.com/feed"),
    ("Import AI, Jack Clark", "analise", "https://importai.substack.com/feed"),
    ("Interconnects, Nathan Lambert", "analise", "https://www.interconnects.ai/feed"),
    ("Latent Space", "analise", "https://www.latent.space/feed"),

    # Midia
    ("MIT Technology Review, IA", "midia", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("Ars Technica, IA", "midia", "https://arstechnica.com/ai/feed/"),
    ("VentureBeat AI", "midia", "https://venturebeat.com/category/ai/feed/"),

    # Ferramentas e infra
    ("Model Context Protocol", "ferramenta", "https://blog.modelcontextprotocol.io/index.xml"),
    ("Weights and Biases", "ferramenta", "https://wandb.ai/fully-connected/rss.xml"),
]

# Fontes de alto valor que nao publicam RSS. Coleta por HTML.
# nome, categoria, url da pagina, padrao de href que conta como item
PAGINAS: list[tuple[str, str, str, str]] = [
    ("Anthropic Engineering", "lab", "https://www.anthropic.com/engineering", r"/engineering/[a-z0-9\-]+"),
    ("Anthropic News", "lab", "https://www.anthropic.com/news", r"/news/[a-z0-9\-]+"),
    ("Anthropic Research", "lab", "https://www.anthropic.com/research", r"/research/[a-z0-9\-]+"),
    ("Greenbook", "insights", "https://www.greenbook.org/insights", r"/insights/[a-z0-9\-/]+"),
    ("Research World, ESOMAR", "insights", "https://researchworld.com/articles", r"/articles/[a-z0-9\-]+"),
    ("Quirks", "insights", "https://www.quirks.com/articles", r"/articles/[a-z0-9\-]+"),
]

# Consultas do arXiv. Cada uma vira uma chamada a API.
ARXIV = [
    ("arXiv cs.AI", "cat:cs.AI"),
    ("arXiv cs.CL", "cat:cs.CL"),
    ("arXiv agentes", 'abs:"LLM agent" OR abs:"agentic"'),
    ("arXiv recuperacao", 'abs:"retrieval augmented" OR abs:"reranking"'),
]

PALAVRAS = [
    "agent", "agente", "harness", "skill", "context engineering", "mcp",
    "model context protocol", "embedding", "retrieval", "rag", "rerank",
    "benchmark", "leaderboard", "eval", "reinforcement", "rlvr", "reasoning",
    "raciocin", "open weight", "open-weight", "open source model", "llm",
    "multimodal", "distill", "fine-tun", "post-train", "inference cost",
    "synthetic", "sintetic", "insight", "market research", "pesquisa de mercado",
    "claude", "gpt-", "gemini", "llama", "qwen", "deepseek", "kimi", "mistral",
]

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def baixar(url: str) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            "Accept-Encoding": "gzip, identity",
        },
    )
    with urllib.request.urlopen(req, timeout=TEMPO_LIMITE, context=ctx) as resp:
        dados = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            dados = gzip.decompress(dados)
        return dados


def limpar(texto: str | None) -> str:
    if not texto:
        return ""
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"&[a-zA-Z#0-9]+;", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def ler_data(bruto: str | None) -> dt.datetime | None:
    if not bruto:
        return None
    bruto = bruto.strip()
    try:
        d = parsedate_to_datetime(bruto)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            d = dt.datetime.strptime(bruto.replace("Z", "+0000"), fmt)
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
    try:
        d = dt.datetime.fromisoformat(bruto.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def extrair(xml_bruto: bytes, fonte: str, categoria: str) -> list[dict]:
    try:
        raiz = ET.fromstring(xml_bruto)
    except ET.ParseError:
        raiz = ET.fromstring(xml_bruto.decode("utf-8", "ignore").encode("utf-8"))

    itens: list[dict] = []

    for item in raiz.iter():
        etiqueta = item.tag.split("}")[-1]
        if etiqueta not in ("item", "entry"):
            continue

        def campo(*nomes: str) -> str:
            for n in nomes:
                for filho in item:
                    if filho.tag.split("}")[-1] == n and (filho.text or "").strip():
                        return filho.text.strip()
            return ""

        titulo = limpar(campo("title"))

        link = campo("link")
        if not link:
            for filho in item:
                if filho.tag.split("}")[-1] == "link":
                    link = filho.attrib.get("href", "")
                    if link:
                        break
        if not link:
            link = campo("id", "guid")

        resumo = limpar(campo("description", "summary", "content", "encoded"))[:600]
        data = ler_data(campo("pubDate", "published", "updated", "date"))

        if titulo and link:
            itens.append({
                "fonte": fonte,
                "categoria": categoria,
                "titulo": titulo,
                "link": link,
                "data": data,
                "resumo": resumo,
            })

    return itens


def buscar_arxiv(nome: str, consulta: str, maximo: int = 40) -> list[dict]:
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query={urllib.parse.quote(consulta)}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={maximo}"
    )
    return extrair(baixar(url), nome, "paper")


def raspar_pagina(nome: str, categoria: str, url: str, padrao: str) -> list[dict]:
    """Coleta itens de uma pagina que nao publica RSS.

    Extrai ancoras cujo href casa com o padrao e usa o texto do link como titulo.
    Nao devolve data, entao o item nunca e cortado pela janela de tempo.
    """
    html = baixar(url).decode("utf-8", "ignore")
    base = "/".join(url.split("/")[:3])
    achados: list[dict] = []
    vistos: set[str] = set()

    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, texto = m.group(1), limpar(m.group(2))
        if not re.search(padrao, href):
            continue
        if len(texto) < 15:
            continue
        link = href if href.startswith("http") else base + href
        chave = link.split("?")[0].rstrip("/")
        if chave in vistos:
            continue

        # Listagens colam a data no texto do link, ora no fim, ora no comeco.
        # Ex.: "Harness design ... Mar 24, 2026" ou "Product Jul 24, 2026 Introducing ..."
        data = None
        m_data = re.search(
            r"(?:^|\s)((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4})(?:\s|$)",
            texto,
        )
        if m_data:
            data = ler_data(m_data.group(1))
            texto = (texto[: m_data.start()] + " " + texto[m_data.end():]).strip()

        # Tira rotulo de secao que a listagem gruda no titulo.
        texto = re.sub(
            r"^(Featured|Announcements?|Product|Policy|Science|Economics|"
            r"Interpretability|Alignment|Societal Impacts|Frontier Red Team|"
            r"Research|Engineering)\s+",
            "", texto,
        ).strip()

        # Corta link de navegacao, que costuma ser rotulo curto de categoria.
        if len(texto.split()) < 4:
            continue

        vistos.add(chave)
        achados.append({
            "fonte": nome,
            "categoria": categoria,
            "titulo": texto[:200],
            "link": link,
            "data": data,
            "resumo": "",
        })

    return achados


def relevante(item: dict) -> bool:
    alvo = (item["titulo"] + " " + item["resumo"]).lower()
    return any(p in alvo for p in PALAVRAS)


def verificar() -> int:
    print("Testando feeds\n")
    ok = 0
    for nome, _cat, url in FEEDS:
        try:
            itens = extrair(baixar(url), nome, _cat)
            if itens:
                print(f"  ok    {nome:38s} {len(itens):3d} itens")
                ok += 1
            else:
                print(f"  vazio {nome:38s} responde mas nao devolve item")
        except urllib.error.HTTPError as e:
            print(f"  HTTP  {nome:38s} {e.code}")
        except Exception as e:
            print(f"  erro  {nome:38s} {type(e).__name__}")
    print("\nTestando paginas sem RSS\n")
    for nome, cat, url, padrao in PAGINAS:
        try:
            itens = raspar_pagina(nome, cat, url, padrao)
            if itens:
                print(f"  ok    {nome:38s} {len(itens):3d} itens")
                ok += 1
            else:
                print(f"  vazio {nome:38s} nada casou com o padrao")
        except Exception as e:
            print(f"  erro  {nome:38s} {type(e).__name__}")

    print(f"\n{ok} de {len(FEEDS) + len(PAGINAS)} fontes funcionando")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Varredura de novidades em IA")
    p.add_argument("--dias", type=int, default=14, help="janela em dias")
    p.add_argument("--verificar", action="store_true", help="so testa os feeds")
    p.add_argument("--tudo", action="store_true", help="sem filtro de palavra chave")
    p.add_argument("--sem-arxiv", action="store_true", help="pula o arXiv")
    args = p.parse_args()

    if args.verificar:
        return verificar()

    SAIDA.mkdir(parents=True, exist_ok=True)
    corte = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.dias)
    coletados: list[dict] = []
    falhas: list[str] = []

    for nome, categoria, url in FEEDS:
        try:
            itens = extrair(baixar(url), nome, categoria)
            coletados.extend(itens)
            print(f"  {nome:38s} {len(itens):3d}")
        except Exception as e:
            falhas.append(f"{nome} ({type(e).__name__})")
            print(f"  {nome:38s} falhou, {type(e).__name__}")

    for nome, categoria, url, padrao in PAGINAS:
        try:
            itens = raspar_pagina(nome, categoria, url, padrao)
            coletados.extend(itens)
            print(f"  {nome:38s} {len(itens):3d}  (html)")
        except Exception as e:
            falhas.append(f"{nome} ({type(e).__name__})")
            print(f"  {nome:38s} falhou, {type(e).__name__}")

    if not args.sem_arxiv:
        for nome, consulta in ARXIV:
            try:
                itens = buscar_arxiv(nome, consulta)
                coletados.extend(itens)
                print(f"  {nome:38s} {len(itens):3d}")
            except Exception as e:
                falhas.append(f"{nome} ({type(e).__name__})")
                print(f"  {nome:38s} falhou, {type(e).__name__}")

    vistos: set[str] = set()
    final: list[dict] = []
    for item in coletados:
        chave = item["link"].split("?")[0].rstrip("/")
        if chave in vistos:
            continue
        if item["data"] and item["data"] < corte:
            continue
        if not args.tudo and not relevante(item):
            continue
        vistos.add(chave)
        final.append(item)

    final.sort(key=lambda i: i["data"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)

    hoje = dt.date.today().isoformat()
    caminho_csv = SAIDA / f"news-{hoje}.csv"
    with open(caminho_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["data", "fonte", "categoria", "titulo", "link", "resumo"])
        for i in final:
            w.writerow([
                i["data"].date().isoformat() if i["data"] else "",
                i["fonte"], i["categoria"], i["titulo"], i["link"], i["resumo"],
            ])

    caminho_md = SAIDA / f"news-{hoje}.md"
    with open(caminho_md, "w", encoding="utf-8") as fh:
        fh.write(f"# Digest de varredura, {hoje}\n\n")
        fh.write(f"Janela de {args.dias} dias. {len(final)} itens relevantes ")
        fh.write(f"de {len(coletados)} coletados.\n\n")
        if falhas:
            fh.write(f"Feeds que falharam: {', '.join(falhas)}\n\n")
        por_categoria: dict[str, list[dict]] = {}
        for i in final:
            por_categoria.setdefault(i["categoria"], []).append(i)
        for categoria in ("lab", "analise", "paper", "insights", "ferramenta", "midia"):
            grupo = por_categoria.get(categoria)
            if not grupo:
                continue
            fh.write(f"## {categoria}\n\n")
            for i in grupo:
                data = i["data"].date().isoformat() if i["data"] else "sem data"
                fh.write(f"- **{i['titulo']}**  \n")
                fh.write(f"  {i['fonte']}, {data}. [{i['link']}]({i['link']})\n")
                if i["resumo"]:
                    fh.write(f"  > {i['resumo'][:280]}\n")
                fh.write("\n")

    print(f"\n{len(final)} itens relevantes de {len(coletados)} coletados")
    print(f"CSV: {caminho_csv}")
    print(f"MD:  {caminho_md}")
    if falhas:
        print(f"Falharam: {', '.join(falhas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
