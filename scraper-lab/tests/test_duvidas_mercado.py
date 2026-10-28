"""
Regressao da vertical duvidas_mercado: validador de citacao literal, schema,
dedupe, teto de buscas e retomada pelo cache de paginas.

Roda sob pytest:  uv run pytest tests/test_duvidas_mercado.py
"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scraper_lab import duvidas_mercado as dm  # noqa: E402
from scraper_lab import sinteticos_paginas as sp  # noqa: E402

URL = "https://exemplo.org/artigo-qa"
TEXTO = ("How do you test every path of an online survey before fieldwork starts?\n"
         "Teams say checking skip logic by hand is time-consuming and error-prone for long questionnaires.")


@pytest.fixture
def corrida(tmp_path):
    cfg = dm.carregar_config()
    cfg["_cache"] = tmp_path / "cache"
    cfg["_saida"] = tmp_path / "saida"
    cfg["clientes_nunca_citar"] = str(tmp_path / "nao-existe.json")
    c = dm.Corrida(cfg, saida=tmp_path / "saida", teto_buscas=10)
    c.proibidos = ["Marca Secreta"]
    pag = sp.Pagina(url=URL, url_final=URL, estado="ok", status=200, metodo="urllib",
                    coletado_em="2026-10-27T10:00:00+00:00", titulo="QA de survey", texto=TEXTO)
    c.paginas._guardar(pag)
    return c


def achado(**kw):
    a = {
        "id": "survey-qa-001", "varredura": "P1",
        "pergunta_ou_fala": {"valor": "How do you test every path of an online survey before fieldwork starts?",
                             "tipo": "literal", "url": URL, "data_pagina": "2026-05-30", "data_captura": "2026-10-27"},
        "pt": {"valor": "Como testar cada caminho de uma pesquisa online antes do campo?", "tipo": "traducao_livre"},
        "quem": "Exemplo", "papel": "Veículo do setor", "grupo": "comentarista", "idioma": "en",
        "tema": "dúvida sobre teste de questionário", "potencial_video": "alto",
        "angulo_video": "Antes do campo, alguém testa cada caminho do questionário. Hoje isso é manual e lento.",
    }
    a.update(kw)
    return a


def doc(achados, **meta):
    m = {"produto": "survey-qa", "data_captura": "2026-10-27", "buscas_usadas": 4, "teto_buscas": 10,
         "metodo": "Teste de método com mais de vinte caracteres.", "bloqueados": []}
    m.update(meta)
    return {"meta": m, "achados": achados,
            "sintese": {"top_perguntas": [a["id"] for a in achados][:1],
                        "lacunas": ["Poucos achados neste teste."],
                        "nota": "Ranking inferido, sem busca nova."}}


def regras(corrida, d):
    return {x["regra"] for x in dm.validar(d, corrida)["violacoes"]}


def trocar(a, **campos):
    a = copy.deepcopy(a)
    a["pergunta_ou_fala"].update(campos)
    return a


# --- tabela de casos do validador ------------------------------------------------

def test_schema_valido_passa(corrida):
    assert dm.validar(doc([achado()]), corrida)["violacoes"] == []


CASOS_REPROVA = [
    ("citacao ausente da pagina",
     lambda: achado(pergunta_ou_fala={"valor": "How do you test every path of a survey before launch?", "tipo": "literal",
                                      "url": URL, "data_pagina": "2026", "data_captura": "2026-10-27"}),
     "citacao_ausente_da_pagina"),
    ("pagina nunca guardada",
     lambda: trocar(achado(), url="https://outro.org/nunca-aberta"),
     "pagina_nao_guardada"),
    ("url vazia", lambda: trocar(achado(), url=""), "schema"),
    ("url sem http", lambda: trocar(achado(), url="exemplo.org/artigo-qa"), "schema"),
    ("grupo fora do enum", lambda: achado(grupo="cliente"), "schema"),
    ("varredura fora do enum", lambda: achado(varredura="P5"), "schema"),
    ("potencial fora do enum", lambda: achado(potencial_video="altissimo"), "schema"),
    ("tipo diferente de literal", lambda: trocar(achado(), tipo="inferido"), "schema"),
    ("travessao em texto nosso", lambda: achado(tema="dúvida — teste"), "pontuacao_ou_contraste"),
    ("contraste proibido", lambda: achado(angulo_video="Isso não é questão de prazo, é questão de método de teste."),
     "pontuacao_ou_contraste"),
    ("preco no angulo", lambda: achado(angulo_video="Hoje o teste é manual e custa R$ 500 por estudo realizado."),
     "valor_ou_gratuidade"),
    ("data de pagina invalida", lambda: trocar(achado(), data_pagina="maio de 2026"), "data_pagina"),
    ("nome de cliente", lambda: achado(quem="Marca Secreta"), "nome_proibido"),
]


@pytest.mark.parametrize("nome,fabrica,regra", CASOS_REPROVA, ids=[c[0] for c in CASOS_REPROVA])
def test_reprova(corrida, nome, fabrica, regra):
    assert regra in regras(corrida, doc([fabrica()]))


def test_citacao_com_aspas_e_travessao_tipograficos_passa(corrida):
    corrida.paginas._guardar(sp.Pagina(url="https://exemplo.org/b", url_final="https://exemplo.org/b", estado="ok",
                                       coletado_em="2026-10-27T10:00:00+00:00",
                                       texto="Teams say it’s time-consuming – and risky."))
    a = trocar(achado(), url="https://exemplo.org/b", valor="Teams say it's time-consuming - and risky.")
    assert dm.validar(doc([a]), corrida)["violacoes"] == []


def test_id_repetido_e_top_perguntas_inexistente(corrida):
    d = doc([achado(), achado(pergunta_ou_fala=achado()["pergunta_ou_fala"] | {"valor": "Teams say checking skip logic by hand"})])
    assert "ids_unicos" in regras(corrida, d)
    d2 = doc([achado()])
    d2["sintese"]["top_perguntas"] = ["survey-qa-099"]
    assert "top_perguntas" in regras(corrida, d2)


def test_teto_de_buscas_excedido(corrida):
    assert "teto_de_buscas" in regras(corrida, doc([achado()], buscas_usadas=11))


def test_minimo_sem_lacuna_reprova_e_com_lacuna_avisa(corrida):
    d = doc([achado()])
    d["sintese"]["lacunas"] = []
    assert "minimo_de_achados" in regras(corrida, d)
    r = dm.validar(doc([achado()]), corrida)
    assert r["violacoes"] == [] and any("menos de 12" in x for x in r["avisos"])


# --- dedupe, extracao, tetos -----------------------------------------------------

def test_dedupe_por_url_e_citacao(corrida):
    d = doc([achado(), achado(id="survey-qa-002")])
    assert "duplicado" in regras(corrida, d)
    achados, descartados = dm.extrair_achados(corrida, "survey-qa", [corrida.paginas.obter(URL)] * 2)
    textos = [a["pergunta_ou_fala"]["valor"] for a in achados]
    assert len(textos) == len(set(textos))


def test_extracao_so_produz_citacao_literal(corrida):
    pag = corrida.paginas.obter(URL)
    achados, _ = dm.extrair_achados(corrida, "survey-qa", [pag])
    assert achados, "a pagina tem uma pergunta e uma dor relevantes"
    assert {a["varredura"] for a in achados} >= {"P1"}
    for a in achados:
        assert sp.citacao_confere(a["pergunta_ou_fala"]["valor"], pag.texto_validacao())
        assert a["pergunta_ou_fala"]["url"] == URL


def test_nome_de_cliente_na_citacao_descarta_o_achado(corrida):
    pag = corrida.paginas.obter(URL)
    pag.texto = "How does Marca Secreta test every path of an online survey before fieldwork?"
    pag.__dict__.pop("_frases", None)
    achados, descartados = dm.extrair_achados(corrida, "survey-qa", [pag])
    assert achados == [] and descartados["nome_proibido"] == 1


def test_tetos_somam_o_total():
    cfg = dm.carregar_config()
    for total in (4, 10, 17, 30, 99):
        t = dm.tetos_por_varredura(cfg, total)
        assert sum(t.values()) == min(total, 30)
        assert all(t[v] <= cfg["teto_buscas_por_varredura"][v] for v in t)


def test_registro_respeita_teto_e_so_conta_busca_nova(corrida):
    reg = corrida.buscas
    res = [{"url": URL, "titulo": "t"}]
    for i in range(corrida.tetos["P1"]):
        reg.registrar("survey-qa", "P1", f"q{i}", "en", res, corrida.tetos["P1"], corrida.teto_total)
    with pytest.raises(dm.TetoDeBuscas):
        reg.registrar("survey-qa", "P1", "q-extra", "en", res, corrida.tetos["P1"], corrida.teto_total)
    reg.registrar("survey-qa", "P1", "q0", "en", res, corrida.tetos["P1"], corrida.teto_total)  # repetir nao conta
    assert reg.usadas("survey-qa", "P1") == corrida.tetos["P1"]


# --- retomada --------------------------------------------------------------------

def test_retomada_nao_refaz_pagina_em_cache(corrida, monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("rede acionada para pagina que ja esta em cache")

    monkeypatch.setattr(sp, "urlopen", proibido)
    corrida.buscas.registrar("survey-qa", "P1", "survey qa test", "en", [{"url": URL}],
                             corrida.tetos["P1"], corrida.teto_total)
    paginas = dm.abrir_paginas(corrida, "survey-qa")
    assert [p.url for p in paginas] == [URL]
    assert corrida.paginas.stats["do_cache"] == 1 and corrida.paginas.stats["abertas_agora"] == 0


def test_segunda_corrida_do_produto_reproduz_o_mesmo_resultado(corrida, monkeypatch):
    monkeypatch.setattr(sp, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rede")))
    corrida.buscas.registrar("survey-qa", "P1", "q", "en", [{"url": URL}], corrida.tetos["P1"], corrida.teto_total)
    a = dm.montar_produto(corrida, "survey-qa")
    b = dm.montar_produto(corrida, "survey-qa")
    assert a["achados"] == b["achados"] and a["meta"]["buscas_usadas"] == 1
    assert dm.validar(a, corrida)["violacoes"] == []


def test_pagina_bloqueada_vira_not_accessible_sem_nova_tentativa(corrida):
    corrida.paginas._guardar(sp.Pagina(url="https://g2.com/x", estado="not accessible", status=403, motivo="HTTP 403",
                                       coletado_em="2026-10-27T10:00:00+00:00"))
    corrida.buscas.registrar("survey-qa", "P1", "q", "en", [{"url": "https://g2.com/x"}], corrida.tetos["P1"], corrida.teto_total)
    d = dm.montar_produto(corrida, "survey-qa")
    assert any("not accessible" in b and "g2.com" in b for b in d["meta"]["bloqueados"])
    assert corrida.paginas.stats["abertas_agora"] == 0
