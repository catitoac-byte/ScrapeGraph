"""
Coleta assistida: gera a pagina de trabalho e importa os arquivos salvos.

    uv run python coleta-assistida/importar.py pagina supermercados
    uv run python coleta-assistida/importar.py importar supermercados ~/Downloads --publicar

"pagina" monta dados/saida/lojas_google/assistida/<vertical>.html com as lojas
ainda na fila e o favorito "Salvar dados da loja" (salvar_loja.js).

"importar" le os arquivos vitrine_*.json da pasta indicada, junta a aba de
visao geral com a de avaliacoes de cada loja, confere o municipio pelo CEP e
grava a loja como coletada no mesmo estado usado por coleta_em_lotes.py.
"""

import html
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))

from coleta_em_lotes import VERTICAIS, carregar, para_loja, publicar, salvar  # noqa: E402
from scraper_lab.lojas_google import (  # noqa: E402
    SAIDA, Avaliacao, Loja, _chave, _corrigir_cidade, _estimar_data, _limpar,
    _num, _sem_acento, exportar,
)

AQUI = Path(__file__).resolve().parent
DESTINO = SAIDA / "assistida"


def favorito() -> str:
    js = (AQUI / "salvar_loja.js").read_text(encoding="utf-8")
    js = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
    return "javascript:" + quote(js, safe="(){}[];,:=!+-*/<>&|'\"?.$ ")


