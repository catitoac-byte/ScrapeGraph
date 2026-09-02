"""
Coleta das empresas associadas a TUAD (Turquia).

    uv run python -u raspar_tuad.py
"""

import time

from scraper_lab.tuad import (
    _preparar_robots,
    codificacoes_detectadas,
    coletar,
    exportar,
    ids_com_iso,
    listar_membros,
    sessao_ativa,
    tem_letras_turcas,
)

if __name__ == "__main__":
    inicio = time.time()

    print("[1/5] Verificando robots.txt")
    for dominio, relato in _preparar_robots().items():
        print(f"      {dominio}: {relato}")

    print("\n[2/5] Listando empresas associadas (duas categorias)")
    membros = listar_membros()
    # A listagem tambem e o que estabelece a sessao PHPSESSID usada nas fichas.
    print(f"      sessao PHPSESSID estabelecida: {sessao_ativa()}")
    print(f"      {len(membros)} empresas unicas")

    print("\n[3/5] Lendo o selo ISO 20252 / GAB")
    com_iso = ids_com_iso()
    ids = {m["id"] for m in membros}
    fora = com_iso - ids
    # Conferencia contra a propria fonte: todo certificado deveria estar numa
    # das duas listas de associadas. Se sobrar algum, a listagem veio truncada.
    print(f"      {len(com_iso & ids)} casados por id; "
          f"{len(fora)} fora das listas de associadas"
          + (f" -> {sorted(fora)}" if fora else ""))

    print("\n[4/5] Coletando fichas")
    empresas = coletar(membros, com_iso)

    print("\n[5/5] Exportando")
    cj, cc = exportar(empresas)

    com_dados = [e for e in empresas if not e.erro]
    falhas = [e for e in empresas if e.erro and "sem dados de contato" not in e.erro]
    turco_ok = sum(1 for e in empresas if tem_letras_turcas(e.nome))
    print("\n" + "=" * 64)
    print(f"  empresas ............. {len(empresas)}")
    for rotulo in sorted({e.tipo_associacao for e in empresas}):
        print(f"    {rotulo[:34]:34} {sum(1 for e in empresas if e.tipo_associacao == rotulo)}")
    print(f"  com email ............ {sum(1 for e in empresas if e.email)}")
    print(f"  com site ............. {sum(1 for e in empresas if e.site)}")
    print(f"  com telefone ......... {sum(1 for e in empresas if e.telefone)}")
    print(f"  com endereco ......... {sum(1 for e in empresas if e.endereco)}")
    print(f"  com descricao ........ {sum(1 for e in empresas if e.descricao)}")
    print(f"  com ISO 20252 ........ {sum(1 for e in empresas if e.iso_20252 == 'sim')}")
    print(f"  ficha sem contato .... {len(empresas) - len(com_dados) - len(falhas)}")
    print(f"  falhas de coleta ..... {len(falhas)}")
    print(f"  nomes com letra turca  {turco_ok}/{len(empresas)}  (prova de codificacao)")
    print(f"  codificacoes ......... {codificacoes_detectadas()}")
    print(f"  tempo ................ {time.time() - inicio:.0f}s")
    print(f"  CSV .................. {cc}")
    print("=" * 64)
