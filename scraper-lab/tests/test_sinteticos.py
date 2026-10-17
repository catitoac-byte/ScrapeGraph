"""
Regressao do validador de citacoes da vertical sinteticos.

O validador e o que impede que uma citacao parafraseada passe por literal.
Ele precisa aceitar diferencas so tipograficas (aspas curvas, travessao,
espaco duro) e recusar qualquer mudanca de palavra.

Roda sob pytest e tambem direto:  python tests/test_sinteticos.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scraper_lab.sinteticos_paginas import Pagina, _analisar_html, citacao_confere, dominio  # noqa: E402

PAGINA = ("Aaru builds simulated populations grounded in real‑world behavior and outcomes.\n"
          "Read our accuracy benchmark across 2,993 questions — with an industry‑leading "
          "mean TVD of 7.62% and an MAE of 3.53%.")


def test_literal_exato():
    assert citacao_confere("Aaru builds simulated populations grounded in real-world behavior", PAGINA)


def test_tipografia_nao_conta():
    assert citacao_confere("across 2,993 questions - with an industry-leading mean TVD of 7.62%", PAGINA)
    assert citacao_confere("Aaru  builds simulated", PAGINA)


def test_parafrase_falha():
    assert not citacao_confere("Aaru builds simulated populations based on real-world behavior", PAGINA)
    assert not citacao_confere("aaru builds simulated populations", PAGINA)  # caixa conta


def test_fragmentos_em_ordem():
    assert citacao_confere("Aaru builds simulated populations ... mean TVD of 7.62%", PAGINA)
    assert not citacao_confere("mean TVD of 7.62% ... Aaru builds simulated populations", PAGINA)


def test_vazio_falha():
    assert not citacao_confere("", PAGINA)
    assert not citacao_confere("...", PAGINA)


def test_html_vira_texto_citavel():
    html = """<html><head><title>Aaru | Simulation</title>
    <meta name="description" content="Simulate what people will do before you decide.">
    <script>var x = "não é texto";</script></head>
    <body><h1>Simulate what people <b>will</b> do</h1>
    <p>Trusted by<br>EY and Accenture.</p><img alt="EY logo" src="x.png">
    <iframe src="https://www.youtube.com/embed/abc"></iframe></body></html>"""
    p = Pagina(url="https://aaru.com/")
    _analisar_html(p, html)
    t = p.texto_validacao()
    assert p.h1 == ["Simulate what people will do"]
    assert citacao_confere("Simulate what people will do before you decide.", t)
    assert citacao_confere("EY logo", t)
    assert citacao_confere("https://www.youtube.com/embed/abc", t)
    assert not citacao_confere("não é texto", p.texto)


def test_dominio():
    assert dominio("https://www.Aaru.com/pricing?x=1") == "aaru.com"
    assert dominio("aaru.com") == "aaru.com"


if __name__ == "__main__":
    falhas = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            try:
                f()
                print(f"ok   {nome}")
            except AssertionError:
                falhas += 1
                print(f"FALHA {nome}")
    sys.exit(1 if falhas else 0)
