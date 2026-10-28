"""Testes da camada de coleta do radar (sem rede: baixar e urlopen sao substituidos)."""

import io
import json
from datetime import date
from pathlib import Path

import pytest

from scraper_lab import radar
from scraper_lab import sinteticos_paginas as sp

HOJE = date(2026, 10, 27)


def rss(itens):
    corpo = "".join(
        f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate><description>{r}</description></item>"
        for t, u, d, r in itens)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{corpo}</channel></rss>'.encode()


def html(titulo, paragrafos, data="2026-10-20"):
    ps = "".join(f"<p>{p}</p>" for p in paragrafos)
    return (f'<html><head><title>{titulo}</title><meta property="article:published_time" content="{data}T10:00:00Z">'
            f'<meta property="og:site_name" content="Fonte Teste"></head><body><h1>{titulo}</h1>{ps}</body></html>').encode()


class RespostaFalsa:
    def __init__(self, dados, url, status=200):
        self._d, self.status, self._u = dados, status, url
        self.headers = {"Content-Type": "text/html"}

    def read(self, n=-1):
        return self._d

    def geturl(self):
        return self._u

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(sp.time, "sleep", lambda s: None)
    monkeypatch.setattr(radar.time, "sleep", lambda s: None)
    monkeypatch.setattr(sp, "PAUSA_DOMINIO", 0)


def fonte(url="https://f.test/feed", **kw):
    return radar.Fonte("Fonte Teste", "en", "rss", url, **kw)


# -- janela por data do item ------------------------------------------------

CASOS_JANELA = [
    ("dentro da janela", "Mon, 20 Oct 2026 10:00:00 +0000", 1),
    ("exatamente no limite de 90 dias", "Wed, 29 Jul 2026 10:00:00 +0000", 1),
    ("um dia antes do limite", "Tue, 28 Jul 2026 10:00:00 +0000", 0),
    ("ano passado", "Tue, 21 Jan 2025 10:51:03 +0000", 0),
    ("sem data", "", 0),
    ("data no futuro distante", "Mon, 20 Oct 2031 10:00:00 +0000", 0),
]


@pytest.mark.parametrize("nome,data,esperado", CASOS_JANELA, ids=[c[0] for c in CASOS_JANELA])
def test_item_de_feed_fora_da_janela_e_descartado(monkeypatch, tmp_path, nome, data, esperado):
    xml = rss([("Synthetic data", "https://f.test/a", data, "x")])
    monkeypatch.setattr(radar, "baixar", lambda url, **kw: {"status": 200, "motivo": "", "dados": xml, "content_type": "", "do_cache": False})
    r = radar.ler_fonte(fonte(), cache_dir=tmp_path, hoje=HOJE, janela_dias=90)
    assert len(r["itens"]) == esperado


def test_sitemap_usa_lastmod_e_indice_so_abre_filho_recente(monkeypatch, tmp_path):
    indice = (b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              b'<sitemap><loc>https://f.test/novo.xml</loc><lastmod>2026-10-25</lastmod></sitemap>'
              b'<sitemap><loc>https://f.test/velho.xml</loc><lastmod>2019-01-01</lastmod></sitemap></sitemapindex>')
    novo = (b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b'<url><loc>https://f.test/p1</loc><lastmod>2026-10-24T10:00:00Z</lastmod></url>'
            b'<url><loc>https://f.test/p2</loc><lastmod>2020-01-01</lastmod></url>'
            b'<url><loc>https://f.test/p3</loc></url></urlset>')
    pedidos = []

    def falso(url, **kw):
        pedidos.append(url)
        d = {"https://f.test/sitemap.xml": indice, "https://f.test/novo.xml": novo}.get(url)
        return {"status": 200 if d else 404, "motivo": "", "dados": d, "content_type": "", "do_cache": False}

    monkeypatch.setattr(radar, "baixar", falso)
    f = radar.Fonte("Fonte Teste", "en", "sitemap", "https://f.test/sitemap.xml")
    r = radar.ler_fonte(f, cache_dir=tmp_path, hoje=HOJE, janela_dias=90)
    assert [i["url"] for i in r["itens"]] == ["https://f.test/p1"]
    assert r["sem_data"] == 1 and r["fora_da_janela"] == 1
    assert "https://f.test/velho.xml" not in pedidos


