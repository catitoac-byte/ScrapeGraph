"""
Extrator do diretorio da Esomar (directory.esomar.org).

O site e um app Angular com DOM regular, entao a extracao e deterministica:
seletores semanticos, sem LLM e sem custo de API.

Nao usa a API interna (datahub.esomar.org), que responde 401 sem chave.
Navegamos pela interface publica, que o robots.txt libera (Allow: /).
"""

from __future__ import annotations

import csv
import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"
BASE = "https://directory.esomar.org"

# Contatos institucionais da propria Esomar, presentes no rodape de toda
# pagina. Precisam ser descartados para nao virarem dado da empresa.
RODAPE_EMAIL = "directory@esomar.org"
RODAPE_TEL = "+31206642141"

_ESPACOS = re.compile(r"\s+")


def _limpar(texto: str | None) -> str:
    return _ESPACOS.sub(" ", texto).strip() if texto else ""


@dataclass
class Contato:
    nome: str
    cargo: str = ""
    membro_esomar: bool = False


@dataclass
class Empresa:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = ""
    telefone: str = ""
    endereco: str = ""
    linkedin: str = ""
    fundacao: str = ""
    funcionarios: str = ""
    tipos: list[str] = field(default_factory=list)
    contatos: list[Contato] = field(default_factory=list)
    coletado_em: str = ""
    erro: str = ""


# --------------------------------------------------------------------------
# Listagem
# --------------------------------------------------------------------------

def _ir_para(page: Page, url: str, *, espera_ms: int = 2000) -> None:
    """
    Navega tolerando paginas que nunca ficam ociosas.

    Alguns perfis mantem atividade de rede continua e jamais disparam
    "networkidle", estourando o timeout mesmo estando saudaveis. Nesses
    casos "domcontentloaded" carrega sem problema.
    """
    try:
        page.goto(url, wait_until="networkidle", timeout=30_000)
    except Exception:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        espera_ms = max(espera_ms, 4000)  # sem idle, damos mais folga ao render
    page.wait_for_timeout(espera_ms)


def _links_da_pagina(page: Page) -> list[str]:
    """Hrefs relativos /company/<id>/<slug> da pagina atual."""
    hrefs = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    return [h for h in hrefs if h and h.startswith("/company/")]


def listar_urls(
    url_busca: str,
    *,
    max_paginas: int = 30,
    delay: float = 1.5,
    headless: bool = True,
    verbose: bool = True,
) -> list[str]:
    """
    Percorre a paginacao e devolve as URLs de perfil, sem repeticao.

    Cada pagina traz 3 resultados patrocinados que se repetem em todas elas,
    mais os organicos. A deduplicacao por ID resolve isso. Paramos apos DUAS
    paginas seguidas sem novidade, para que um render lento nao trunque.
    """
    base_sem_pn = re.sub(r"[&?]pn=\d+", "", url_busca)
    sep = "&" if "?" in base_sem_pn else "?"

    vistos: dict[str, str] = {}
    vazias = 0
    falhas = 0
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        page = navegador.new_page()
        try:
            for n in range(1, max_paginas + 1):
                # Uma pagina que falha nao pode derrubar a listagem inteira:
                # tentamos duas vezes e, persistindo, seguimos para a proxima.
                links: list[str] | None = None
                for tentativa in (1, 2):
                    try:
                        _ir_para(page, f"{base_sem_pn}{sep}pn={n}", espera_ms=2500)
                        links = _links_da_pagina(page)
                        break
                    except Exception as exc:
                        if verbose:
                            print(f"  pagina {n:>2}: falha ({type(exc).__name__}), "
                                  f"tentativa {tentativa}/2")
                        time.sleep(3)
                if links is None:
                    falhas += 1
                    if falhas >= 3:
                        if verbose:
                            print(f"  3 paginas falharam; encerrando esta listagem")
                        break
                    continue

                novos = 0
                for href in links:
                    ident = href.split("/")[2]
                    if ident not in vistos:
                        vistos[ident] = BASE + href
                        novos += 1

                if verbose:
                    print(f"  pagina {n:>2}: +{novos:>2} novos | acumulado {len(vistos)}")
                # Duas paginas vazias seguidas para parar. Com uma so, um
                # render lento truncaria a listagem silenciosamente.
                vazias = vazias + 1 if novos == 0 else 0
                if vazias >= 2:
                    break
                time.sleep(delay + random.uniform(0, 0.5))
        finally:
            navegador.close()

    return list(vistos.values())


