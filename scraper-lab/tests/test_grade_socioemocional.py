import zipfile

from scraper_lab import grade_socioemocional as g


def test_checar_regras_pega_palavra_proibida_e_travessao():
    erros = g.checar_regras("O aluno com depressão — e a turma toda")
    assert any("proibida" in e for e in erros)
    assert any("separador" in e for e in erros)


def test_checar_regras_aceita_hifen_dentro_de_palavra():
    assert g.checar_regras("Autoavaliação no pré-teste e no Alerta de Estado Emocional.") == []


def test_texto_docx_le_paragrafos(tmp_path):
    caminho = tmp_path / "a.docx"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("word/document.xml", "<w:body><w:p><w:r><w:t>Self-awareness</w:t></w:r></w:p>"
                                        "<w:p><w:r><w:t>Grades 1-3</w:t></w:r></w:p></w:body>")
    assert g._texto_docx(caminho) == ["Self-awareness\nGrades 1-3"]


def test_citacao_normalizada_ignora_espacos_e_caixa():
    assert g._normalizar("Conhecer-se,\n  apreciar-se") in g._normalizar("Ele deve CONHECER-SE, apreciar-se e cuidar")


def test_series_do_codigo_bncc():
    assert g.series_do_codigo("EF15LP09") == ["1ano", "2ano", "3ano", "4ano", "5ano"]
    assert g.series_do_codigo("EF06HI01") == ["6ano"]
    assert g.series_do_codigo("EF89LP12") == ["8ano", "9ano"]
    assert g.series_do_codigo("EM13CHS101") == ["em1", "em2", "em3"]
    assert g.series_do_codigo("EI03EO01") == ["pre_escola"]
    assert g.series_do_codigo("CG8") is None


def _plano(periodos):
    return {"objetivo_ano": "x", "periodos": periodos}


def _periodo(foco, objetivos, atividades):
    return {"competencia_foco": foco, "objetivos": objetivos, "atividades": atividades, "encontros": [],
            "gesto_professor": "", "avaliacao": "", "cuidados": ""}


def test_conferir_plano_aceita_ano_completo():
    refs = [{"id": f"o{n}", "competencia": c} for n, c in enumerate(g.COMPETENCIAS)]
    plano = _plano([_periodo("autoconhecimento", ["o0"], ["A"]), _periodo("autogestao", ["o1"], ["B"]),
                    _periodo("consciencia_social", ["o2", "o3"], ["C"]), _periodo("tomada_de_decisao", ["o4"], [])])
    assert g.conferir_plano(plano, refs, ["A", "B", "C"]) == []


def test_conferir_plano_aponta_inventado_repetido_e_esquecido():
    refs = [{"id": "o0", "competencia": "autoconhecimento"}]
    plano = _plano([_periodo("autoconhecimento", ["o0", "o9"], ["A", "Z"]), _periodo("autoconhecimento", [], ["A"])])
    problemas = g.conferir_plano(plano, refs, ["A", "B"])
    assert "2 periodos em vez de 4" in problemas
    assert any("o9 fora da grade" in p for p in problemas)
    assert any("inventada Z" in p for p in problemas)
    assert "atividade repetida: A" in problemas
    assert "atividade sem periodo: B" in problemas
    assert any("competencia ausente" in p for p in problemas)