# -- dedupe -----------------------------------------------------------------

CASOS_DEDUPE = [
    ("utm e barra final", ["https://f.test/a/?utm_source=x", "https://f.test/a", "https://F.test/a/"], 1),
    ("path diferente", ["https://f.test/a", "https://f.test/b"], 2),
    ("query que importa fica", ["https://f.test/a?id=1", "https://f.test/a?id=2"], 2),
]


@pytest.mark.parametrize("nome,urls,esperado", CASOS_DEDUPE, ids=[c[0] for c in CASOS_DEDUPE])
def test_dedupe_por_url_canonica(monkeypatch, tmp_path, nome, urls, esperado):
    xml = rss([("t", u, "Mon, 20 Oct 2026 10:00:00 +0000", "") for u in urls])
    monkeypatch.setattr(radar, "baixar", lambda url, **kw: {"status": 200, "motivo": "", "dados": xml, "content_type": "", "do_cache": False})
    r = radar.ler_fonte(fonte(), cache_dir=tmp_path, hoje=HOJE, janela_dias=90)
    assert len(r["itens"]) == esperado


# -- trechos ----------------------------------------------------------------

def pagina(texto):
    return sp.Pagina(url="https://f.test/a", estado="ok", texto=texto)


def test_trecho_por_palavra_chave_e_literal():
    voc = radar.compilar_termos(["synthetic", "gêmeo digital"])
    sinal = radar.compilar_termos(["survey finds", "launch"])
    texto = "\n".join([
        "Menu", "Home",
        "Quirk's launch of synthetic respondents drew attention across the research industry this autumn.",
        "The weather was fine and nothing else happened in the office during the afternoon of Tuesday.",
        "A new survey finds that buyers of",
        "synthetic data",
        "still want a human check before they sign off on any study that reaches the board.",
        "O gêmeo digital do consumidor virou tema de debate entre as empresas de pesquisa no Brasil.",
    ])
    p = pagina(texto)
    trechos = radar.extrair_trechos(p, voc, sinal)
    assert len(trechos) == 3
    assert not any("weather" in t for t in trechos)
    # parágrafo quebrado por link inline volta inteiro, e todo trecho é literal da página
    assert any(t.startswith("A new survey finds that buyers of synthetic data still want") for t in trechos)
    assert all(sp.citacao_confere(t, p.texto) for t in trechos)


def test_vocabulario_casa_acento_e_sufixo_mas_nao_meio_de_palavra():
    voc = radar.compilar_termos(["sintético", "synthetic"])
    assert radar.contar(voc, "Dados SINTETICOS e synthetically generated") == 2
    assert radar.contar(voc, "asynthetic") == 0


# -- conferir ---------------------------------------------------------------

def preparar_cache(tmp_path, texto, url="https://f.test/a"):
    cache = sp.CachePaginas(tmp_path)
    p = sp.Pagina(url=url, estado="ok", status=200, metodo="urllib", texto=texto, coletado_em="2026-10-27T00:00:00+00:00")
    cache._guardar(p)
    return cache


def sinais(valor, url="https://f.test/a"):
    return {"sinais": [{"id": "s1", "evidencias": [{"url": url, "valor": valor}]}]}