# --------------------------------------------------------------------------
# Perfil
# --------------------------------------------------------------------------

_JS_INFO = r"""
() => {
  const anchors = [...document.querySelectorAll('a[href]')];
  const href = a => a.getAttribute('href') || '';
  const texto = el => (el?.innerText || '').replace(/\s+/g, ' ').trim();

  // Rotulo -> valor, para blocos do tipo "FOUNDED / 1978"
  const porRotulo = (rotulo) => {
    for (const el of document.querySelectorAll('p, div, span')) {
      if (el.children.length === 0 && texto(el).toUpperCase() === rotulo) {
        const irmao = el.nextElementSibling;
        if (irmao) return texto(irmao);
      }
    }
    return '';
  };

  // Endereco: paragrafo que contem o span "Headquarters"
  let endereco = '';
  for (const p of document.querySelectorAll('p')) {
    const s = p.querySelector('span');
    if (s && texto(s).toLowerCase() === 'headquarters') {
      endereco = texto(p).replace(/^headquarters\s*/i, '');
      break;
    }
  }

  // COMPANY TYPE vem como lista de itens iniciados por "- "
  const tipos = (() => {
    const corpo = document.body.innerText;
    const i = corpo.indexOf('COMPANY TYPE');
    if (i < 0) return [];
    const resto = corpo.slice(i);
    const f = resto.search(/PROFESSIONAL ASSOCIATIONS|Burgemeester/);
    return (f > 0 ? resto.slice(0, f) : resto)
      .split('\n').map(l => l.trim())
      .filter(l => l.startsWith('- '))
      .map(l => l.slice(2).trim());
  })();

  return {
    nome: texto(document.querySelector('h1')),
    emails: anchors.filter(a => href(a).startsWith('mailto:'))
                   .map(a => href(a).slice(7).split('?')[0]),
    telefones: anchors.filter(a => href(a).startsWith('tel:'))
                      .map(a => href(a).slice(4)),
    site: (anchors.find(a => texto(a).toLowerCase() === 'website') || {}).href || '',
    linkedin: (anchors.find(a => href(a).includes('linkedin.com')
                               && !href(a).includes('esomar')) || {}).href || '',
    endereco,
    fundacao: porRotulo('FOUNDED'),
    funcionarios: porRotulo('EMPLOYEES'),
    tipos,
  };
}
"""

_JS_PESSOAS = r"""
() => {
  const corpo = document.body.innerText;
  const ini = corpo.indexOf('PEOPLE');
  if (ini < 0) return [];
  const fim = corpo.indexOf('COMPANY INFO', ini);
  const bloco = corpo.slice(ini, fim > 0 ? fim : ini + 2000);
  return bloco.split('\n').map(l => l.trim()).filter(Boolean);
}
"""

