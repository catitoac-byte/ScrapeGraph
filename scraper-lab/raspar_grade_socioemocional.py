"""
Grade socioemocional por serie, Brasil e EUA (Corredor Escola). Etapas, em ordem:

    uv run python raspar_grade_socioemocional.py coletar      # sem modelo, com cache
    uv run python raspar_grade_socioemocional.py filtrar      # sem modelo
    uv run python raspar_grade_socioemocional.py extrair      # GPT da conta ChatGPT, via Codex
    uv run python raspar_grade_socioemocional.py conferir     # Claude Haiku numa amostra de 10%
    uv run python raspar_grade_socioemocional.py montar       # grade.json
    uv run python raspar_grade_socioemocional.py atividades   # GPT, uma chamada por serie
    uv run python raspar_grade_socioemocional.py markdown     # .md legiveis
    uv run python raspar_grade_socioemocional.py plano        # GPT, plano anual por serie, e seus .md

Fontes em verticais/grade_socioemocional.json. Saida em dados/saida/grade_socioemocional/.
extrair, atividades e plano retomam de onde pararam (arquivos .jsonl).
"""

import json
import sys

from scraper_lab import grade_socioemocional as g

ETAPAS = {
    "coletar": g.coletar, "filtrar": g.filtrar, "extrair": g.extrair, "conferir": g.conferir_amostra,
    "montar": g.montar_grade, "atividades": g.gerar_atividades, "markdown": g.escrever_markdown,
    "plano": lambda: (g.gerar_plano_ensino(), g.escrever_markdown_plano())[0],
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ETAPAS:
        sys.exit(f"uso: raspar_grade_socioemocional.py {{{'|'.join(ETAPAS)}}}")
    r = ETAPAS[sys.argv[1]]()
    if isinstance(r, dict) and "amostra" in r:
        print(json.dumps({k: v for k, v in r.items() if k != "resultados"}, ensure_ascii=False))
    elif isinstance(r, list):
        print(f"{sys.argv[1]}: {len(r)} registros")