CASOS_CONFERIR = [
    ("citação presente", "Buyers said it was “not ready”   for prime time.", "Buyers said it was \"not ready\" for prime time.", 0),
    ("aspas tipográficas na citação", 'The CEO said "we are all in" on synthetic data.', "The CEO said “we are all in” on synthetic data.", 0),
    ("apóstrofo tipográfico", "It's a hype cycle, said Marta.", "It’s a hype cycle", 0),
    ("citação ausente", "Nothing to see here.", "Synthetic data is 90% accurate", 1),
    ("citação alterada em uma palavra", "Synthetic data is 80% accurate", "Synthetic data is 90% accurate", 1),
    ("reticências marcam fragmentos em ordem", "AAA bbb CCC ddd EEE", "AAA ... EEE", 0),
    ("fragmentos fora de ordem", "AAA bbb CCC ddd EEE", "EEE ... AAA", 1),
]


@pytest.mark.parametrize("nome,pagina_txt,valor,violacoes", CASOS_CONFERIR, ids=[c[0] for c in CASOS_CONFERIR])
def test_conferir(tmp_path, nome, pagina_txt, valor, violacoes):
    cache = tmp_path / "cache"
    preparar_cache(cache, pagina_txt)
    arq = tmp_path / "sinais.json"
    arq.write_text(json.dumps(sinais(valor), ensure_ascii=False), encoding="utf-8")
    res = radar.conferir(arq, cache_dir=cache)
    assert len(res["violacoes"]) == violacoes
    assert res["ok"] == (violacoes == 0)
    assert (tmp_path / "sinais.json.conferencia.json").exists()


def test_conferir_sem_cache_abre_a_pagina_e_sem_url_procura_no_cache(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.setattr(sp, "permitido", lambda *a, **k: True)
    monkeypatch.setattr(sp, "urlopen", lambda req, timeout=0: RespostaFalsa(html("T", ["Synthetic panels cut cost by half in this pilot study of retail shoppers."]), req.full_url))
    arq = tmp_path / "s.json"
    arq.write_text(json.dumps(sinais("Synthetic panels cut cost by half", url="https://novo.test/p")), encoding="utf-8")
    assert radar.conferir(arq, cache_dir=cache)["ok"]
    sem_url = {"sinais": [{"id": "s", "evidencias": [{"valor": "Synthetic panels cut cost by half"}, {"valor": "texto que ninguém escreveu"}]}]}
    arq.write_text(json.dumps(sem_url), encoding="utf-8")
    res = radar.conferir(arq, cache_dir=cache)
    assert [v["evidencia"] for v in res["violacoes"]] == [1]


def test_conferir_pagina_bloqueada_e_violacao(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "permitido", lambda *a, **k: False)
    arq = tmp_path / "s.json"
    arq.write_text(json.dumps(sinais("qualquer coisa", url="https://fechado.test/x")), encoding="utf-8")
    res = radar.conferir(arq, cache_dir=tmp_path / "c")
    assert not res["ok"] and "not accessible" in res["violacoes"][0]["motivo"]


# -- robots -----------------------------------------------------------------

def test_robots_proibe_vira_bloqueado_e_nao_candidato(monkeypatch, tmp_path):
    from scraper_lab.robots import Robots

    regras = Robots("User-agent: *\nDisallow: /privado/\n")
    monkeypatch.setattr(sp, "permitido", lambda url, **k: regras.permite(url))
    chamadas = []
    monkeypatch.setattr(sp, "urlopen", lambda req, timeout=0: (chamadas.append(req.full_url), RespostaFalsa(html("Aberta", ["Synthetic respondents reshape the market research industry, says a new report from the field."]), req.full_url))[1])
    feed = rss([("Synthetic A", "https://f.test/privado/a", "Mon, 20 Oct 2026 10:00:00 +0000", "synthetic"),
                ("Synthetic B", "https://f.test/publico/b", "Mon, 20 Oct 2026 10:00:00 +0000", "synthetic")])
    monkeypatch.setattr(radar, "baixar", lambda url, **kw: {"status": 200, "motivo": "", "dados": feed, "content_type": "", "do_cache": False})
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"fontes_feeds": [{"publicador": "F", "idioma": "en", "tipo": "rss", "url": "https://f.test/feed"}],
                               "consultas": {"synthetic": {"en": ["synthetic respondents"]}},
                               "vocabulario": {"synthetic": ["synthetic"]}}), encoding="utf-8")
    doc = radar.coletar(cfg, "synthetic", 90, tmp_path / "out", hoje=HOJE, cache_dir=tmp_path / "cache", log=lambda *a: None)
    assert [c["url"] for c in doc["candidatos"]] == ["https://f.test/publico/b"]
    assert [b["url"] for b in doc["meta"]["bloqueados"]] == ["https://f.test/privado/a"]
    assert doc["meta"]["bloqueados"][0]["estado"] == "not accessible"
    assert all("privado" not in u for u in chamadas)
    gravado = json.loads((tmp_path / "out" / "candidatos-synthetic.json").read_text(encoding="utf-8"))
    assert gravado["meta"]["categoria"] == "synthetic" and gravado["meta"]["janela_dias"] == 90
    c = gravado["candidatos"][0]
    assert set(["url", "publicador", "titulo", "data_pagina", "idioma", "consulta_ou_feed", "trechos", "cache_path"]) <= set(c)
    assert Path(c["cache_path"]).exists()