# Uma linha e nome quando comeca com tratamento (Mr./Ms./Dr./Mrs.).
_TRATAMENTO = re.compile(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+", re.I)
# "Esomar Member" NAO entra aqui: e um selo do contato anterior,
# nao um cabecalho de secao.
_SECAO = {"PEOPLE", "MEMBERS"}
_SELO_MEMBRO = "esomar member"


def _parsear_pessoas(linhas: list[str]) -> list[Contato]:
    """
    O bloco PEOPLE vem como texto corrido:
        MEMBERS / Mr. Jerry Thomas / CEO, Founder / Esomar Member / PEOPLE / ...
    Uma linha apos um nome e cargo, salvo se for marcador de secao.
    """
    contatos: list[Contato] = []
    for linha in linhas:
        if linha.upper() in _SECAO:
            continue
        if _TRATAMENTO.match(linha):
            contatos.append(Contato(nome=linha))
        elif not contatos:
            continue
        elif linha.lower() == _SELO_MEMBRO:
            contatos[-1].membro_esomar = True
        elif not contatos[-1].cargo:
            contatos[-1].cargo = linha
    return contatos


# Paises cujo nome contem virgula. Sem isso, "Korea, Republic of" vira
# "Republic of" ao cortar no ultimo separador.
_PAISES_COM_VIRGULA = (
    "Korea, Republic of",
    "Korea, Democratic People's Republic of",
    "Congo, Democratic People's Republic",
    "Congo, Republic of",
    "Virgin Islands, British",
    "Virgin Islands, U.S.",
    "Taiwan, Province of China",
    "Macedonia, the former Yugoslav Republic of",
    "Moldova, Republic of",
    "Tanzania, United Republic of",
    "Bolivia, Plurinational State of",
    "Venezuela, Bolivarian Republic of",
)


def _pais_do_endereco(endereco: str) -> str:
    """
    Ultimo trecho do endereco, com duas ressalvas.

    Nomes de pais podem conter virgula, entao conferimos primeiro se o
    endereco termina com um deles. Endereco sem pais reconhecivel devolve
    o ultimo trecho como antes, e a normalizacao posterior decide.
    """
    limpo = endereco.strip().rstrip(".")
    baixo = limpo.lower()
    for pais in _PAISES_COM_VIRGULA:
        if baixo.endswith(pais.lower()):
            return pais
    partes = [p.strip() for p in limpo.split(",") if p.strip()]
    return partes[-1] if partes else ""


def extrair_empresa(page: Page, url: str) -> Empresa:
    """Abre um perfil, percorre a aba PEOPLE e devolve os campos."""
    empresa = Empresa(url_perfil=url, coletado_em=datetime.now(timezone.utc).isoformat())
    try:
        _ir_para(page, url, espera_ms=2000)

        info = page.evaluate(_JS_INFO)
        empresa.nome = _limpar(info["nome"])
        empresa.endereco = _limpar(info["endereco"])
        empresa.pais = _pais_do_endereco(empresa.endereco)
        empresa.site = info["site"]
        empresa.linkedin = info["linkedin"]
        empresa.fundacao = _limpar(info["fundacao"])
        empresa.funcionarios = _limpar(info["funcionarios"])
        empresa.tipos = [_limpar(t) for t in info.get("tipos", []) if _limpar(t)]

        emails = [e for e in info["emails"] if e.lower() != RODAPE_EMAIL]
        empresa.email = emails[0] if emails else ""
        tels = [t for t in info["telefones"] if t.replace(" ", "") != RODAPE_TEL]
        empresa.telefone = _limpar(tels[0]) if tels else ""

        try:
            page.get_by_text("PEOPLE", exact=True).first.click(timeout=6000)
            page.wait_for_timeout(1800)
            empresa.contatos = _parsear_pessoas(page.evaluate(_JS_PESSOAS))
        except Exception:
            empresa.contatos = []

    except Exception as exc:
        empresa.erro = f"{type(exc).__name__}: {exc}"[:200]
    return empresa


def raspar_perfis(
    urls: list[str],
    *,
    delay: float = 2.0,
    headless: bool = True,
    verbose: bool = True,
) -> list[Empresa]:
    """Visita cada perfil, com pausa entre requisicoes."""
    empresas: list[Empresa] = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        page = navegador.new_page()
        try:
            for i, url in enumerate(urls, 1):
                emp = extrair_empresa(page, url)
                empresas.append(emp)
                if verbose:
                    marca = "!" if emp.erro else "."
                    print(f"  [{i:>3}/{len(urls)}] {marca} {emp.nome[:40]:40} | "
                          f"{emp.email[:32]:32} | {len(emp.contatos)} contatos")
                if i < len(urls):
                    time.sleep(delay + random.uniform(0, 0.6))
        finally:
            navegador.close()
    return empresas


# --------------------------------------------------------------------------
# Saida
# --------------------------------------------------------------------------

COLUNAS = [
    "nome", "email", "site", "pais", "telefone", "endereco", "linkedin",
    "fundacao", "funcionarios", "tipos", "contatos", "url_perfil", "erro",
]


def exportar(empresas: list[Empresa], nome_base: str = "esomar") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    caminho_json = SAIDA / f"{nome_base}.json"
    caminho_csv = SAIDA / f"{nome_base}.csv"

    caminho_json.write_text(
        json.dumps([asdict(e) for e in empresas], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with caminho_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            linha = asdict(e)
            linha["tipos"] = " | ".join(linha["tipos"])
            linha["contatos"] = " | ".join(
                f"{c['nome']}" + (f" ({c['cargo']})" if c["cargo"] else "")
                for c in linha["contatos"]
            )
            w.writerow({k: linha.get(k, "") for k in COLUNAS})

    return caminho_json, caminho_csv
