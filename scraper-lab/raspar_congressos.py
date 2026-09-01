"""
Coleta de expositores e patrocinadores dos congressos do setor.

Uso:
    uv run python raspar_congressos.py            # todos os eventos
    uv run python raspar_congressos.py quirks     # so um coletor
    uv run python raspar_congressos.py iiex mrmw tmre ia
"""

import sys
import time
from collections import Counter

from scraper_lab.congressos import (
    coletar_ia,
    coletar_iiex,
    coletar_mrmw,
    coletar_mrs,
    coletar_quirks,
    coletar_tmre,
    coletar_tudo,
    deduplicar,
    eh_comercial,
    exportar,
)

COLETORES = {
    "quirks": coletar_quirks,
    "iiex": coletar_iiex,
    "mrmw": coletar_mrmw,
    "tmre": coletar_tmre,
    "ia": coletar_ia,
    "mrs": coletar_mrs,
}

if __name__ == "__main__":
    alvos = [a for a in sys.argv[1:] if a in COLETORES]
    inicio = time.time()

    if alvos:
        regs = []
        for a in alvos:
            print(f"=== {a} ===")
            regs += COLETORES[a]()
        regs = deduplicar(regs)
        sufixo = "_" + "_".join(alvos)
    else:
        regs = coletar_tudo()
        sufixo = ""

    print("\nExportando")
    cj, cc = exportar(regs, f"congressos{sufixo}")

    comerciais = [r for r in regs if eh_comercial(r)]
    expositores = [r for r in comerciais if "expositor" in r.tipo_participacao]
    patrocinadores = [r for r in comerciais if "patrocinador" in r.tipo_participacao]

    print(f"\n{'=' * 64}")
    print(f"  registros ................. {len(regs)}")
    print(f"  empresas comerciais ....... {len(comerciais)}")
    print(f"  empresas unicas (nome) .... {len({r.nome.lower() for r in comerciais})}")
    print(f"  com site .................. {sum(1 for r in comerciais if r.site)}")
    print(f"  com e-mail ................ {sum(1 for r in comerciais if r.email)}")
    print(f"  com descricao ............. {sum(1 for r in comerciais if r.descricao)}")
    print(f"  expositores ............... {len(expositores)}")
    print(f"  patrocinadores ............ {len(patrocinadores)}")
    print(f"  descartados (org/midia) ... {len(regs) - len(comerciais)}")
    print(f"  erros ..................... {sum(1 for r in regs if r.erro)}")
    print(f"\n  por evento:")
    for ev, n in Counter(r.evento for r in comerciais).most_common():
        print(f"    {ev:44} {n:4}")
    print(f"\n  tempo ..................... {(time.time() - inicio) / 60:.1f} min")
    print(f"  CSV ....................... {cc}")
    print(f"{'=' * 64}")
