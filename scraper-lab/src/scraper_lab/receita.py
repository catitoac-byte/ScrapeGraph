"""
Extrator do Cadastro Nacional da Pessoa Juridica (dados abertos da Receita).

Por que esta fonte importa: as associacoes cobrem uma fracao pequena do
mercado. O CNAE 7320-3/00 ("Pesquisas de mercado e de opiniao publica") e
o registro oficial de toda empresa do setor no pais.

Acesso: o portal e um Nextcloud publico que exige JavaScript, porem expoe
o WebDAV padrao, por onde baixamos sem navegador.

Estrategia de disco: cada zip e baixado, filtrado em fluxo e apagado. O pico
fica no maior arquivo (2,2 GB) em vez dos 6,7 GB do conjunto.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import zipfile
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"
TEMP = RAIZ / "dados" / "temp_rf"

TOKEN = "gn672Ad4CF8N6TK"
WEBDAV = ("https://arquivos.receitafederal.gov.br/public.php/webdav"
          "/Dados/Cadastros/CNPJ/{mes}/{arquivo}")

CNAE_PESQUISA = "7320300"
SITUACAO_ATIVA = "02"

# Layout dos CSV da Receita (sem cabecalho, ';' e latin-1).
EST = {"cnpj_basico": 0, "cnpj_ordem": 1, "cnpj_dv": 2, "matriz_filial": 3,
       "nome_fantasia": 4, "situacao": 5, "data_situacao": 6,
       "inicio_atividade": 10, "cnae_principal": 11, "cnae_secundaria": 12,
       "tipo_logradouro": 13, "logradouro": 14, "numero": 15,
       "complemento": 16, "bairro": 17, "cep": 18, "uf": 19, "municipio": 20,
       "ddd1": 21, "tel1": 22, "ddd2": 23, "tel2": 24, "email": 27}
EMP = {"cnpj_basico": 0, "razao_social": 1, "natureza": 2,
       "capital": 4, "porte": 5}

PORTE = {"00": "Nao informado", "01": "Micro empresa",
         "03": "Pequeno porte", "05": "Demais"}

SOC = {"cnpj_basico": 0, "tipo": 1, "nome": 2, "cpf_cnpj": 3,
       "qualificacao": 4, "data_entrada": 5, "faixa_etaria": 10}

# Qualificacoes que indicam quem decide na empresa. O alvo de contato e o
# socio-administrador; socio sem poder de gestao entra como secundario.
QUALIFICACAO = {
    "05": "Administrador", "08": "Conselheiro de Administracao",
    "10": "Diretor", "16": "Presidente", "17": "Procurador",
    "22": "Socio", "23": "Socio Capitalista", "24": "Socio Comanditado",
    "28": "Socio-Gerente", "29": "Socio Incapaz ou Relativamente Incapaz",
    "30": "Socio Menor", "31": "Socio Ostensivo", "37": "Socio Pessoa Juridica",
    "38": "Socio Pessoa Fisica", "47": "Socio Pessoa Fisica Residente Exterior",
    "48": "Socio Pessoa Juridica Domiciliado Exterior",
    "49": "Socio-Administrador", "52": "Socio com Capital",
    "54": "Fundador", "59": "Produtor Rural", "65": "Titular Pessoa Fisica",
}
DECISORES = {"49", "05", "16", "10", "28", "31", "65", "54"}
FAIXA_ETARIA = {"1": "0-12", "2": "13-20", "3": "21-30", "4": "31-40",
                "5": "41-50", "6": "51-60", "7": "61-70", "8": "71-80",
                "9": "80+", "0": "nao informada"}


@dataclass
class Socio:
    cnpj_basico: str
    nome: str = ""
    qualificacao: str = ""
    decisor: bool = False
    tipo: str = ""          # pessoa fisica ou juridica
    data_entrada: str = ""
    faixa_etaria: str = ""


def filtrar_socios(zip_path: Path, bases: set[str]) -> list["Socio"]:
    """Socios das empresas que nos interessam, pelo CNPJ base."""
    achados: list[Socio] = []
    for c in _linhas(zip_path):
        if len(c) <= SOC["qualificacao"]:
            continue
        base = c[SOC["cnpj_basico"]]
        if base not in bases:
            continue
        q = c[SOC["qualificacao"]].strip()
        tipo = {"1": "juridica", "2": "fisica", "3": "estrangeiro"}.get(
            c[SOC["tipo"]].strip(), "")
        faixa = (FAIXA_ETARIA.get(c[SOC["faixa_etaria"]].strip(), "")
                 if len(c) > SOC["faixa_etaria"] else "")
        achados.append(Socio(
            cnpj_basico=base,
            nome=c[SOC["nome"]].strip(),
            qualificacao=QUALIFICACAO.get(q, q),
            decisor=q in DECISORES,
            tipo=tipo,
            data_entrada=c[SOC["data_entrada"]].strip(),
            faixa_etaria=faixa,
        ))
    return achados


@dataclass
class Estabelecimento:
    cnpj: str
    cnpj_basico: str
    razao_social: str = ""
    nome_fantasia: str = ""
    email: str = ""
    telefone: str = ""
    uf: str = ""
    municipio: str = ""
    endereco: str = ""
    cep: str = ""
    situacao: str = ""
    inicio_atividade: str = ""
    matriz_filial: str = ""
    cnae_origem: str = ""     # principal ou secundaria
    porte: str = ""
    capital_social: str = ""


def _auth() -> str:
    return "Basic " + b64encode(f"{TOKEN}:".encode()).decode()


def baixar(mes: str, arquivo: str, destino: Path, *, verbose: bool = True) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    url = WEBDAV.format(mes=mes, arquivo=arquivo)
    req = Request(url, headers={"Authorization": _auth(), "User-Agent": "scraper-lab/1.0"})
    with urlopen(req, timeout=120) as r, destino.open("wb") as fh:
        shutil.copyfileobj(r, fh, length=1 << 20)
    if verbose:
        print(f"      baixado {arquivo} ({destino.stat().st_size/1e6:.0f} MB)")
    return destino


def _linhas(zip_path: Path):
    """Le o CSV de dentro do zip sem extrair para o disco."""
    with zipfile.ZipFile(zip_path) as z:
        for nome in z.namelist():
            with z.open(nome) as bruto:
                texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
                yield from csv.reader(texto, delimiter=";", quotechar='"')


def _fmt_tel(ddd: str, num: str) -> str:
    ddd, num = ddd.strip(), num.strip()
    return f"({ddd}) {num}" if ddd and num else num


def filtrar_estabelecimentos(zip_path: Path, *, incluir_secundaria: bool = True
                             ) -> list[Estabelecimento]:
    achados = []
    for c in _linhas(zip_path):
        if len(c) <= EST["email"]:
            continue
        principal = c[EST["cnae_principal"]].strip()
        secundaria = c[EST["cnae_secundaria"]].strip()
        origem = ""
        if principal == CNAE_PESQUISA:
            origem = "principal"
        elif incluir_secundaria and CNAE_PESQUISA in secundaria.split(","):
            origem = "secundaria"
        if not origem:
            continue

        base, ordem, dv = (c[EST["cnpj_basico"]], c[EST["cnpj_ordem"]], c[EST["cnpj_dv"]])
        endereco = " ".join(x.strip() for x in (
            c[EST["tipo_logradouro"]], c[EST["logradouro"]], c[EST["numero"]],
            c[EST["complemento"]], c[EST["bairro"]]) if x.strip())
        achados.append(Estabelecimento(
            cnpj=f"{base}{ordem}{dv}",
            cnpj_basico=base,
            nome_fantasia=c[EST["nome_fantasia"]].strip(),
            email=c[EST["email"]].strip().lower(),
            telefone=_fmt_tel(c[EST["ddd1"]], c[EST["tel1"]]),
            uf=c[EST["uf"]].strip(),
            municipio=c[EST["municipio"]].strip(),
            endereco=endereco,
            cep=c[EST["cep"]].strip(),
            situacao=c[EST["situacao"]].strip(),
            inicio_atividade=c[EST["inicio_atividade"]].strip(),
            matriz_filial="matriz" if c[EST["matriz_filial"]].strip() == "1" else "filial",
            cnae_origem=origem,
        ))
    return achados


def completar_empresas(zip_path: Path, alvos: dict[str, Estabelecimento]) -> int:
    """Preenche razao social, porte e capital a partir do arquivo Empresas."""
    n = 0
    for c in _linhas(zip_path):
        if len(c) <= EMP["porte"]:
            continue
        base = c[EMP["cnpj_basico"]]
        if base not in alvos:
            continue
        for est in alvos[base]:
            est.razao_social = c[EMP["razao_social"]].strip()
            est.porte = PORTE.get(c[EMP["porte"]].strip(), c[EMP["porte"]].strip())
            est.capital_social = c[EMP["capital"]].strip()
        n += 1
    return n
