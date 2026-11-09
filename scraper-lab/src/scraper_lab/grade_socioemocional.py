"""
Grade socioemocional por serie, Brasil e EUA (pedido do Corredor Escola, 09/11/2026).

Tres camadas, na ordem:

1. coletar: baixa cada fonte de verticais/grade_socioemocional.json uma vez so
   (PDF por HTTP, pagina pelo Chromium da ScrapeGraph) e guarda em cache. O
   gov.br devolve 429 quando se baixa varias vezes seguidas, por isso o cache.
2. filtrar: quebra o texto em trechos com pagina e fica so com os que tem
   palavra da area. Nada disso usa modelo.
3. extrair: manda os trechos em lotes para o GPT da conta ChatGPT do Cassiano,
   pelo Codex que vem no ChatGPT.app. A resposta segue um JSON Schema e cada
   item carrega o id do trecho de onde saiu.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "verticais" / "grade_socioemocional.json"
CACHE = RAIZ / "dados" / "cache" / "grade_socioemocional"
SAIDA = RAIZ / "dados" / "saida" / "grade_socioemocional"
CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/130 Safari/537.36"

TAM_TRECHO = 1800  # caracteres; cabe num paragrafo longo de PDF sem cortar no meio da ideia


def carregar_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _baixar(url: str) -> tuple[int, str, bytes]:
    url = urllib.parse.quote(url, safe=":/?&=%#+@")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), b""


def _texto_docx(caminho: Path) -> list[str]:
    import zipfile

    xml = zipfile.ZipFile(caminho).read("word/document.xml").decode("utf-8")
    paragrafos = [re.sub(r"<[^>]+>", "", p) for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)]
    return ["\n".join(p for p in paragrafos if p.strip())]


def _texto_pdf(caminho: Path) -> list[str]:
    from pypdf import PdfReader

    return [(p.extract_text() or "") for p in PdfReader(caminho).pages]


def coletar(ids: list[str] | None = None) -> list[dict]:
    """Baixa o que falta no cache e devolve o registro de cada fonte."""
    from scraper_lab.coleta import coletar as coletar_paginas

    CACHE.mkdir(parents=True, exist_ok=True)
    registros = []
    for f in carregar_config()["fontes"]:
        if ids and f["id"] not in ids:
            continue
        reg = {**f, "coletado_em": datetime.now(timezone.utc).isoformat()}
        pdf, html, docx = (CACHE / f"{f['id']}.{ext}" for ext in ("pdf", "md", "docx"))
        try:
            if not pdf.exists() and not html.exists() and not docx.exists():
                if f.get("arquivo") or f["url"].lower().split("?")[0].endswith(".pdf"):
                    status, tipo, corpo = _baixar(f["url"])
                    if status == 200 and corpo[:4] == b"%PDF":
                        pdf.write_bytes(corpo)
                    elif status == 200 and corpo[:2] == b"PK":
                        docx.write_bytes(corpo)
                    reg["http"] = status
                    time.sleep(3)  # gov.br corta quem pede rapido demais
                else:
                    try:
                        pag = coletar_paginas([f["url"]])[0]
                    except RuntimeError as e:
                        if "Download is starting" not in str(e):
                            raise
                        # a pagina e um arquivo: baixa direto
                        status, tipo, corpo = _baixar(f["url"])
                        reg["http"] = status
                        if corpo[:4] == b"%PDF":
                            pdf.write_bytes(corpo)
                        corpo = b""
                        pag = None
                    if pag is None:
                        pass
                    else:
                        bloqueio = re.search(r"request is blocked|access denied|403 forbidden", pag.markdown[:500], re.I)
                        if len(pag.markdown) > 500 and not bloqueio:
                            html.write_text(pag.markdown, encoding="utf-8")
            if docx.exists():
                paginas = _texto_docx(docx)
                reg.update(formato="docx", paginas=1, chars=len(paginas[0]), ok=True)
            elif pdf.exists():
                paginas = _texto_pdf(pdf)
                reg.update(formato="pdf", paginas=len(paginas), chars=sum(map(len, paginas)), ok=True)
            elif html.exists():
                reg.update(formato="html", paginas=1, chars=len(html.read_text(encoding="utf-8")), ok=True)
            else:
                reg.update(ok=False, motivo=f"sem conteudo (http {reg.get('http', '?')})")
        except Exception as e:  # uma fonte ruim nao derruba a coleta
            reg.update(ok=False, motivo=f"{type(e).__name__}: {e}"[:300])
        registros.append(reg)
        print(f"[coleta] {f['id']}: {'ok' if reg['ok'] else reg['motivo']} {reg.get('paginas', '')}")
    SAIDA.mkdir(parents=True, exist_ok=True)
    arq = SAIDA / "fontes.json"
    if ids and arq.exists():
        novos = {r["id"] for r in registros}
        registros = [r for r in json.loads(arq.read_text(encoding="utf-8")) if r["id"] not in novos] + registros
    arq.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    return registros


def _paginas_da_fonte(fid: str) -> list[str]:
    pdf, html, docx = CACHE / f"{fid}.pdf", CACHE / f"{fid}.md", CACHE / f"{fid}.docx"
    if docx.exists():
        return _texto_docx(docx)
    if pdf.exists():
        return _texto_pdf(pdf)
    if html.exists():
        return [html.read_text(encoding="utf-8")]
    return []


def filtrar(ids: list[str] | None = None) -> list[dict]:
    """Trechos com pagina de origem que tem ao menos duas palavras da area.

    Com ids, acrescenta so os trechos dessas fontes ao fim de trechos.json, para
    nao mexer no que ja foi extraido.
    """
    cfg = carregar_config()
    palavras = [p.lower() for p in cfg["palavras_filtro"]]
    fontes = {f["id"]: f for f in json.loads((SAIDA / "fontes.json").read_text(encoding="utf-8")) if f["ok"]}
    trechos = []
    for fid, f in fontes.items():
        if ids and fid not in ids:
            continue
        for n, texto in enumerate(_paginas_da_fonte(fid), start=1):
            texto = re.sub(r"[ \t]+", " ", texto)
            blocos = [texto[i : i + TAM_TRECHO] for i in range(0, len(texto), TAM_TRECHO)]
            for k, bloco in enumerate(blocos):
                baixo = bloco.lower()
                acertos = sum(baixo.count(p) for p in palavras)
                if acertos >= 2:
                    trechos.append({
                        "id": f"{fid}:p{n}:{k}", "fonte": fid, "pais": f["pais"], "url": f["url"],
                        "pagina": n, "acertos": acertos, "texto": bloco.strip(),
                    })
    arq = SAIDA / "trechos.json"
    if ids and arq.exists():
        antigos = json.loads(arq.read_text(encoding="utf-8"))
        vistos = {t["id"] for t in antigos}
        trechos = antigos + [t for t in trechos if t["id"] not in vistos]
    arq.write_text(json.dumps(trechos, ensure_ascii=False, indent=2), encoding="utf-8")
    return trechos


def chamar_gpt(prompt: str, schema: dict, *, tentativas: int = 2) -> dict:
    """Uma chamada ao GPT pelo Codex, com resposta presa ao schema."""
    with tempfile.TemporaryDirectory() as tmp:
        sch, saida = Path(tmp) / "schema.json", Path(tmp) / "resposta.json"
        sch.write_text(json.dumps(schema), encoding="utf-8")
        for t in range(tentativas):
            r = subprocess.run(
                [CODEX, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                 "-C", tmp, "--output-schema", str(sch), "-o", str(saida), "-"],
                input=prompt, text=True, capture_output=True, timeout=900,
            )
            if saida.exists() and saida.read_text(encoding="utf-8").strip():
                try:
                    return json.loads(saida.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            time.sleep(5 * (t + 1))
        raise RuntimeError(f"GPT nao respondeu no formato: {r.stderr[-500:]}")


# ---------------------------------------------------------------- extracao

COMPETENCIAS = ["autoconhecimento", "autogestao", "consciencia_social", "relacionamento", "tomada_de_decisao"]
SERIES = {
    "BR": ["creche", "pre_escola", "1ano", "2ano", "3ano", "4ano", "5ano", "6ano", "7ano", "8ano", "9ano",
           "em1", "em2", "em3"],
    "US": ["prek", "k", "g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9", "g10", "g11", "g12"],
}
REGRAS_CASA = (
    "Regras de conteudo obrigatorias: nunca falar de suicidio nem de automutilacao; nunca usar a palavra "
    "depressao (o termo da casa e 'Alerta de Estado Emocional'); sem preco; sem tema juridico; em portugues "
    "nao use travessao nem hifen para separar frases; nunca obrigar o aluno a se expor; avaliacao sem nota "
    "de 0 a 10, so portfolio e autoavaliacao. Trechos sobre Setembro Amarelo ou prevencao ao suicidio devem "
    "ser ignorados."
)

SCHEMA_ITENS = {
    "type": "object", "additionalProperties": False, "required": ["itens"],
    "properties": {"itens": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["trecho_id", "tipo", "series", "competencias", "descricao", "citacao", "codigo_oficial"],
        "properties": {
            "trecho_id": {"type": "string"},
            "tipo": {"type": "string", "enum": ["habilidade", "progressao", "dinamica", "metodologia", "avaliacao"]},
            "series": {"type": "array", "items": {"type": "string", "enum": SERIES["BR"] + SERIES["US"]}},
            "competencias": {"type": "array", "items": {"type": "string", "enum": COMPETENCIAS}},
            "descricao": {"type": "string"},
            "citacao": {"type": "string"},
            "codigo_oficial": {"type": "string"},
        }}}},
}

PROMPT_ITENS = """Voce extrai a grade curricular socioemocional por serie de documentos oficiais e de referencia.
Leia os trechos abaixo. Cada um tem um id, o pais (BR ou US) e a fonte.
Para cada habilidade, objetivo por serie, progressao, dinamica, metodologia ou forma de avaliacao
socioemocional que o trecho afirma, devolva um item:
- trecho_id: o id exato do trecho.
- tipo: habilidade (objetivo ou benchmark), progressao (o que muda de uma serie para outra), dinamica
  (atividade concreta), metodologia (abordagem como assembleia, projeto, roda de conversa) ou avaliacao.