def pagina(vertical: str) -> Path:
    cfg = json.loads((VERTICAIS / f"{vertical}.json").read_text(encoding="utf-8"))
    estado = carregar(SAIDA / f"{cfg['saida']}_estado.json")
    linhas = []
    for i, item in enumerate(estado["fila"], 1):
        nome = unquote(item["url"].split("/place/")[1].split("/")[0]).replace("+", " ")
        linhas.append(
            f'<tr><td class="n">{i}</td><td>{html.escape(item["marca"])}</td>'
            f'<td><a href="{html.escape(item["url"])}&hl=pt-BR" target="_blank" rel="noopener">{html.escape(nome)}</a></td>'
            f'<td><label><input type="checkbox"> ficha</label> <label><input type="checkbox"> avaliações</label></td></tr>'
        )
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coleta assistida · {html.escape(cfg['nome_pagina'])}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Instrument+Sans:wght@400;500;600&display=swap">
<style>
body{{margin:0;background:#F8FAFC;color:#0F172A;font:400 15px/1.55 "Instrument Sans",system-ui,sans-serif;padding:32px 20px}}
main{{max-width:980px;margin:0 auto}} h1{{font:800 32px/1.1 "Syne",sans-serif;letter-spacing:-.02em;margin:0 0 8px}}
h2{{font:700 18px "Syne",sans-serif;margin:28px 0 10px}} p,li{{color:#334155}}
.fav{{display:inline-block;background:#2563EB;color:#fff;font:700 14px "Syne",sans-serif;padding:12px 18px;border-radius:10px;text-decoration:none;cursor:grab}}
.passo{{background:#fff;border:1px solid rgba(15,23,42,.1);border-radius:12px;padding:16px 20px}}
table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid rgba(15,23,42,.1);border-radius:12px;overflow:hidden}}
td,th{{padding:10px 12px;border-bottom:1px solid rgba(15,23,42,.08);text-align:left;vertical-align:top}}
th{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#64748B}} td.n{{color:#64748B;width:32px}}
a{{color:#2563EB}} label{{white-space:nowrap;margin-right:10px}} tr:has(input:checked + *) td{{}}
.aviso{{background:#FFF7ED;border:1px solid #FED7AA;border-radius:10px;padding:12px 16px}}
</style></head><body><main>
<h1>Coleta assistida</h1>
<p>{html.escape(cfg['titulo'])} · {html.escape(cfg['cidade'])} · {len(estado['fila'])} lojas na fila</p>

<h2>1. Instale o favorito</h2>
<p>Arraste o botão azul para a barra de favoritos do navegador. Ele só lê a ficha que está aberta e baixa um arquivo; não navega nem rola nada sozinho.</p>
<p><a class="fav" href="{html.escape(favorito())}">Salvar dados da loja</a></p>
<p><b>Se não conseguir arrastar:</b> clique em “Copiar código”, depois clique com o botão direito na barra de favoritos, escolha “Adicionar página…”, dê o nome <i>Salvar dados da loja</i> e cole o código no campo URL.</p>
<p><button id="copiar" type="button" style="font:600 14px 'Instrument Sans',sans-serif;padding:10px 16px;border-radius:10px;border:1px solid #2563EB;background:#fff;color:#2563EB;cursor:pointer">Copiar código</button> <span id="copiado" style="color:#16864a"></span></p>
<textarea id="codigo" readonly style="width:100%;height:70px;font:12px monospace;border-radius:8px;border:1px solid rgba(15,23,42,.15);padding:8px">{html.escape(favorito())}</textarea>
<script>
document.getElementById("copiar").onclick = function () {{
  var t = document.getElementById("codigo"); t.select();
  (navigator.clipboard ? navigator.clipboard.writeText(t.value) : Promise.reject()).catch(function () {{ document.execCommand("copy"); }})
    .finally(function () {{ document.getElementById("copiado").textContent = "Copiado. Agora cole no campo URL do novo favorito."; }});
}};
</script>

<h2>2. Para cada loja da lista</h2>
<ol class="passo">
<li>Abra o link da loja. Se o Google mostrar “visualização limitada”, entre na sua conta Google neste navegador.</li>
<li>Na aba <b>Visão geral</b>, role até aparecer <b>Horários de pico</b> e clique no favorito. Sai um arquivo terminado em <code>visao-geral</code>.</li>
<li>Vá para a aba <b>Avaliações</b>, escolha <b>Ordenar › Mais recentes</b> e role a lista até onde quiser (umas 100 a 300 avaliações). Clique no favorito de novo. Sai um arquivo terminado em <code>avaliacoes</code>.</li>
<li>Marque a loja abaixo e siga para a próxima, no seu ritmo.</li>
</ol>
<p class="aviso">Os arquivos vão para a pasta de Downloads. Quando terminar (ou a cada algumas lojas), me avise que eu importo e publico o painel.</p>

<h2>3. Lojas</h2>
<table><thead><tr><th>#</th><th>Marca</th><th>Loja</th><th>Feito</th></tr></thead><tbody>
{''.join(linhas)}
</tbody></table>
<p style="margin-top:18px;font-size:13px;color:#64748B">Nome de quem avaliou não é lido pelo favorito. Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}.</p>
</main></body></html>"""
    DESTINO.mkdir(parents=True, exist_ok=True)
    caminho = DESTINO / f"{vertical}.html"
    caminho.write_text(doc, encoding="utf-8")
    return caminho




def montar_loja(marca: str, arquivos: list[dict]) -> Loja:
    # O arquivo da aba de avaliacoes tambem traz estrelas, mas nunca o pico:
    # a ficha e o arquivo com mais dias de pico preenchidos
    ficha = max(arquivos, key=lambda a: sum(1 for v in a["horarios_pico"].values() if v))
    base = max(arquivos, key=lambda a: len(a["endereco"]))
    loja = Loja(marca=marca, nome=_limpar(base["nome"]), url=base["url"])
    loja.place_id = base["place_id"] or _chave(base["url"])
    loja.latitude, loja.longitude = base["latitude"], base["longitude"]
    loja.categoria = base["categoria"]
    loja.nota = _num(base["nota_txt"])
    total = _num(base["total_txt"])
    loja.total_avaliacoes = int(total) if total is not None else None
    loja.endereco = _limpar(base["endereco"])
    cidades = re.findall(r"(?:^|,)\s*([^,]+?)\s+-\s+[A-Z]{2}\b", loja.endereco)
    loja.cidade = _corrigir_cidade(_limpar(cidades[-1]) if cidades else "", loja.endereco)
    loja.localizada_em = _limpar(base["localizada_em"])
    loja.telefone, loja.site, loja.plus_code = base["telefone"], base["site"], base["plus_code"]
    for a in arquivos:
        loja.horario_funcionamento.update(a["horario_funcionamento"])
        loja.distribuicao_estrelas.update(a["distribuicao_estrelas"])
        loja.topicos_avaliacoes.update(a["topicos_avaliacoes"])
    loja.horarios_pico = ficha["horarios_pico"]
    agora = datetime.now()
    vistos = set()
    for a in arquivos:
        for r in a["avaliacoes"]:
            if r["id"] in vistos:
                continue
            vistos.add(r["id"])
            est = _num(r["estrelas_txt"])
            loja.avaliacoes.append(Avaliacao(
                id=r["id"], autor="", autor_info="Local Guide" if r["local_guide"] else "",
                estrelas=int(est) if est is not None else None,
                data_relativa=_limpar(r["data_relativa"]),
                data_estimada=_estimar_data(r["data_relativa"], agora),
                texto=_limpar(r["texto"]), curtidas=None,
                resposta_proprietario=_limpar(r["resposta_proprietario"]), fotos=r["fotos"],
            ))
    loja.ordenacao = "mais recentes"
    if any(a["limitada"] for a in arquivos) and not loja.horarios_pico:
        loja.erro = "visualizacao limitada na coleta assistida"
    loja.coletado_em = max(a["salvo_em"] for a in arquivos)
    return loja


def importar(vertical: str, pasta: Path, publicar_site: bool) -> None:
    cfg = json.loads((VERTICAIS / f"{vertical}.json").read_text(encoding="utf-8"))
    caminho = SAIDA / f"{cfg['saida']}_estado.json"
    estado = carregar(caminho)
    marca_por_chave = {_chave(i["url"]): i["marca"] for i in estado["fila"]}
    marca_por_chave.update({k: d["marca"] for k, d in estado["feitas"].items()})
    grupos: dict[str, list[dict]] = {}
    for f in sorted(pasta.glob("vitrine_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("formato") != "vitrine-assistida-1":
            continue
        grupos.setdefault(d["place_id"] or _chave(d["url"]), []).append(d)
    alvo = _sem_acento(cfg["cidade"].split(",")[0].strip())
    novas = 0
    for chave, arquivos in grupos.items():
        marca = marca_por_chave.get(chave)
        if not marca:
            print(f"   ignorado (loja fora da lista): {arquivos[0]['nome']}")
            continue
        loja = montar_loja(marca, arquivos)
        estado["fila"] = [i for i in estado["fila"] if _chave(i["url"]) != chave]
        if loja.cidade and _sem_acento(loja.cidade) != alvo:
            estado["fora"].append({"marca": marca, "url": loja.url, "cidade": loja.cidade})
            print(f"   fora da cidade: {loja.nome} ({loja.cidade})")
            continue
        estado["feitas"][loja.place_id] = asdict(loja)
        novas += 1
        print(f"   ok: {marca} · {loja.nome} · pico={sum(1 for v in loja.horarios_pico.values() if v)}d · aval={len(loja.avaliacoes)}"
              + (f" · {loja.erro}" if loja.erro else ""))
    estado["lotes"].append({"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "resultado": f"coleta assistida: {novas} lojas importadas"})
    salvar(caminho, estado)
    lojas = [para_loja(d) for d in estado["feitas"].values()]
    if lojas:
        exportar(lojas, cfg["saida"])
        if publicar_site and novas:
            publicar(cfg)
    print(f"{novas} lojas importadas, {len(estado['fila'])} ainda na fila")


if __name__ == "__main__":
    acao, vertical = sys.argv[1], sys.argv[2]
    if acao == "pagina":
        print(pagina(vertical))
    else:
        importar(vertical, Path(sys.argv[3]).expanduser(), "--publicar" in sys.argv)
