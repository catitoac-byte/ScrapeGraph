"""
Classificacao de qualidade de e-mail para priorizar prospeccao.

Duas dimensoes independentes:

  tipo     de quem e o dominio
             corporativo  dominio da propria empresa
             gratuito     gmail, hotmail e afins
             contador     escritorio contabil (comum no cadastro da Receita)

  alcance  quem le a caixa
             nominal   joao@empresa.com, chega a uma pessoa
             funcao    contato@empresa.com, chega a um time

O cruzamento com a validacao de DNS produz a camada (tier). Corporativo
nominal com MX ativo e o topo; gratuito fica abaixo porque costuma ser
e-mail pessoal do socio no cadastro fiscal, nao canal comercial, e porque
nenhum provedor gratuito permite verificar se a caixa existe.
"""

from __future__ import annotations

import re

from scraper_lab.validar_email import GRATUITOS, PAPEL

_CONTADOR = re.compile(r"contab|contad|escritorio|assessoria.?cont", re.I)

TIERS = {
    "A": "corporativo nominal",
    "B": "corporativo de funcao",
    "C": "gratuito",
    "D": "contador",
    "E": "sem e-mail ou invalido",
}


def tipo_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return ""
    if _CONTADOR.search(e):
        return "contador"
    return "gratuito" if e.split("@")[-1] in GRATUITOS else "corporativo"


def alcance(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return ""
    return "funcao" if e.split("@")[0].split("+")[0] in PAPEL else "nominal"


def tier(email: str, *, mx_ok: bool | None = None) -> str:
    """
    Camada de prioridade. mx_ok=False rebaixa para E, porque dominio que
    nao recebe e-mail invalida qualquer outra qualidade do endereco.
    """
    e = (email or "").strip().lower()
    if not e or "@" not in e or mx_ok is False:
        return "E"
    t = tipo_email(e)
    if t == "contador":
        return "D"
    if t == "gratuito":
        return "C"
    return "A" if alcance(e) == "nominal" else "B"
