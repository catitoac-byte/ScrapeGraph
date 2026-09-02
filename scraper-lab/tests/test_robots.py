"""
Regressao do verificador de robots.txt.

O caso que motivou este arquivo: researchsociety.com.au serve o robots.txt
em UTF-8 com BOM. O U+FEFF sobrevive ao str.strip(), a primeira chave virava
"﻿user-agent", o grupo inteiro era descartado e o site que proibe tudo
passava a ser lido como liberado. Falha silenciosa e no pior sentido: o
verificador dizia sim justamente onde o dono do site diz nao.

Roda sob pytest e tambem direto:  python tests/test_robots.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scraper_lab.robots import Robots  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

BOM = "﻿"

# Recorte fiel do arquivo real, com os dois grupos "User-agent: *" que ele tem.
RESEARCHSOCIETY = """User-agent: *
Disallow: /*  # Disallow everything

# Allow favicon.ico with wildcard for directory segment
Allow: /public/*/website/favicon.ico

User-agent: Googlebot
Disallow: /public/
Allow: /public/*/website/favicon.ico
Allow: /
Crawl-delay: 10

User-agent: *
Disallow: /setup*
"""


def _vereditos(texto: str) -> dict[str, bool]:
    r = Robots(texto, UA)
    base = "https://www.researchsociety.com.au"
    return {c: r.permite(base + c) for c in (
        "/", "/find-a-provider", "/documents/item/1",
        "/public/x/website/favicon.ico")}


def test_bom_nao_descarta_o_primeiro_grupo():
    """O bug original: com BOM o Disallow do primeiro grupo sumia."""
    assert _vereditos(BOM + RESEARCHSOCIETY) == _vereditos(RESEARCHSOCIETY)


def test_site_que_proibe_tudo_e_lido_como_proibido():
    esperado = {"/": False,
                "/find-a-provider": False,
                "/documents/item/1": False,
                "/public/x/website/favicon.ico": True}
    assert _vereditos(BOM + RESEARCHSOCIETY) == esperado


def test_bom_sobrevive_a_decodificacao_ingenua():
    """
    _buscar ja usa utf-8-sig, mas kora.py, mrsi.py e jmra.py montam
    Robots(texto, agente) por conta propria com utf-8 puro. O parser precisa
    aguentar o BOM sozinho, sem depender de quem decodificou.
    """
    bruto = (BOM + RESEARCHSOCIETY).encode("utf-8")
    ingenuo = bruto.decode("utf-8", errors="replace")     # preserva o BOM
    limpo = bruto.decode("utf-8-sig", errors="replace")   # descarta o BOM
    assert BOM in ingenuo and BOM not in limpo
    assert _vereditos(ingenuo) == _vereditos(limpo)


def test_bom_com_crlf():
    texto = BOM + RESEARCHSOCIETY.replace("\n", "\r\n")
    assert _vereditos(texto) == _vereditos(RESEARCHSOCIETY)


def test_bom_nao_quebra_agentes_bloqueados():
    r = Robots(BOM + "User-agent: BadBot\nDisallow: /\n", UA)
    assert r.agentes_bloqueados == ["badbot"]


def test_arquivo_sem_bom_nao_mudou():
    """Controle: o que ja funcionava tem que continuar identico."""
    r = Robots("User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n", UA)
    assert r.permite("https://x/") is True
    assert r.permite("https://x/wp-admin/") is False
    assert r.permite("https://x/wp-admin/admin-ajax.php") is True


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except AssertionError as exc:
                falhas += 1
                print(f"  FALHA {nome}: {exc}")
    print(f"\n{falhas} falha(s)")
    sys.exit(1 if falhas else 0)