- series: as series a que se aplica. BR: creche, pre_escola, 1ano a 9ano, em1 a em3. US: prek, k, g1 a g12.
  Faixas como "K-3" ou "6 a 9 ano" viram a lista completa. Lista vazia se o trecho nao diz a serie.
- competencias: mapeie para as cinco do CASEL (autoconhecimento, autogestao, consciencia_social,
  relacionamento, tomada_de_decisao).
- descricao: uma frase curta em portugues dizendo o que o aluno desenvolve ou faz.
- citacao: copie de 8 a 30 palavras SEGUIDAS e LITERAIS do trecho, no idioma original, que provam o item.
- codigo_oficial: codigo da BNCC (ex.: EF15LP09, EI03EO01), da competencia geral (ex.: CG8) ou do padrao
  estadual (ex.: 1A.1a). Vazio se nao houver no trecho.
Nao invente: so o que estiver no trecho. Trecho sem nada socioemocional nao gera item.
{regras}

TRECHOS:
{trechos}
"""


def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def extrair(*, tam_lote: int = 14, limite_lotes: int | None = None) -> list[dict]:
    """Manda os trechos em lotes ao GPT e guarda os itens com a citacao conferida."""
    trechos = json.loads((SAIDA / "trechos.json").read_text(encoding="utf-8"))
    por_id = {t["id"]: t for t in trechos}
    feitos_arq = SAIDA / "itens_brutos.jsonl"
    feitos: set[str] = set()
    if feitos_arq.exists():
        for linha in feitos_arq.read_text(encoding="utf-8").splitlines():
            reg = json.loads(linha)
            # linhas antigas so tem o numero do lote de 14, contado na lista original
            feitos.update(reg.get("trechos") or [t["id"] for t in trechos[reg["lote"] * 14 : reg["lote"] * 14 + 14]])
    pendentes = [t for t in trechos if t["id"] not in feitos]
    lotes = [pendentes[i : i + tam_lote] for i in range(0, len(pendentes), tam_lote)]
    for n, lote in enumerate(lotes):
        if limite_lotes is not None and n >= limite_lotes:
            break
        corpo = "\n\n".join(f"[{t['id']}] pais={t['pais']} fonte={t['fonte']}\n{t['texto']}" for t in lote)
        inicio = time.time()
        resp = chamar_gpt(PROMPT_ITENS.format(regras=REGRAS_CASA, trechos=corpo), SCHEMA_ITENS)
        with feitos_arq.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"lote": n, "trechos": [t["id"] for t in lote], "itens": resp["itens"]},
                                ensure_ascii=False) + "\n")
        print(f"[gpt] lote {n + 1}/{len(lotes)}: {len(resp['itens'])} itens em {time.time() - inicio:.0f}s")

    itens = []
    for linha in feitos_arq.read_text(encoding="utf-8").splitlines():
        for it in json.loads(linha)["itens"]:
            t = por_id.get(it["trecho_id"])
            if not t:
                continue
            it["citacao_conferida"] = _normalizar(it["citacao"]) in _normalizar(t["texto"])
            it.update(pais=t["pais"], fonte=t["fonte"], url=t["url"], pagina=t["pagina"])
            itens.append(it)
    (SAIDA / "itens.json").write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
    return itens


# ---------------------------------------------------------------- grade e atividades

NOME_SERIE = {
    "creche": "Educação Infantil, creche (0 a 3 anos)", "pre_escola": "Educação Infantil, pré-escola (4 e 5 anos)",
    **{f"{n}ano": f"{n}º ano do Ensino Fundamental" for n in range(1, 10)},
    "em1": "1ª série do Ensino Médio", "em2": "2ª série do Ensino Médio", "em3": "3ª série do Ensino Médio",
    "prek": "Pre-K", "k": "Kindergarten", **{f"g{n}": f"Grade {n}" for n in range(1, 13)},
}


# Arquivos que ja sao de uma faixa so: a serie vem do arquivo, nao da leitura do modelo.
SERIES_POR_FONTE = {
    "wisconsin_pk_5k": ["prek", "k"], "wisconsin_1_3": ["g1", "g2", "g3"], "wisconsin_4_5": ["g4", "g5"],
    "wisconsin_6_8": ["g6", "g7", "g8"], "wisconsin_9_10": ["g9", "g10"], "wisconsin_11_adulto": ["g11", "g12"],
}
EI_POR_GRUPO = {"01": ["creche"], "02": ["creche"], "03": ["pre_escola"]}


def series_do_codigo(codigo: str) -> list[str] | None:
    """Series pela regra do codigo da BNCC: EF15 = 1 a 5 ano, EF06 = 6 ano, EM13 = todo o EM, EI03 = pre-escola."""
    m = re.match(r"(EF|EM|EI)(\d)(\d)", codigo.strip().upper())
    if not m:
        return None
    etapa, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    if etapa == "EI":
        return EI_POR_GRUPO.get(f"{a}{b}")
    if etapa == "EM":
        return ["em1", "em2", "em3"]
    if a == 0:
        return [f"{b}ano"]
    return [f"{n}ano" for n in range(a, b + 1)]


def montar_grade() -> dict:
    """Grade por pais e serie, so com itens cuja citacao bate literalmente com a fonte."""
    itens = [i for i in json.loads((SAIDA / "itens.json").read_text(encoding="utf-8")) if i["citacao_conferida"]]
    for i in itens:
        regra = SERIES_POR_FONTE.get(i["fonte"]) or series_do_codigo(i["codigo_oficial"])
        if regra:
            i["series"], i["series_por_regra"] = regra, True
    grade = {}
    for pais, series in SERIES.items():
        grade[pais] = []
        for s in series:
            doserie = [i for i in itens if i["pais"] == pais and s in i["series"]]
            grade[pais].append({
                "serie": s, "nome": NOME_SERIE[s],
                "competencias": {c: [
                    {k: i[k] for k in ("tipo", "descricao", "codigo_oficial", "citacao", "url", "pagina", "fonte")}
                    for i in doserie if c in i["competencias"]
                ] for c in COMPETENCIAS},
            })
    gerais = [i for i in itens if not i["series"]]
    (SAIDA / "grade.json").write_text(json.dumps(
        {"gerado_em": datetime.now(timezone.utc).isoformat(), "grade": grade, "sem_serie": gerais},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return grade


SCHEMA_ATIVIDADES = {
    "type": "object", "additionalProperties": False, "required": ["atividades"],
    "properties": {"atividades": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["titulo", "formato", "competencias", "objetivo", "duracao_min", "materiais", "passos",
                     "como_avaliar", "cuidados", "base_itens"],
        "properties": {
            "titulo": {"type": "string"},
            "formato": {"type": "string", "enum": ["gamificada", "sala_de_aula", "plataforma"]},
            "competencias": {"type": "array", "items": {"type": "string", "enum": COMPETENCIAS}},
            "objetivo": {"type": "string"},
            "duracao_min": {"type": "integer"},
            "materiais": {"type": "array", "items": {"type": "string"}},
            "passos": {"type": "array", "items": {"type": "string"}},
            "como_avaliar": {"type": "string"},
            "cuidados": {"type": "string"},
            "base_itens": {"type": "array", "items": {"type": "string"}},
        }}}},
}

PROMPT_ATIVIDADES = """Voce cria atividades socioemocionais para a {nome} ({pais_nome}), para a plataforma escolar Corredor.
Use como base SOMENTE os itens de referencia abaixo, cada um com id, tirados de documentos oficiais e de referencia.
Crie {por_formato} atividades de cada formato, {total} no total:
- gamificada: jogo com regra, pontos coletivos ou desafio, sem ranking que exponha aluno.
- sala_de_aula: exercicio presencial conduzido pelo professor.
- plataforma: exercicio que o aluno faz sozinho na plataforma (tela, escolha, registro no diario), com
  resposta privada que so o aluno e a psicologa veem.
