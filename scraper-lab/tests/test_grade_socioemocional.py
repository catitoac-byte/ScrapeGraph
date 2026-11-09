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
