"""
Extrator das asociadas da AMAI, a associacao mexicana de agencias de
inteligencia de mercado y opinion (amai.org).

Conformidade: o robots.txt da AMAI nao tem nenhum Disallow, mas declara
`Crawl-delay: 30`. Por isso o intervalo padrao aqui e 30s e nao os 1,5s do
resto do projeto: a regra do site e mais restritiva que a nossa e vence.
A coleta inteira leva cerca de meia hora, o que e o preco de respeitar isso.

A home monta a lista de asociados por AJAX, mas os endpoints
(BuscoAsociados1_AJAX.php / BuscoAsociados2_AJAX.php) devolvem HTML pronto
num GET simples. Nao precisamos de navegador; a mesma lista tambem aparece
em Asociados_AMAI.php, que e a fonte primaria usada aqui.

A ficha de cada asociada e uma tabela rotulo/valor estavel, o que permite
extrair por rotulo em vez de por posicao.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.amai.org/"
LISTAGEM = BASE + "Asociados_AMAI.php"
# Pagina das certificadas: e a mesma lista, mas traz duas asociadas que nao
# aparecem na listagem principal. Sem ela a base sairia incompleta.
LISTAGEM_CERTIFICADAS = BASE + "Asociados_AMAI_Certificados.php"
PAIS = "Mexico"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Crawl-delay declarado no robots.txt de amai.org.
PAUSA_ROBOTS = 30.0

_ESPACOS = re.compile(r"\s+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@\s?[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NAO_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$", re.I)
_EMAIL_PLACEHOLDER = re.compile(
    r"^(usuario|user|ejemplo|example|correo|email|e-mail|nombre|tu|su|abc|test|"
    r"sample)@(dominio|domain|ejemplo|example|correo|email|tudominio|"
    r"sudominio|mail)\.", re.I)

# Contato institucional da AMAI: esta no rodape de todas as paginas.
_EMAIL_ASSOCIACAO = {"amai@amai.org"}
_DOMINIO_ASSOCIACAO = ("amai.org", "campusamai.org", "d-virtual.mx")
_TELEFONE_ASSOCIACAO = {"+52(55)5545-1465", "525555451465", "5555451465"}

_PERFIL = re.compile(r"(?:Asociados_AMAI_Contacto|quienesMiembrosDet)\.php"
                     r"\?ID_socio=([A-Za-z0-9]+)")

# Rotulo na ficha -> campo do registro.
_CAMPOS = {
    "razon social": "nome",
    "direccion": "endereco",
    "telefono": "telefone",
    "e-mail": "email",
    "email": "email",
    "website": "site",
    "contacto": "contato",
    "certificados": "certificados",
    "fax": "fax",
}

_ACENTOS = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüñç", "aaaaaeeeeiiiiooooouuuunc")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _so_letras(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def _chave_rotulo(t: str) -> str:
    return _limpar(t).rstrip(":").lower().translate(_ACENTOS)


def _normalizar_email(v: str) -> str:
    v = _ESPACOS.sub("", (v or "").strip().lower()).strip(".,;:")
    if not v or _NAO_EMAIL.search(v) or _EMAIL_PLACEHOLDER.match(v):
        return ""
    if v in _EMAIL_ASSOCIACAO:
        return ""
    if any(d == v.split("@")[-1] for d in _DOMINIO_ASSOCIACAO):
        return ""
    return v


def _baixar(url: str, timeout: int = 45) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe: {url}")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "es-MX,es;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(4_000_000).decode("utf-8", errors="replace")


@dataclass
class Asociada:
    url_perfil: str
    id_socio: str = ""
    nome: str = ""
    nome_comercial: str = ""   # nome do logo, quando difere da razao social
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    estado: str = ""
    cidade: str = ""
    contato: str = ""
    certificados: str = ""
    fax: str = ""
    fonte_listagem: str = ""
    coletado_em: str = ""
    erro: str = ""
    emails_extras: list[str] = field(default_factory=list)


def _ids_da_pagina(html: str) -> dict[str, str]:
    """{id_socio: nome do alt do logo} encontrados numa listagem."""
    sopa = BeautifulSoup(html, "html.parser")
    achados: dict[str, str] = {}
    for a in sopa.select("a[href]"):
        m = _PERFIL.search(a["href"])
        if not m:
            continue
        img = a.find("img")
        alt = _limpar(img.get("alt")) if img else ""
        if m.group(1) not in achados or not achados[m.group(1)]:
            achados[m.group(1)] = alt
    return achados


def listar_asociadas(*, delay: float = PAUSA_ROBOTS,
                     verbose: bool = True) -> list[tuple[str, str, str, str]]:
    """
    (id_socio, nome do logo, url da ficha, listagem de origem) de cada asociada.

    Cruzamos a listagem principal com a das certificadas porque as duas
    divergem; usar so uma delas perderia asociadas sem aviso nenhum.
    """
    principais = _ids_da_pagina(_baixar(LISTAGEM))
    time.sleep(delay)
    certificadas = _ids_da_pagina(_baixar(LISTAGEM_CERTIFICADAS))

    if verbose:
        print(f"      {len(principais)} na listagem principal, "
              f"{len(certificadas)} na de certificadas, "
              f"{len(set(certificadas) - set(principais))} so nas certificadas")

    itens: list[tuple[str, str, str, str]] = []
    for sid, alt in principais.items():
        itens.append((sid, alt, f"{BASE}Asociados_AMAI_Contacto.php?ID_socio={sid}",
                      "listagem"))
    for sid, alt in certificadas.items():
        if sid not in principais:
            itens.append((sid, alt, f"{BASE}Asociados_AMAI_Contacto.php?ID_socio={sid}",
                          "so_certificadas"))
    return itens


def _partes_endereco(td) -> list[str]:
    """
    Linhas do endereco, separadas apenas por <br>.

    O HTML tambem quebra linha no meio de um trecho ("Jalisco,\\n Guadalajara").
    Se dividissemos por quebra de linha crua, estado e cidade virariam dois
    itens e o par "<estado>, <ciudad>" nunca seria reconhecido.
    """
    copia = BeautifulSoup(str(td), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\x00")
    return [_limpar(p) for p in copia.get_text(" ").split("\x00") if _limpar(p)]


def extrair_asociada(html: str, url: str, sid: str = "", nome_logo: str = "",
                     fonte: str = "") -> Asociada:
    # O logo traz o nome de mercado ("BRAIN") e a ficha, a razao social
    # ("BRAND INVESTIGATION"). Guardamos os dois: a razao social identifica a
    # empresa, o nome de mercado e o que casa com as outras bases do projeto.
    reg = Asociada(url_perfil=url, id_socio=sid, nome=nome_logo, fonte_listagem=fonte,
                   coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")

    h1 = sopa.find("h1")
    if h1:
        pequeno = h1.find("small")
        if pequeno:
            pequeno.extract()
        titulo = _limpar(h1.get_text())
        if titulo:
            reg.nome = titulo

    tabela = sopa.select_one("table.table-bordered")
    if tabela is None:
        # Sem tabela nao ha ficha; o nome do logo sozinho nao e registro util.
        reg.erro = "tabela de contato ausente"
        return reg

    partes_end: list[str] = []
    for tr in tabela.find_all("tr"):
        tds = tr.find_all("td", recursive=False) or tr.find_all("td")
        if len(tds) < 2:
            continue
        campo = _CAMPOS.get(_chave_rotulo(tds[0].get_text()))
        if not campo:
            continue
        valor_td = tds[1]

        if campo == "email":
            # Varias fichas colam dois enderecos no mesmo link
            # ("ana@exemplo.com.mx-bruno@exemplo.com.mx") ou deixam uma
            # barra no fim. Por isso extraimos por regex em vez de aproveitar
            # o texto do link inteiro: cada endereco sai separado e limpo.
            achados: list[str] = []
            fontes = []
            for a in valor_td.select('a[href^="mailto:"]'):
                fontes.append(_limpar(a.get_text()))
                fontes.append(a["href"][7:].split("?")[0])
            fontes.append(valor_td.get_text(" "))
            for fonte in fontes:
                for bruto in _EMAIL.findall(fonte):
                    v = _normalizar_email(bruto)
                    if v and v not in achados:
                        achados.append(v)
            if achados:
                reg.email, reg.emails_extras = achados[0], achados[1:4]
            continue

        if campo == "site":
            link = valor_td.find("a", href=True)
            valor = link["href"] if link else _limpar(valor_td.get_text())
            valor = valor.split("?")[0].strip()
            dominio = valor.split("//", 1)[-1].split("/")[0].lower()
            reg.site = "" if any(d in dominio for d in _DOMINIO_ASSOCIACAO) else valor
            continue

        if campo == "endereco":
            partes_end = _partes_endereco(valor_td)
            continue

        if campo == "certificados":
            itens = [_limpar(a.get_text()) for a in valor_td.find_all("a")]
            reg.certificados = " | ".join(i for i in itens if i) or _limpar(valor_td.get_text())
            continue

        setattr(reg, campo, _limpar(valor_td.get_text(" ")))

    if reg.telefone.replace(" ", "") in _TELEFONE_ASSOCIACAO:
        reg.telefone = ""

    reg.endereco = ", ".join(partes_end)
    # A ultima linha do endereco e "<estado>, <ciudad>". So separamos quando ha
    # exatamente uma virgula: nomes de municipio com virgula estragariam o par.
    if partes_end and partes_end[-1].count(",") == 1:
        estado, cidade = (p.strip() for p in partes_end[-1].split(","))
        reg.estado, reg.cidade = estado, cidade

    if _so_letras(reg.nome) != _so_letras(nome_logo):
        reg.nome_comercial = nome_logo

    if not reg.nome:
        reg.erro = "ficha sem razao social"
    return reg


def coletar(itens: list[tuple[str, str, str, str]], *, delay: float = PAUSA_ROBOTS,
            verbose: bool = True) -> list[Asociada]:
    saida: list[Asociada] = []
    for i, (sid, nome_logo, url, fonte) in enumerate(itens, 1):
        try:
            reg = extrair_asociada(_baixar(url), url, sid, nome_logo, fonte)
        except Exception as exc:
            # Falha de rede nao vira veredito: guardamos o motivo para que a
            # conferencia final mostre o que merece nova tentativa.
            reg = Asociada(url_perfil=url, id_socio=sid, nome=nome_logo,
                           fonte_listagem=fonte,
                           erro=f"{type(exc).__name__}: {exc}"[:150],
                           coletado_em=datetime.now(timezone.utc).isoformat())
        saida.append(reg)
        if verbose:
            print(f"  [{i:>2}/{len(itens)}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:30]:30} | {reg.email[:34]:34} | {reg.estado[:14]}")
        if i < len(itens):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "nome_comercial", "email", "site", "pais", "estado", "cidade", "telefone",
           "endereco", "descricao", "contato", "certificados", "fax",
           "emails_extras", "fonte_listagem", "id_socio", "url_perfil", "erro"]


def exportar(regs: list[Asociada], nome: str = "amai_mexico") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(r) for r in regs], ensure_ascii=False, indent=2),
                  encoding="utf-8")
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for r in regs:
            d = asdict(r)
            d["emails_extras"] = " | ".join(d.get("emails_extras") or [])
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