Cubra as cinco competencias ao longo do conjunto. Adeque linguagem e duracao a idade. Passos curtos e concretos.
base_itens: ids dos itens de referencia que sustentam a atividade (pelo menos um, so ids da lista).
Pode adaptar dinamicas citadas pelo Cassiano quando servirem a idade: termometro das emocoes, teia da amizade,
ilha deserta, mala e lixo do projeto de vida, iceberg, cruze a linha, semaforo, roda de conversa de check-in
e check-out, assembleia escolar, aprendizagem baseada em projetos, design thinking.
Escreva em {idioma}.
{regras}

ITENS DE REFERENCIA:
{itens}
"""


def gerar_atividades(*, por_formato: int = 3, series: list[str] | None = None) -> list[dict]:
    grade = json.loads((SAIDA / "grade.json").read_text(encoding="utf-8"))["grade"]
    arq = SAIDA / "atividades_brutas.jsonl"
    feitas = set()
    if arq.exists():
        feitas = {json.loads(l)["serie"] for l in arq.read_text(encoding="utf-8").splitlines()}
    for pais, linhas in grade.items():
        for linha in linhas:
            s = linha["serie"]
            if s in feitas or (series and s not in series):
                continue
            refs, vistos = [], set()
            for c, lista in linha["competencias"].items():
                for i in lista:
                    chave = (i["descricao"], i["url"])
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    refs.append({"id": f"r{len(refs)}", **i})
            if not refs:
                print(f"[atividades] {s}: sem itens de referencia, pulei")
                continue
            texto_refs = "\n".join(
                f"[{r['id']}] ({r['tipo']}, {r['fonte']}) {r['descricao']} | \"{r['citacao']}\"" for r in refs[:60])
            prompt = PROMPT_ATIVIDADES.format(
                nome=linha["nome"], pais_nome="Brasil" if pais == "BR" else "Estados Unidos",
                por_formato=por_formato, total=3 * por_formato, regras=REGRAS_CASA, itens=texto_refs,
                idioma="portugues do Brasil" if pais == "BR" else "ingles (EUA)")
            inicio = time.time()
            resp = chamar_gpt(prompt, SCHEMA_ATIVIDADES)
            por_id = {r["id"]: r for r in refs}
            for a in resp["atividades"]:
                a["fontes"] = [{"url": por_id[b]["url"], "pagina": por_id[b]["pagina"], "citacao": por_id[b]["citacao"]}
                               for b in a.pop("base_itens") if b in por_id]
            with arq.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"pais": pais, "serie": s, "atividades": resp["atividades"]}, ensure_ascii=False) + "\n")
            print(f"[atividades] {pais} {s}: {len(resp['atividades'])} em {time.time() - inicio:.0f}s")
    todas = []
    for l in arq.read_text(encoding="utf-8").splitlines():
        reg = json.loads(l)
        for a in reg["atividades"]:
            todas.append({"pais": reg["pais"], "serie": reg["serie"], "nome_serie": NOME_SERIE[reg["serie"]], **a})
    (SAIDA / "atividades.json").write_text(json.dumps(todas, ensure_ascii=False, indent=2), encoding="utf-8")
    return todas


# ---------------------------------------------------------------- markdown e regras

NOME_COMP = {"autoconhecimento": "Autoconhecimento", "autogestao": "Autogestão",
             "consciencia_social": "Consciência social", "relacionamento": "Habilidades de relacionamento",
             "tomada_de_decisao": "Tomada de decisão responsável"}
PROIBIDAS = re.compile(r"suic[ií]d|automutila|depress[aã]o|depressiv|self-harm|suicid|depression", re.I)
SEPARADOR = re.compile(r"\s[—–]\s|\s-\s")


def checar_regras(texto: str) -> list[str]:
    erros = [f"palavra proibida: {m.group(0)}" for m in PROIBIDAS.finditer(texto)]
    erros += [f"separador de frase: ...{texto[max(0, m.start() - 30):m.end() + 30]}..." for m in SEPARADOR.finditer(texto)]
    return erros


def escrever_markdown() -> None:
    grade = json.loads((SAIDA / "grade.json").read_text(encoding="utf-8"))["grade"]
    atividades = json.loads((SAIDA / "atividades.json").read_text(encoding="utf-8"))
    for pais, titulo in (("BR", "Brasil"), ("US", "Estados Unidos")):
        linhas = [f"# Grade socioemocional por série: {titulo}", "",
                  "Cada linha traz a citação literal e o link da fonte. Gerado pela varredura da ScrapeGraph.", ""]
        for s in grade[pais]:
            linhas += [f"## {s['nome']}", ""]
            vazia = True
            for c, lista in s["competencias"].items():
                if not lista:
                    continue
                vazia = False
                linhas.append(f"**{NOME_COMP[c]}**")
                for i in lista[:12]:
                    cod = f" `{i['codigo_oficial']}`" if i["codigo_oficial"] else ""
                    linhas.append(f"- {i['descricao']}{cod}. Fonte: [{i['fonte']}, p. {i['pagina']}]({i['url']}). "
                                  f"\"{i['citacao']}\"")
                linhas.append("")
            if vazia:
                linhas += ["Nenhum item com série explícita nas fontes coletadas.", ""]
        (SAIDA / f"grade_{pais.lower()}.md").write_text("\n".join(linhas), encoding="utf-8")

        linhas = [f"# Atividades socioemocionais por série: {titulo}", ""]
        for s in grade[pais]:
            doserie = [a for a in atividades if a["serie"] == s["serie"]]
            if not doserie:
                continue
            linhas += [f"## {s['nome']}", ""]
            for a in doserie:
                comps = ", ".join(NOME_COMP[c] for c in a["competencias"])
                linhas += [f"### {a['titulo']}", "",
                           f"Formato: {a['formato'].replace('_', ' ')}. Duração: {a['duracao_min']} min. Competências: {comps}.",
                           "", a["objetivo"], ""]
                if a["materiais"]:
                    linhas += ["Materiais: " + "; ".join(a["materiais"]) + ".", ""]
                linhas += [f"{n}. {p}" for n, p in enumerate(a["passos"], 1)] + [""]
                linhas += [f"Como avaliar: {a['como_avaliar']}", "", f"Cuidados: {a['cuidados']}", ""]
                linhas += ["Base: " + " ".join(f"[{n}]({f['url']})" for n, f in enumerate(a["fontes"], 1)), ""]
        (SAIDA / f"atividades_{pais.lower()}.md").write_text("\n".join(linhas), encoding="utf-8")


# ---------------------------------------------------------------- conferencia por amostra

PROMPT_CONFERIR = """Confira se o item extraido e sustentado pelo trecho da fonte. Responda so JSON:
{{"descricao_ok": true|false, "series_ok": true|false, "comentario": "uma frase"}}
series_ok e true quando as series do item aparecem no trecho ou decorrem de uma faixa citada nele
(ex.: "K-3"), ou quando a lista esta vazia.

