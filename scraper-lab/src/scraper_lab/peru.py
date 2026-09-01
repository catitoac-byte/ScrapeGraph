"""
Extrator das asociadas da APEIM, a associacao peruana de empresas de
inteligencia de mercados (apeim.com.pe/directorio-de-asociadas).

O robots.txt do site traz `Disallow:` vazio, que na especificacao significa
liberar tudo. Ainda assim cada URL passa pelo verificador antes da
requisicao, porque a regra pode mudar entre uma coleta e outra.

Paginas renderizadas no servidor: HTTP puro basta, sem navegador. Cada ficha
fica em /works/<slug>/ e traz um unico bloco de contato com as linhas
separadas por <br>. Nao ha paginacao: a listagem inteira vem numa resposta.
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

LISTAGEM = "https://apeim.com.pe/directorio-de-asociadas/"
PAIS = "Peru"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

_ESPACOS = re.compile(r"\s+")
# O `@` aparece com espaco em pelo menos uma ficha (mauricio.cheng@ kantar.com);
# aceitamos o espaco aqui e removemos na normalizacao.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@\s?[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NAO_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$", re.I)
# Placeholders de formulario que nao sao contato de ninguem.
_EMAIL_PLACEHOLDER = re.compile(
    r"^(usuario|user|ejemplo|example|correo|email|e-mail|nombre|tu|su|abc|test|"
    r"sample|info)@(dominio|domain|ejemplo|example|correo|email|tudominio|"
    r"sudominio|mail)\.", re.I)

# Dominios da propria APEIM e de redes sociais: aparecem no rodape de toda
# ficha e nao sao o site nem o e-mail da associada.
_DOMINIO_ASSOCIACAO = ("apeim.com.pe", "talkin.com.pe", "tudashboard.com")
_DOMINIO_SOCIAL = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com",
                   "x.com", "youtube.com", "wa.me", "api.whatsapp.com")

_SITE_TEXTO = re.compile(r"^(https?://|www\.)\S+", re.I)
# O acento erra de vogal em pelo menos uma ficha ("Télefono"), entao as duas
# posicoes aceitam acento. Sem isso o telefone vaza para o endereco.
_ROTULO_TEL = re.compile(
    r"^(t[eé]l[eé]fonos?|tel[eé]fs?|telf|central telef[oó]nica|whatsapp|fax|"
    r"m[oó]vil|celular|cel)\b", re.I)
# Linha que e so numero de telefone, sem rotulo (ex.: "+54 9 11 2598-1002").
_SO_TELEFONE = re.compile(r"^[+(]?\d[\d\s()+./\-]{6,}$")
# Telefone grudado no fim da linha de endereco (caso da NIQ Peru).
_TEL_NO_ENDERECO = re.compile(
    r"[,;.\s]*(?:t[eé]l[eé]fonos?|telf|tel)\.?\s*:?\s*([\d][\d\s()+./\-]{5,})$", re.I)
_ENDERECO = re.compile(
    r"\b(av\.|avda\.|avenida|calle|jr\.|jir[oó]n|urb\.|edificio|piso|of\.|"
    r"oficina|centro empresarial|paseo|torre|mz\.|nro\.?|km\b|carretera)",
    re.I)

# Blocos do tema que usam a mesma classe do bloco de contato.
_BLOCO_RUIDO = ("gremio sin fines de lucro", "políticas de privacidad",
                "inicio", "nombre de usuario")


def _limpar(t: str | None) -> str:
    return _ESPACOS.sub(" ", t or "").strip()


def _normalizar_email(v: str) -> str:
    v = _ESPACOS.sub("", (v or "").strip().lower()).strip(".,;:")
    if not v or _NAO_EMAIL.search(v) or _EMAIL_PLACEHOLDER.match(v):
        return ""
    if any(d in v.split("@")[-1] for d in _DOMINIO_ASSOCIACAO):
        return ""
    return v


def _baixar(url: str, timeout: int = 40) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe: {url}")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(4_000_000).decode("utf-8", errors="replace")


@dataclass
class Asociada:
    url_perfil: str
    nome: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    descricao: str = ""
    categoria: str = ""       # "Socios plenos" ou "Socios adherentes"
    contato: str = ""         # pessoa citada na ficha
    cargo: str = ""
    emails_extras: list[str] = field(default_factory=list)
    coletado_em: str = ""
    erro: str = ""


def listar_asociadas() -> list[tuple[str, str, str]]:
    """(nome, categoria, url) de cada asociada, na ordem da listagem."""
    sopa = BeautifulSoup(_baixar(LISTAGEM), "html.parser")
    itens = []
    for it in sopa.select("div.stm_works div.item"):
        link = it.select_one("a.link[href]")
        titulo = it.select_one(".title")
        categoria = it.select_one(".category")
        if not link or not titulo:
            continue
        itens.append((_limpar(titulo.get_text()),
                      _limpar(categoria.get_text()) if categoria else "",
                      link["href"].split("?")[0]))
    return itens


def _total_declarado(html: str) -> int:
    """Numero de empresas que a propria APEIM anuncia, para conferencia."""
    m = re.search(r"conformada por\s+(\d+)\s+empresas", html, re.I)
    return int(m.group(1)) if m else 0


def total_declarado() -> int:
    return _total_declarado(_baixar(LISTAGEM))


def _bloco_contato(sopa: BeautifulSoup):
    """
    O bloco util e o unico text-editor com dado de contato.

    Escolher pelo conteudo, e nao pela posicao, evita quebrar quando o tema
    reordena os widgets do Elementor.
    """
    for b in sopa.select("div.elementor-widget-text-editor div.elementor-widget-container"):
        texto = b.get_text(" ", strip=True)
        if len(texto) < 15:
            continue
        if any(r in texto.lower() for r in _BLOCO_RUIDO):
            continue
        return b
    return None


def _linhas(bloco) -> list[str]:
    """
    Linhas do bloco. <br> nao gera texto, entao viram quebra explicita.

    O texto de cada <a> e achatado antes: uma ficha quebra a linha no meio da
    URL, e sem isso o resto ("answers/") viraria uma linha solta que o
    classificador nao reconhece e joga no endereco.
    """
    copia = BeautifulSoup(str(bloco), "html.parser")
    for br in copia.find_all("br"):
        br.replace_with("\n")
    for a in copia.find_all("a"):
        a.string = _limpar(a.get_text())
    return [_limpar(l) for l in copia.get_text("\n").split("\n") if _limpar(l)]


def _emails_do_bloco(bloco) -> list[str]:
    """
    E-mails da ficha, em ordem de confianca.

    O texto do link vence o href: em pelo menos uma ficha (Lumini) o href
    ficou defasado e aponta para uma pessoa que ja saiu, enquanto o texto
    exibido traz o contato atual. Fichas sem <a> guardam o e-mail em texto
    puro, entao varremos as linhas depois.
    """
    achados: list[str] = []
    for a in bloco.select('a[href^="mailto:"]'):
        texto = _normalizar_email(_limpar(a.get_text()))
        href = _normalizar_email(a["href"][7:].split("?")[0])
        for v in (texto, href):
            if v and v not in achados:
                achados.append(v)
                break
    for linha in _linhas(bloco):
        for bruto in _EMAIL.findall(linha):
            v = _normalizar_email(bruto)
            if v and v not in achados:
                achados.append(v)
    return achados


def _site_do_bloco(bloco, linhas: list[str]) -> str:
    for a in bloco.select("a[href^=http]"):
        h = a["href"].split("?")[0]
        d = h.split("//", 1)[-1].split("/")[0]
        if not any(x in d for x in _DOMINIO_ASSOCIACAO + _DOMINIO_SOCIAL):
            return h
    for linha in linhas:
        m = _SITE_TEXTO.match(linha)
        if m:
            h = m.group(0).rstrip(".,;")
            d = h.split("//", 1)[-1].split("/")[0]
            if not any(x in d for x in _DOMINIO_ASSOCIACAO + _DOMINIO_SOCIAL):
                return h
    return ""


def extrair_asociada(html: str, url: str, nome: str, categoria: str) -> Asociada:
    reg = Asociada(url_perfil=url, nome=nome, categoria=categoria,
                   coletado_em=datetime.now(timezone.utc).isoformat())
    sopa = BeautifulSoup(html, "html.parser")
    bloco = _bloco_contato(sopa)
    if bloco is None:
        reg.erro = "bloco de contato ausente"
        return reg

    linhas = _linhas(bloco)
    emails = _emails_do_bloco(bloco)
    if emails:
        reg.email, reg.emails_extras = emails[0], emails[1:4]
    reg.site = _site_do_bloco(bloco, linhas)

    telefones: list[str] = []
    enderecos: list[str] = []
    cabecalho: list[str] = []       # linhas antes do primeiro dado de contato
    ja_classificou = False

    for linha in linhas:
        if _EMAIL.search(linha) or _SITE_TEXTO.match(linha):
            ja_classificou = True
            continue
        if _ROTULO_TEL.match(linha) or _SO_TELEFONE.match(linha):
            telefones.append(linha)
            ja_classificou = True
            continue
        if _ENDERECO.search(linha):
            # a NIQ Peru cola o telefone no fim do endereco; separamos os dois
            m = _TEL_NO_ENDERECO.search(linha)
            if m:
                telefones.append(_limpar(m.group(1)))
                linha = _limpar(linha[:m.start()])
            enderecos.append(linha)
            ja_classificou = True
            continue
        if ja_classificou:
            # continuacao do endereco (bairro, cidade, pais) so aparece depois
            # do primeiro campo estruturado; fragmentos curtos sao ruido de link
            if len(linha) >= 4:
                enderecos.append(linha)
            continue
        cabecalho.append(linha)

    # A ficha as vezes repete o nome da empresa antes da pessoa de contato.
    alvo = re.sub(r"[^a-z0-9]", "", nome.lower())
    while cabecalho and re.sub(r"[^a-z0-9]", "", cabecalho[0].lower()) == alvo:
        cabecalho.pop(0)
    if cabecalho:
        reg.contato = cabecalho[0]
    if len(cabecalho) > 1:
        reg.cargo = cabecalho[1]

    reg.telefone = " / ".join(dict.fromkeys(telefones))
    reg.endereco = ", ".join(dict.fromkeys(enderecos))
    reg.descricao = _limpar(" ".join(cabecalho[2:]))[:400]

    if not (reg.email or reg.site or reg.telefone):
        reg.erro = "ficha sem canal de contato"
    return reg


def coletar(itens: list[tuple[str, str, str]], *, delay: float = 1.6,
            verbose: bool = True) -> list[Asociada]:
    saida: list[Asociada] = []
    for i, (nome, categoria, url) in enumerate(itens, 1):
        try:
            reg = extrair_asociada(_baixar(url), url, nome, categoria)
        except Exception as exc:
            # Timeout nao e ausencia de dado: marcamos o erro e seguimos, para
            # a conferencia final apontar o que precisa de nova tentativa.
            reg = Asociada(url_perfil=url, nome=nome, categoria=categoria,
                           erro=f"{type(exc).__name__}: {exc}"[:150],
                           coletado_em=datetime.now(timezone.utc).isoformat())
        saida.append(reg)
        if verbose:
            print(f"  [{i:>2}/{len(itens)}] {'!' if reg.erro else '.'} "
                  f"{reg.nome[:22]:22} | {reg.email[:34]:34} | {reg.site[:30]}")
        if i < len(itens):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "email", "site", "pais", "telefone", "endereco", "descricao",
           "categoria", "contato", "cargo", "emails_extras", "url_perfil", "erro"]


def exportar(regs: list[Asociada], nome: str = "apeim_peru") -> tuple[Path, Path]:
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
