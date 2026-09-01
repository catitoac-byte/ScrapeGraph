"""
Une a base Esomar com a base ABEP num CSV unico.

Deduplica apenas empresas que sao de fato a mesma, casadas por nome
normalizado. Dominio corporativo compartilhado NAO gera fusao: Ipsos Brasil
e Ipsos Australia usam ipsos.com e sao escritorios distintos.

    uv run python -u unir_bases.py
"""

import csv
import json
import re
import unicodedata
from pathlib import Path

SAIDA = Path(__file__).resolve().parent / "dados" / "saida"

COLUNAS = [
    "fonte", "nome", "email", "site", "pais", "uf", "telefone", "endereco",
    "linkedin", "fundacao", "funcionarios", "tipos", "contatos",
    "campos_atuacao", "metodos_tecnicas", "outros_servicos",
    "url_perfil", "filtros",
]

_RUIDO = re.compile(
    r"\b(ltda|s\.?a\.?|me|epp|eireli|inc|llc|group|grupo|pesquisas?|pesquisa|"
    r"marketing|research|consultoria|consulting|de|do|da|e)\b")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", _RUIDO.sub(" ", s))


def linha_esomar(r: dict) -> dict:
    return {
        "fonte": "esomar", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais", ""), "uf": "",
        "telefone": r.get("telefone", ""), "endereco": r.get("endereco", ""),
        "linkedin": r.get("linkedin", ""), "fundacao": r.get("fundacao", ""),
        "funcionarios": r.get("funcionarios", ""),
        "tipos": " | ".join(r.get("tipos") or []),
        "contatos": " | ".join(
            c["nome"] + (f" ({c['cargo']})" if c.get("cargo") else "")
            for c in (r.get("contatos") or [])),
        "campos_atuacao": "", "metodos_tecnicas": "", "outros_servicos": "",
        "url_perfil": r.get("url_perfil", ""),
        "filtros": " | ".join(r.get("filtros") or []),
    }


def linha_aim(r: dict) -> dict:
    return {
        "fonte": "aim", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais", "Chile"), "uf": "",
        "telefone": r.get("telefone", ""), "endereco": "",
        "linkedin": "", "fundacao": "", "funcionarios": "",
        "tipos": "", "contatos": "",
        "campos_atuacao": "", "metodos_tecnicas": "",
        "outros_servicos": "", "url_perfil": "https://aimchile.cl/socios/",
        "filtros": r.get("origem_dados", ""),
    }


def linha_abep(r: dict) -> dict:
    return {
        "fonte": "abep", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais", "Brazil"), "uf": r.get("uf", ""),
        "telefone": r.get("telefone", ""), "endereco": r.get("endereco", ""),
        "linkedin": "", "fundacao": "", "funcionarios": "",
        "tipos": r.get("tipo_empresa", ""), "contatos": "",
        "campos_atuacao": r.get("campos_atuacao", ""),
        "metodos_tecnicas": r.get("metodos_tecnicas", ""),
        "outros_servicos": r.get("outros_servicos", ""),
        "url_perfil": r.get("url_perfil", ""), "filtros": "",
    }


def fundir(a: dict, b: dict) -> dict:
    """
    Campo vazio de um lado recebe o valor do outro. Nada e sobrescrito.

    A procedencia acumula as fontes que realmente participaram. Antes o
    rotulo era fixo em "esomar+abep", o que marcava uma empresa belga vinda
    da MRS como se fosse do diretorio brasileiro.
    """
    saida = dict(a)
    for k in COLUNAS:
        if not saida.get(k) and b.get(k):
            saida[k] = b[k]
    fontes = sorted(set(str(a.get("fonte", "")).split("+"))
                    | set(str(b.get("fonte", "")).split("+")) - {""})
    saida["fonte"] = "+".join(f for f in fontes if f)
    return saida


_UF_EUA = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR",
}


def sigla_uf(valor: str) -> str:
    """Uma fonte escreve "North Carolina", outra "NC". Padronizamos na sigla."""
    v = (valor or "").strip()
    return _UF_EUA.get(v.lower(), v if len(v) <= 3 else v)


def linha_greenbook(r: dict) -> dict:
    return {
        "fonte": "greenbook", "nome": r.get("nome", ""), "email": "",
        "site": r.get("site", ""), "pais": r.get("pais", ""),
        "uf": sigla_uf(r.get("regiao", "")), "telefone": r.get("telefone", ""),
        "endereco": r.get("endereco", ""), "linkedin": r.get("linkedin", ""),
        "fundacao": "", "funcionarios": "", "tipos": r.get("categoria", ""),
        "contatos": "", "campos_atuacao": r.get("servicos", ""),
        "metodos_tecnicas": "", "outros_servicos": "",
        "url_perfil": r.get("url_perfil", ""), "filtros": "",
    }


def linha_mrs(r: dict) -> dict:
    return {
        "fonte": "mrs", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais", ""), "uf": "",
        "telefone": r.get("telefone", ""), "endereco": r.get("endereco", ""),
        "linkedin": "", "fundacao": "", "funcionarios": "",
        "tipos": r.get("tipo_membro", ""), "contatos": "",
        "campos_atuacao": "", "metodos_tecnicas": "", "outros_servicos": "",
        "url_perfil": r.get("url_perfil", ""), "filtros": "",
    }