ITEM: {item}

TRECHO ({url}, p. {pagina}):
{texto}
"""


def conferir_amostra(*, fracao: float = 0.10, modelo: str = "claude-haiku-5-5", semente: int = 7) -> dict:
    """Segundo modelo confere uma amostra dos itens contra o trecho de origem."""
    import os
    import random

    import anthropic

    itens = json.loads((SAIDA / "itens.json").read_text(encoding="utf-8"))
    por_id = {t["id"]: t for t in json.loads((SAIDA / "trechos.json").read_text(encoding="utf-8"))}
    amostra = random.Random(semente).sample(itens, max(1, int(len(itens) * fracao)))
    cliente = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resultados, uso = [], [0, 0]
    for it in amostra:
        t = por_id[it["trecho_id"]]
        resumo = {k: it[k] for k in ("tipo", "series", "competencias", "descricao", "citacao")}
        r = cliente.messages.create(model=modelo, max_tokens=2000, messages=[{"role": "user", "content":
            PROMPT_CONFERIR.format(item=json.dumps(resumo, ensure_ascii=False), url=t["url"], pagina=t["pagina"], texto=t["texto"])}])
        uso[0] += r.usage.input_tokens
        uso[1] += r.usage.output_tokens
        bruto = next((b.text for b in r.content if b.type == "text"), "")
        try:
            veredito = json.loads(bruto[bruto.index("{"): bruto.rindex("}") + 1])
        except ValueError:
            veredito = {"descricao_ok": None, "series_ok": None, "comentario": bruto[:200]}
        resultados.append({"trecho_id": it["trecho_id"], "descricao": it["descricao"], **veredito})
    resumo = {
        "modelo": modelo, "amostra": len(resultados),
        "descricao_ok": sum(1 for r in resultados if r["descricao_ok"]),
        "series_ok": sum(1 for r in resultados if r["series_ok"]),
        "tokens_entrada": uso[0], "tokens_saida": uso[1], "resultados": resultados,
    }
    (SAIDA / "conferencia_amostra.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumo


# ---------------------------------------------------------------- plano de ensino

PERIODOS = {"BR": [f"{n}º bimestre" for n in range(1, 5)], "US": [f"Quarter {n}" for n in range(1, 5)]}

PROMPT_PLANO = """Voce monta o plano de ensino socioemocional do ano para a {nome} ({pais_nome}), na plataforma escolar Corredor.
O ano tem quatro periodos: {periodos}.
Para cada periodo, nesta ordem:
- competencia_foco: uma das cinco do CASEL. As cinco aparecem ao longo do ano, com progressao (do eu para o outro
  e para as escolhas). Um periodo pode ter uma competencia secundaria, que entra so nos objetivos.
