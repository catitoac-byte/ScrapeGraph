"""
Extrator do diretorio de filiados da ABEP (abep.org/diretorio-dos-filiados).

Diferente da Esomar, as paginas sao renderizadas no servidor, entao nao
precisamos de navegador: HTTP puro resolve e a coleta cai de horas para
minutos. O unico obstaculo e o e-mail, ofuscado pelo Cloudflare, que
decodificamos a partir do atributo data-cfemail.

A ABEP nao publica pessoas de contato, so o canal da empresa. A coluna
`contatos` sai vazia de proposito, para manter o mesmo formato da Esomar.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

DIRETORIO = "https://abep.org/diretorio-dos-filiados/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Todo filiado da ABEP e brasileiro. Usamos o nome em ingles para casar com
# a nomenclatura da base Esomar e permitir juntar as duas.
PAIS = "Brazil"

_VAZIOS = {"", "n/a", "na", "-", "--"}
_ESPACOS = re.compile(r"\s+")

# Rotulo no site -> campo do registro
_CAMPOS = {
    "tipo de empresa": "tipo_empresa",
    "endereço": "endereco",
    "endereco": "endereco",
    "telefone": "telefone",
    "e-mail": "email",
    "email": "email",
    "site": "site",
    "campos de atuação": "campos_atuacao",
    "métodos e técnicas": "metodos_tecnicas",
    "outros serviços": "outros_servicos",
}


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", texto or "").strip()
    return "" if t.lower() in _VAZIOS else t


def _baixar(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def decodifica_cfemail(hexstr: str) -> str:
    """
    Reverte a ofuscacao de e-mail do Cloudflare.

    O primeiro byte da string hex e a chave; cada byte seguinte, aplicado
    XOR com ela, devolve um caractere do endereco.
    """
    try:
        b = bytes.fromhex(hexstr)
        chave = b[0]
        return "".join(chr(x ^ chave) for x in b[1:])
    except Exception:
        return ""


@dataclass
class Filiado:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    uf: str = ""
    tipo_empresa: str = ""
    campos_atuacao: str = ""
    metodos_tecnicas: str = ""
    outros_servicos: str = ""
    coletado_em: str = ""
    erro: str = ""


# Endereco termina com "<Cidade> <UF>", ex.: "... São Paulo SP"
_UF = re.compile(r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|"
                 r"RJ|RN|RS|RO|RR|SC|SP|SE|TO)\s*$")


def _uf_do_endereco(endereco: str) -> str:
    m = _UF.search(endereco.strip())
    return m.group(1) if m else ""


def listar_filiados() -> list[str]:
    """URLs de perfil, sem repeticao, na ordem de ID."""
    html = _baixar(DIRETORIO)
    urls = set(re.findall(r'href="(https://abep\.org/filiado/\d+)"', html))
    return sorted(urls, key=lambda u: int(u.rsplit("/", 1)[1]))


def extrair_filiado(html: str, url: str) -> Filiado:
    reg = Filiado(url_perfil=url, coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")
    bloco = sopa.find("div", class_="area-texto")
    if bloco is None:
        reg.erro = "bloco area-texto ausente"
        return reg

    titulo = bloco.find("h3")
    reg.nome = _limpar(titulo.get_text() if titulo else "")

    for p in bloco.find_all("p"):
        rotulo_el = p.find("b")
        if not rotulo_el:
            continue
        rotulo = _limpar(rotulo_el.get_text()).rstrip(":").lower()
        campo = _CAMPOS.get(rotulo)
        if not campo:
            continue

        if campo == "email":
            oculto = p.find("a", class_="__cf_email__")
            if oculto and oculto.get("data-cfemail"):
                reg.email = decodifica_cfemail(oculto["data-cfemail"])
            else:
                link = p.find("a", href=re.compile(r"^mailto:", re.I))
                reg.email = link["href"][7:].split("?")[0] if link else ""
            continue

        if campo == "site":
            link = p.find("a", href=True)
            valor = link["href"] if link else p.get_text()
            # texto do link costuma ser mais limpo que o href
            reg.site = _limpar(link.get_text()) if link else _limpar(valor)
            continue

        # demais campos: texto do <p> sem o rotulo
        rotulo_el.extract()
        setattr(reg, campo, _limpar(p.get_text()))

    reg.uf = _uf_do_endereco(reg.endereco)
    return reg


def coletar(urls: list[str], *, delay: float = 1.0, verbose: bool = True) -> list[Filiado]:
    filiados: list[Filiado] = []
    for i, url in enumerate(urls, 1):
        try:
            reg = extrair_filiado(_baixar(url), url)
        except Exception as exc:
            reg = Filiado(url_perfil=url, erro=f"{type(exc).__name__}: {exc}"[:150],
                          coletado_em=datetime.now(timezone.utc).isoformat())
        filiados.append(reg)
        if verbose:
            marca = "!" if reg.erro else "."
            print(f"  [{i:>3}/{len(urls)}] {marca} {reg.nome[:38]:38} | "
                  f"{reg.email[:30]:30} | {reg.uf}")
        if i < len(urls):
            time.sleep(delay)
    return filiados


# O banco da ABEP contem registros que nao sao empresas: o texto de estado
# vazio do proprio site, uma entrada de teste e a desenvolvedora do site
# (endereco com digitacao aleatoria e "site" apontando para a propria ABEP).
_NAO_EMPRESAS = {"nenhum resultado encontrado!", "teste", "marcasites"}


def eh_empresa(f: Filiado) -> bool:
    """Descarta placeholders e registros de teste do diretorio."""
    if not f.nome or f.nome.strip().lower() in _NAO_EMPRESAS:
        return False
    # sem nenhum canal de contato nao ha registro util
    return bool(f.email or f.telefone or f.site)


COLUNAS = [
    "nome", "email", "site", "pais", "uf", "telefone", "endereco",
    "tipo_empresa", "campos_atuacao", "metodos_tecnicas", "outros_servicos",
    "url_perfil", "erro",
]


def exportar(filiados: list[Filiado], nome: str = "abep") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(f) for f in filiados], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for f in filiados:
            d = asdict(f)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