def linha_ia(r: dict) -> dict:
    return {
        "fonte": "ia-espana", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais", "Spain"), "uf": "",
        "telefone": r.get("telefone", ""), "endereco": "",
        "linkedin": "", "fundacao": "", "funcionarios": "",
        "tipos": "", "contatos": "", "campos_atuacao": "",
        "metodos_tecnicas": "", "outros_servicos": r.get("associacoes", ""),
        "url_perfil": r.get("url_perfil", ""), "filtros": "",
    }


def linha_quirks(r: dict) -> dict:
    return {
        "fonte": "quirks", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais") or "United States",
        "uf": sigla_uf(r.get("estado", "")), "telefone": "",
        "endereco": ", ".join(x for x in (r.get("cidade"), r.get("estado")) if x),
        "linkedin": "", "fundacao": "", "funcionarios": "", "tipos": "",
        "contatos": "", "campos_atuacao": r.get("servicos", ""),
        "metodos_tecnicas": "", "outros_servicos": "",
        "url_perfil": r.get("url_perfil", ""), "filtros": "",
    }


def linha_usaspending(r: dict) -> dict:
    return {
        "fonte": "usaspending", "nome": r.get("nome", ""), "email": r.get("email", ""),
        "site": r.get("site", ""), "pais": r.get("pais", ""),
        "uf": sigla_uf(r.get("estado", "")), "telefone": "",
        "endereco": ", ".join(x for x in (r.get("endereco"), r.get("cidade"),
                                          r.get("estado"), r.get("cep")) if x),
        "linkedin": "", "fundacao": "", "funcionarios": "",
        "tipos": r.get("tipos_negocio", ""), "contatos": "",
        "campos_atuacao": "", "metodos_tecnicas": "",
        "outros_servicos": f"UEI {r.get('uei','')}".strip(),
        "url_perfil": "", "filtros": "",
    }


def carregar(nome: str, conversor):
    caminho = SAIDA / f"{nome}.json"
    if not caminho.exists():
        print(f"  aviso: {nome}.json ausente, fonte ignorada")
        return []
    return [conversor(r) for r in json.loads(caminho.read_text(encoding="utf-8"))
            if r.get("nome")]


if __name__ == "__main__":
    eso = [linha_esomar(r) for r in json.loads((SAIDA / "esomar_mestre.json").read_text(encoding="utf-8"))]
    abp = [linha_abep(r) for r in json.loads((SAIDA / "abep.json").read_text(encoding="utf-8"))]
    aim = carregar("aim_chile", linha_aim)
    gb = carregar("greenbook", linha_greenbook)
    mrs = carregar("mrs_uk", linha_mrs)
    ia = carregar("ia_espana", linha_ia)
    qk = carregar("quirks_united_states", linha_quirks)
    us = carregar("usaspending_naics541910", linha_usaspending)
    print(f"esomar {len(eso)} | abep {len(abp)} | aim {len(aim)} | "
          f"greenbook {len(gb)} | mrs {len(mrs)} | ia-espana {len(ia)} | "
          f"quirks {len(qk)} | usaspending {len(us)}")

    # A chave inclui o pais: "Ipsos" no Chile e "Ipsos" nos EUA sao escritorios
    # diferentes, e fundi-los apagaria uma empresa real da base.
    por_nome = {(r["pais"], norm(r["nome"])): i
                for i, r in enumerate(eso) if norm(r["nome"])}
    fundidas, novas = 0, 0
    for r in abp + aim + gb + mrs + ia + qk + us:
        chave = (r["pais"], norm(r["nome"]))
        if chave[1] and chave in por_nome:
            eso[por_nome[chave]] = fundir(eso[por_nome[chave]], r)
            fundidas += 1
        else:
            # O indice precisa crescer junto. Sem isto, a segunda fonte a
            # trazer a mesma empresa nao a encontra e cria duplicata: eram
            # 102 pares repetidos so nos EUA.
            if chave[1]:
                por_nome[chave] = len(eso)
            eso.append(r)
            novas += 1

    eso.sort(key=lambda r: (r["pais"], r["nome"]))
    destino = SAIDA / "base_unificada.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for r in eso:
            w.writerow({k: r.get(k, "") for k in COLUNAS})

    br = [r for r in eso if r["pais"] == "Brazil"]
    print(f"\n{'='*58}")
    print(f"  total ............ {len(eso)}")
    print(f"  fundidas ......... {fundidas}")
    print(f"  novas ............ {novas}")
    print(f"  brasileiras ...... {len(br)}")
    print(f"  com email ........ {sum(1 for r in eso if r['email'])}")
    print(f"  com contatos ..... {sum(1 for r in eso if r['contatos'])}")
    print(f"  paises ........... {len({r['pais'] for r in eso if r['pais']})}")
    print(f"  CSV .............. {destino}")
    print(f"{'='*58}")