- objetivos: de 3 a 5 ids da lista OBJETIVOS abaixo, coerentes com a competencia do periodo. So ids da lista.
- atividades: titulos exatos da lista ATIVIDADES. Distribua as {n_ativ} atividades ao longo do ano, cada uma em um
  periodo so, todas usadas.
- encontros: de 2 a 4 encontros em tempo de aula, cada um com tema curto e a atividade usada (titulo exato da
  lista, ou "conversa de abertura" ou "fechamento do periodo").
- gesto_professor: um gesto do professor no dia a dia da turma, fora dos encontros, que sustente a competencia.
- avaliacao: so portfolio e autoavaliacao, sem nota.
- cuidados: o que evitar naquele periodo.
objetivo_ano: uma ou duas frases com o que a turma desenvolve no ano.
Toda atividade acontece em tempo de aula, fecha em uma acao concreta e usa exemplo ficticio.
Escreva em {idioma}.
{regras}

OBJETIVOS (da grade, com fonte):
{objetivos}

ATIVIDADES (do catalogo desta serie):
{atividades}
"""


def _schema_plano(ids_obj: list[str], titulos: list[str]) -> dict:
    encontro = {"type": "object", "additionalProperties": False, "required": ["tema", "atividade"],
                "properties": {"tema": {"type": "string"}, "atividade": {"type": "string"}}}
    periodo = {
        "type": "object", "additionalProperties": False,
        "required": ["competencia_foco", "objetivos", "atividades", "encontros", "gesto_professor", "avaliacao", "cuidados"],
        "properties": {
            "competencia_foco": {"type": "string", "enum": COMPETENCIAS},
            "objetivos": {"type": "array", "items": {"type": "string", "enum": ids_obj}},
            "atividades": {"type": "array", "items": {"type": "string", "enum": titulos}},
            "encontros": {"type": "array", "items": encontro},
            "gesto_professor": {"type": "string"},
            "avaliacao": {"type": "string"},
            "cuidados": {"type": "string"},
        }}
    return {"type": "object", "additionalProperties": False, "required": ["objetivo_ano", "periodos"],
            "properties": {"objetivo_ano": {"type": "string"},
                           "periodos": {"type": "array", "items": periodo}}}


def _objetivos_da_serie(linha: dict, por_comp: int = 12) -> list[dict]:
    """Ate por_comp itens de cada competencia, sem repetir descricao, com id curto."""
    refs, vistos = [], set()
    for c in COMPETENCIAS:
        n = 0
        for i in linha["competencias"][c]:
            chave = (i["descricao"], i["url"])
            if chave in vistos or n >= por_comp:
                continue
            vistos.add(chave)
            n += 1
            refs.append({"id": f"o{len(refs)}", "competencia": c, **i})
    return refs


def conferir_plano(plano: dict, refs: list[dict], titulos: list[str]) -> list[str]:
    """Problemas deterministicos: objetivo fora da grade, atividade inventada, repetida ou esquecida."""
    ids = {r["id"] for r in refs}
    problemas, usadas = [], []
    if len(plano["periodos"]) != 4:
        problemas.append(f"{len(plano['periodos'])} periodos em vez de 4")
    for n, p in enumerate(plano["periodos"], 1):
        problemas += [f"periodo {n}: objetivo {o} fora da grade" for o in p["objetivos"] if o not in ids]
        problemas += [f"periodo {n}: atividade inventada {a}" for a in p["atividades"] if a not in titulos]
        usadas += p["atividades"]
    problemas += [f"atividade repetida: {a}" for a in sorted({a for a in usadas if usadas.count(a) > 1})]
    problemas += [f"atividade sem periodo: {a}" for a in titulos if a not in usadas]
    focos = {p["competencia_foco"] for p in plano["periodos"]}
    objs = {next(r["competencia"] for r in refs if r["id"] == o) for p in plano["periodos"] for o in p["objetivos"] if o in ids}
    faltam = set(COMPETENCIAS) - focos - objs
    problemas += [f"competencia ausente no ano: {c}" for c in sorted(faltam)]
    return problemas


def gerar_plano_ensino(*, series: list[str] | None = None) -> list[dict]:
    grade = json.loads((SAIDA / "grade.json").read_text(encoding="utf-8"))["grade"]
    atividades = json.loads((SAIDA / "atividades.json").read_text(encoding="utf-8"))
    arq = SAIDA / "plano_ensino_brutas.jsonl"
    feitas = set()
    if arq.exists():
        feitas = {json.loads(l)["serie"] for l in arq.read_text(encoding="utf-8").splitlines()}
    for pais, linhas in grade.items():
        for linha in linhas:
            s = linha["serie"]
            if s in feitas or (series and s not in series):
                continue
            refs = _objetivos_da_serie(linha)
            ativ = [a for a in atividades if a["pais"] == pais and a["serie"] == s]
            titulos = [a["titulo"] for a in ativ]
            if not refs or not ativ:
                print(f"[plano] {s}: sem objetivos ou atividades, pulei")
                continue
            prompt = PROMPT_PLANO.format(
                nome=linha["nome"], pais_nome="Brasil" if pais == "BR" else "Estados Unidos",
                periodos=", ".join(PERIODOS[pais]), n_ativ=len(titulos), regras=REGRAS_CASA,
                idioma="portugues do Brasil" if pais == "BR" else "ingles (EUA)",
                objetivos="\n".join(f"[{r['id']}] ({r['competencia']}) {r['descricao']}" for r in refs),
                atividades="\n".join(f"- {a['titulo']} ({a['formato']}; {', '.join(a['competencias'])})" for a in ativ))
            inicio = time.time()
            plano = chamar_gpt(prompt, _schema_plano([r["id"] for r in refs], titulos))
            problemas = conferir_plano(plano, refs, titulos)
            por_id = {r["id"]: r for r in refs}
            for nome_periodo, p in zip(PERIODOS[pais], plano["periodos"]):
                p["periodo"] = nome_periodo
                p["objetivos"] = [{k: por_id[o][k] for k in ("competencia", "descricao", "codigo_oficial", "url", "pagina", "fonte", "citacao")}
                                  for o in p["objetivos"] if o in por_id]
            reg = {"pais": pais, "serie": s, "nome_serie": linha["nome"], **plano, "problemas": problemas}
            with arq.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(reg, ensure_ascii=False) + "\n")
            print(f"[plano] {pais} {s}: {len(problemas)} problemas em {time.time() - inicio:.0f}s")
    planos = [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines()]
    (SAIDA / "plano_ensino.json").write_text(json.dumps(planos, ensure_ascii=False, indent=2), encoding="utf-8")
    return planos


def escrever_markdown_plano() -> None:
    planos = json.loads((SAIDA / "plano_ensino.json").read_text(encoding="utf-8"))
    rotulos = {
        "BR": {"titulo": "Plano de ensino socioemocional por série: Brasil", "ano": "Objetivo do ano", "foco": "Foco",
               "obj": "Objetivos de aprendizagem", "ativ": "Atividades do catálogo", "enc": "Encontros",
               "gesto": "Gesto do professor", "aval": "Avaliação", "cuid": "Cuidados", "fonte": "fonte"},
        "US": {"titulo": "Social emotional teaching plan by grade: United States", "ano": "Goal for the year",
               "foco": "Focus", "obj": "Learning objectives", "ativ": "Catalog activities", "enc": "Sessions",
               "gesto": "Teacher's daily practice", "aval": "Assessment", "cuid": "Cautions", "fonte": "source"},
    }
    nome_comp = {"BR": NOME_COMP, "US": {"autoconhecimento": "Self-awareness", "autogestao": "Self-management",
                 "consciencia_social": "Social awareness", "relacionamento": "Relationship skills",
                 "tomada_de_decisao": "Responsible decision-making"}}
    for pais in ("BR", "US"):
        r = rotulos[pais]
        linhas = [f"# {r['titulo']}", ""]
        for pl in [p for p in planos if p["pais"] == pais]:
            linhas += [f"## {pl['nome_serie']}", "", f"**{r['ano']}:** {pl['objetivo_ano']}", ""]
            for p in pl["periodos"]:
                linhas += [f"### {p['periodo']}. {r['foco']}: {nome_comp[pais][p['competencia_foco']]}", "", f"**{r['obj']}**"]
                for o in p["objetivos"]:
                    cod = f" `{o['codigo_oficial']}`" if o["codigo_oficial"] else ""
                    linhas.append(f"- {o['descricao']}{cod} ([{r['fonte']}, p. {o['pagina']}]({o['url']}))")
                linhas += ["", f"**{r['ativ']}:** " + "; ".join(p["atividades"]) + ".", "", f"**{r['enc']}**"]
                linhas += [f"{n}. {e['tema']} ({e['atividade']})" for n, e in enumerate(p["encontros"], 1)]
                linhas += ["", f"**{r['gesto']}:** {p['gesto_professor']}", "", f"**{r['aval']}:** {p['avaliacao']}", "",
                           f"**{r['cuid']}:** {p['cuidados']}", ""]
        (SAIDA / f"plano_ensino_{pais.lower()}.md").write_text("\n".join(linhas), encoding="utf-8")
