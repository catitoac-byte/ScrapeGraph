"""
Gera o data.js do painel a partir do JSON da varredura.

    uv run python painel/gerar_dados.py moda
    uv run python painel/gerar_dados.py supermercados

Le verticais/<id>.json (marcas, temas, textos) e o JSON da coleta indicado
em "saida". O arquivo sai em dados/saida/lojas_google/painel/<id>/ (fora do git) porque carrega
o texto das avaliacoes. Nome de autor nunca entra: o painel nao precisa dele
e a pagina pode ser compartilhada.
"""

import json
from pathlib import Path
import re
import sys
from datetime import date

from scraper_lab.lojas_google import DIAS, SAIDA

# Loja sem "localizada_em" no Google: shopping inferido pelo endereco
SHOPPING_POR_ENDERECO = [
    (r"Perimetral Norte", "Passeio das Águas Shopping"),
    (r"24 de Outubro", "Loja de rua · Centro"),
]


def shopping(loja: dict) -> str:
    local = re.sub(r"^(Andar [^·]*·\s*|Localizado em\s*)", "", loja["localizada_em"]).strip()
    if local:
        return local
    for padrao, nome in SHOPPING_POR_ENDERECO:
        if re.search(padrao, loja["endereco"]):
            return nome
    # Loja de rua (caso comum em atacarejo): o local vira o bairro
    b = bairro(loja["endereco"])
    return f"Rua · {b}" if b else "Loja de rua"


def bairro(endereco: str) -> str:
    # O trecho antes de ", Cidade - UF": depois do ultimo " - " ou da ultima virgula
    m = re.search(r"([^,]+),\s*[^,]+?\s+-\s+[A-Z]{2}\b", endereco)
    if not m:
        return ""
    trecho = m.group(1).split(" - ")[-1].strip()
    trecho = re.sub(r"^(s/?n|\d+[a-z]?)\s+", "", trecho, flags=re.I)
    return trecho if not re.fullmatch(r"[\d\s/a-z]{0,4}", trecho, flags=re.I) else ""


def meses(data_iso: str, hoje: date) -> float | None:
    if not data_iso:
        return None
    d = date.fromisoformat(data_iso)
    return round((hoje - d).days / 30.4, 1)


VERTICAIS = Path(__file__).resolve().parents[1] / "verticais"


def main(vertical: str) -> None:
    cfg = json.loads((VERTICAIS / f"{vertical}.json").read_text(encoding="utf-8"))
    nome = cfg["saida"]
    lojas = json.load(open(SAIDA / f"{nome}.json", encoding="utf-8"))
    hoje = date.fromisoformat(lojas[0]["coletado_em"][:10])
    saida_lojas, avaliacoes = [], []
    for i, l in enumerate(lojas):
        sid = f"s{i}"
        saida_lojas.append({
            "id": sid, "marca": l["marca"], "nome": l["nome"], "shopping": shopping(l),
            "bairro": bairro(l["endereco"]), "endereco": l["endereco"],
            "telefone": l["telefone"], "lat": l["latitude"], "lng": l["longitude"],
            "nota": l["nota"], "total": l["total_avaliacoes"], "dist": l["distribuicao_estrelas"],
            "topicos": l["topicos_avaliacoes"], "destaques": l["destaques"],
            "atributos": l["atributos"], "horario": l["horario_funcionamento"],
            "pico": {d: {int(h): p for h, p in l["horarios_pico"].get(d, {}).items()} for d in DIAS},
            "url": l["url"], "pendente": l["erro"],
        })
        for a in l["avaliacoes"]:
            avaliacoes.append({
                "s": sid, "e": a["estrelas"], "t": a["texto"], "m": meses(a["data_estimada"], hoje),
                "d": a["data_relativa"], "r": 1 if a["resposta_proprietario"] else 0,
                "g": 1 if "Local Guide" in a["autor_info"] else 0, "f": a["fotos"],
                "a": a["data_estimada"][:7],
            })
    # O Google usa "Shopping X" como bairro em algumas fichas: herda o bairro
    # de outra loja do mesmo shopping
    bairros = {l["shopping"]: l["bairro"] for l in saida_lojas if "shopping" not in l["bairro"].lower()}
    for l in saida_lojas:
        if "shopping" in l["bairro"].lower():
            l["bairro"] = bairros.get(l["shopping"], "")
    ordens = {l.get("ordenacao", "relevancia") for l in lojas if l["avaliacoes"]}
    dados = {"coleta": hoje.isoformat(), "cidade": cfg["cidade"], "dias": DIAS,
             "vertical": cfg["id"], "titulo": cfg["titulo"],
             "marcas": [m["nome"] for m in cfg["marcas"]], "temas": cfg["temas"],
             "destaque_tema": cfg.get("destaque_tema"), "destaque_texto": cfg.get("destaque_texto"),
             "cores": cfg.get("cores"), "periodo_mensal_desde": cfg.get("periodo_mensal_desde"),
             "ordenacao": "mais recentes" if ordens == {"mais recentes"} else "relevancia",
             "lojas": saida_lojas, "avaliacoes": avaliacoes}
    destino = SAIDA / "painel" / cfg["id"]
    destino.mkdir(parents=True, exist_ok=True)
    js = "window.PAINEL = " + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (destino / "data.js").write_text(js, encoding="utf-8")
    print(destino / "data.js", f"{len(js)/1024:.0f} KB", len(saida_lojas), "lojas", len(avaliacoes), "avaliacoes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "moda")
