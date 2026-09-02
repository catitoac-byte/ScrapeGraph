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
    "url_perfil", "filtros", "restricao_fonte",
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


# Os 13 extratores dos squads seguem o mesmo contrato de campos, com
# extras proprios de cada fonte. Um adaptador generico evita repetir treze
# funcoes quase identicas; o que muda de fato vira parametro.
# Fontes cujo robots.txt restringe rastreamento. Ficam marcadas na coluna
# `restricao_fonte` para que a decisao de manter ou remover seja auditavel
# e reversivel, em vez de invisivel dentro da base.
#   receita: arquivos.receitafederal.gov.br declara "User-agent: * /
#            Disallow: /". O dado e oficialmente aberto e o portal existe
#            para distribui-lo, mas a regra escrita e categorica.
RESTRICAO_FONTE = {
    "receita": "robots.txt do dominio declara Disallow: / (dado aberto por lei)",
}

FONTES_SQUAD = [
    # (arquivo, rotulo da fonte, pais fixo ou None, campo de decisores)
    ("amai_mexico",    "amai",      "Mexico",         "contato"),
    ("apeim_peru",     "apeim",     "Peru",           "contato"),
    ("ceim_argentina", "ceim",      "Argentina",      None),
    ("acei_colombia",  "acei",      "Colombia",       None),
    ("bvm",            "bvm",       None,             None),
    ("adm",            "adm",       "Germany",        "direcao"),
    ("syntec_etudes",  "syntec",    "France",         None),
    ("assirm",         "assirm",    "Italy",          "gruppo_dirigente"),
    ("cric",           "cric",      "Canada",         None),
    ("jmra",           "jmra",      "Japan",          "representante"),
    ("kora",           "kora",      "South Korea",    "representante"),
    ("mrsi",           "mrsi",      "India",          "contatos"),
    ("congressos",     "congresso", None,             None),
    ("din_holanda",    "din",       "Netherlands",    None),
    ("vmoe_austria",   "vmoe",      None,             "contato"),
    ("swiss_insights", "swiss",     "Switzerland",    None),
    ("cube_belgica",   "cube",      "Belgium",        "contato"),
    ("tuad",           "tuad",      "Turkey",         None),
    ("sedea",          "sedea",     "Greece",         "pessoas"),
    ("ofbor",          "ofbor",     "Poland",         None),
    ("ptbrio",         "ptbrio",    "Poland",         None),
]


def _texto(v) -> str:
    """Campos ricos vem como lista ou dict conforme a fonte."""
    if not v:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return " | ".join(f"{k}: {x}" for k, x in v.items() if x)
    return " | ".join(
        (x if isinstance(x, str) else
         " ".join(str(y) for y in x.values() if y)) for x in v if x)


def linha_squad(r: dict, fonte: str, pais_fixo: str | None,
                campo_decisor: str | None) -> dict:
    # O nome de mercado casa melhor entre fontes que a razao social.
    nome = r.get("nome_comercial") or r.get("nome") or r.get("nome_latino") or ""
    return {
        "fonte": fonte, "nome": nome.strip(),
        "email": (r.get("email") or "").strip().lower(),
        "site": r.get("site", ""), "pais": pais_fixo or r.get("pais", ""),
        "uf": r.get("estado") or r.get("cidade", ""),
        "telefone": r.get("telefone", ""), "endereco": r.get("endereco", ""),
        "linkedin": "", "fundacao": str(r.get("fundacao") or r.get("ano_fundacao") or ""),
        "funcionarios": str(r.get("funcionarios") or ""),
        "tipos": _texto(r.get("tipo_associado") or r.get("tipo_membro")
                        or r.get("tipo_associacao") or r.get("categoria")
                        or r.get("tipo_participacao")),
        "contatos": _texto(r.get(campo_decisor)) if campo_decisor else "",
        "campos_atuacao": _texto(r.get("especializacoes") or r.get("servicos")
                                 or r.get("especialidades") or r.get("expertise")),
        "metodos_tecnicas": _texto(r.get("metodos")),
        "outros_servicos": _texto(r.get("setores") or r.get("industrias")
                                  or r.get("nivel_patrocinio")),
        "url_perfil": r.get("url_perfil", ""),
        "filtros": _texto(r.get("evento")),
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
    squads = []
    for arquivo, fonte, pais, dec in FONTES_SQUAD:
        regs = carregar(arquivo, lambda r, f=fonte, p=pais, d=dec: linha_squad(r, f, p, d))
        squads += regs
        if regs:
            print(f"  {fonte}: {len(regs)}")
    print(f"esomar {len(eso)} | abep {len(abp)} | aim {len(aim)} | "
          f"greenbook {len(gb)} | mrs {len(mrs)} | ia-espana {len(ia)} | "
          f"quirks {len(qk)} | usaspending {len(us)} | squads {len(squads)}")

    # A chave inclui o pais: "Ipsos" no Chile e "Ipsos" nos EUA sao escritorios
    # diferentes, e fundi-los apagaria uma empresa real da base.
    por_nome = {(r["pais"], norm(r["nome"])): i
                for i, r in enumerate(eso) if norm(r["nome"])}
    fundidas, novas = 0, 0
    for r in abp + aim + gb + mrs + ia + qk + us + squads:
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

    # O enriquecimento por site roda depois da coleta e grava em cache. Sem
    # reaplicar aqui, cada reconstrucao da base descartava esses e-mails: os
    # EUA caiam de 465 para 108 acionaveis sem nenhum aviso.
    cache_enr = Path("dados/cache")
    aplicados = 0
    for arquivo in ["enriquecimento.json", "enriquecimento_eua.json",
                    "enriquecimento_global.json"]:
        f = cache_enr / arquivo
        if not f.exists():
            continue
        por_dominio = {}
        for v in json.loads(f.read_text(encoding="utf-8")).values():
            if v.get("email_comercial") and v.get("site"):
                d = v["site"].split("//")[-1].split("/")[0].replace("www.", "").lower()
                por_dominio.setdefault(d, v["email_comercial"])
        for r in eso:
            if r["email"] or not r["site"]:
                continue
            d = r["site"].split("//")[-1].split("/")[0].replace("www.", "").lower()
            if d in por_dominio:
                r["email"] = por_dominio[d]
                r["fonte"] += "+site"
                aplicados += 1
    if aplicados:
        print(f"  e-mails do enriquecimento reaplicados: {aplicados}")

    for r in eso:
        r["restricao_fonte"] = "; ".join(
            RESTRICAO_FONTE[f] for f in str(r.get("fonte", "")).split("+")
            if f in RESTRICAO_FONTE)

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
