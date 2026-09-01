"""
Integra a exportacao oficial de conexoes do LinkedIn do proprio usuario.

Nao ha scraping aqui: e o arquivo que o LinkedIn entrega ao titular da
conta pela funcao de exportacao de dados.

O valor esta em transformar lead frio em morno: onde a nossa base tem a
empresa e o usuario ja tem alguem la dentro, o contato deixa de ser
abordagem fria.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Cargos com poder de decisao sobre contratacao de pesquisa.
_DECISOR = re.compile(
    r"\b(ceo|chief executive|founder|co-?founder|fundador|s[oó]cio|owner|"
    r"propriet[aá]ri|president|presidente|managing director|diretor|director|"
    r"vp\b|vice[- ]president|head of|partner|s[oó]cio[- ]?diretor|"
    r"general manager|country manager|managing partner|cmo|cio|coo|cfo)\b", re.I)

# Sinais de que a pessoa atua com pesquisa, insights ou dados.
_AREA = re.compile(
    r"\b(insight|research|pesquisa|market intelligence|intelig[eê]ncia|"
    r"consumer|shopper|analytics|data|estrat[eé]gi|strategy|cx|ux)\b", re.I)

_RUIDO = re.compile(
    r"\b(ltda|s\.?a\.?|sa|me|epp|eireli|inc|llc|corp|corporation|group|grupo|"
    r"holding|company|co|the|and|e|de|da|do|dos|das)\b", re.I)


def normalizar(nome: str) -> str:
    t = unicodedata.normalize("NFKD", (nome or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", _RUIDO.sub(" ", t))


@dataclass
class Conexao:
    nome: str
    sobrenome: str
    url: str
    email: str
    empresa: str
    cargo: str
    conectado_em: str

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.sobrenome}".strip()

    @property
    def decisor(self) -> bool:
        return bool(_DECISOR.search(self.cargo))

    @property
    def da_area(self) -> bool:
        return bool(_AREA.search(self.cargo))


def carregar(caminho: Path) -> list[Conexao]:
    """
    Le o Connections.csv.

    O arquivo comeca com um aviso em texto livre antes do cabecalho real,
    entao localizamos a linha que inicia com "First Name," em vez de supor
    que o cabecalho esta na primeira linha.
    """
    linhas = caminho.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    try:
        i = next(n for n, l in enumerate(linhas) if l.startswith("First Name,"))
    except StopIteration:
        raise ValueError("cabecalho 'First Name,' nao encontrado no export")

    saida = []
    for r in csv.DictReader(io.StringIO("\n".join(linhas[i:]))):
        saida.append(Conexao(
            nome=(r.get("First Name") or "").strip(),
            sobrenome=(r.get("Last Name") or "").strip(),
            url=(r.get("URL") or "").strip(),
            email=(r.get("Email Address") or "").strip().lower(),
            empresa=(r.get("Company") or "").strip(),
            cargo=(r.get("Position") or "").strip(),
            conectado_em=(r.get("Connected On") or "").strip(),
        ))
    return saida


def indexar(conexoes: list[Conexao]) -> dict[str, list[Conexao]]:
    """
    Agrupa por empresa normalizada.

    Chaves muito curtas sao descartadas: "cx" ou "ia" casariam com dezenas
    de empresas diferentes e produziriam ligacao falsa.
    """
    idx: dict[str, list[Conexao]] = {}
    for c in conexoes:
        chave = normalizar(c.empresa)
        if len(chave) >= 5:
            idx.setdefault(chave, []).append(c)
    return idx