def test_feed_proibido_por_robots_nao_e_baixado(monkeypatch, tmp_path):
    monkeypatch.setattr(radar, "permitido", lambda *a, **k: False)
    monkeypatch.setattr(radar, "urlopen", lambda *a, **k: pytest.fail("não podia abrir"))
    r = radar.baixar("https://f.test/feed", cache_dir=tmp_path)
    assert r["dados"] is None and "robots" in r["motivo"]


# -- config -----------------------------------------------------------------

CASOS_CONFIG = [
    ("sem fontes_feeds", {"consultas": {"synthetic": {"en": ["synthetic data"]}}, "vocabulario": {"synthetic": ["synthetic"]}}, "fontes_feeds", 0),
    ("sem consultas", {"fontes_feeds": [{"publicador": "F", "idioma": "en", "url": "https://f.test/feed"}], "vocabulario": {"synthetic": ["synthetic"]}}, "consultas", 1),
    ("sem vocabulario deriva das consultas", {"fontes_feeds": [], "consultas": {"synthetic": {"en": ["synthetic respondents survey"]}}}, "vocabulario", 0),
    ("fonte sem idioma e fonte sem url", {"fontes_feeds": [{"publicador": "A", "url": "https://a.test/feed"}, {"publicador": "B"}],
                                          "consultas": {"synthetic": ["x y z"]}, "vocabulario": {"synthetic": ["x"]}}, "idioma", 1),
]


@pytest.mark.parametrize("nome,conteudo,trecho_aviso,n_fontes", CASOS_CONFIG, ids=[c[0] for c in CASOS_CONFIG])
def test_config_com_chave_ausente_avisa_e_segue(tmp_path, nome, conteudo, trecho_aviso, n_fontes):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps(conteudo), encoding="utf-8")
    cfg = radar.carregar_config(arq, "synthetic")
    assert any(trecho_aviso in a for a in cfg.avisos)
    assert len(cfg.fontes) == n_fontes
    assert cfg.sinais  # padrão do projeto quando o config não traz termos_de_sinal
    assert cfg.vocabulario


def test_config_aceita_fontes_em_dicionario_e_feed_com_sitemap(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps({"fontes_feeds": {"Pub": {"idioma": "pt", "feed": "https://p.test/feed", "sitemap": "https://p.test/sitemap.xml"}},
                               "consultas": {"synthetic": {"pt": ["a b c"]}}, "vocabulario": {"synthetic": {"pt": ["sintético"]}}}), encoding="utf-8")
    cfg = radar.carregar_config(arq, "synthetic")
    assert sorted(f.tipo for f in cfg.fontes) == ["auto", "sitemap"]
    assert all(f.publicador == "Pub" and f.idioma == "pt" for f in cfg.fontes)
    assert cfg.vocabulario == ["sintético"]
