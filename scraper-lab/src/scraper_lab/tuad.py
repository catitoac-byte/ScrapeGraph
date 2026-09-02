"""
Extrator das associadas da TUAD, a associacao turca de pesquisa de mercado
(Turkiye Arastirmacilar Dernegi, www.tuad.org.tr).

A TUAD separa as pessoas juridicas em duas listas que nao se cruzam:

  /uyeler/tuzel-uye-arastirma-firmalari      empresas de pesquisa
  /uyeler/tuzel-uye-veri-toplama-firmalari   empresas de coleta de dados

Conferimos a interseccao dos identificadores das duas paginas antes de
escrever este modulo: e vazia. Sao 40 mais 12, 52 empresas distintas.

Ha ainda /gab-ve-iso-20252-belgeli-uyeler, com 38 empresas. Essa NAO e uma
terceira categoria de associada: os 38 identificadores estao todos contidos
na uniao das duas listas acima. E um selo de certificacao, e entra como o
campo booleano `iso_20252`, casado por identificador. Tratar essa pagina
como listagem adicional inflaria a base com 38 duplicatas.

/uyeler/bireysel-uyelerimiz e /uyelik-bilgileri/onur-uyelerimiz sao pessoas
fisicas, nao empresas, e nao usam o mesmo mecanismo de ficha (zero chamadas
a modalAc). Ficam de fora deste extrator, que coleta empresas.

Ficha por AJAX: a listagem so traz nome e logo; o resto abre num modal via
POST em /phpfonk/mysqlajax.php com dosya=uyecek, tablo=uyeler, id=<id>.
Nao precisa de navegador, mas precisa de SESSAO: sem o cookie PHPSESSID
obtido ao carregar a listagem, o endpoint responde 200 com corpo VAZIO, e
nao um erro. Um coletor ingenuo registraria 52 empresas sem nenhum dado e
concluiria que a TUAD nao publica contato. Por isso abrimos a listagem
primeiro e reaproveitamos o cookie.

TLS: o certificado da TUAD nao valida contra o bundle embutido do Python,
so contra o trust store do sistema. Mesmo caso da KORA. Sem truststore toda
requisicao morre em CERTIFICATE_VERIFY_FAILED e o site parece fora do ar.

Codificacao: a TUAD responde utf-8 no cabecalho e na meta, e os caracteres
turcos (i sem ponto, g breve, s cedilha, I com ponto) chegam integros. Ainda
assim `_decodificar` percorre a ordem cabecalho, meta, utf-8, cp1254,
iso-8859-9 e roda um teste de mojibake: cp1254 e iso-8859-9 aceitam
qualquer byte sem erro, entao um dia em que o servidor declarasse
iso-8859-9 servindo utf-8 devolveria "AraÅtÄ±rma" em vez de "Arastirma"
sem excecao nenhuma.
"""

from __future__ import annotations

import csv
import http.cookiejar
import json
import re
import ssl
import time
import unicodedata
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

import truststore
from bs4 import BeautifulSoup

from scraper_lab import robots as robots_mod
from scraper_lab.robots import permitido as robots_permitido

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "dados" / "saida"

BASE = "https://www.tuad.org.tr"
AJAX = f"{BASE}/phpfonk/mysqlajax.php"

# Rotulo -> caminho. O rotulo entra em `tipo_associacao` porque separa a
# empresa que desenha e analisa a pesquisa da que so executa o campo.
LISTAS = {
    "Tuzel Uye Arastirma Firmalari": "/uyeler/tuzel-uye-arastirma-firmalari",
    "Tuzel Uye Veri Toplama Firmalari": "/uyeler/tuzel-uye-veri-toplama-firmalari",
}
LISTA_ISO = "/gab-ve-iso-20252-belgeli-uyeler"

PAIS = "Turkey"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

# Sem Crawl-delay declarado (ver `_preparar_robots`), entao vale a pausa
# padrao do projeto.
PAUSA_PADRAO = 1.5

_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

# Contatos da propria TUAD, presentes no cabecalho de toda pagina.
_EMAIL_INSTITUCIONAL = {"tuad@tuad.org.tr", "info@tuad.org.tr"}
_TELEFONE_INSTITUCIONAL = {"902122753523", "02122753523", "2122753523"}

_ESPACOS = re.compile(r"[\s ​]+")
_VAZIOS = {"", "-", "--", ".", "n/a", "na", "yok", "belirtilmemis"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Perfil de rede social nao e site institucional.
_REDES_SOCIAIS = ("instagram.com", "facebook.com", "twitter.com", "x.com",
                  "linkedin.com", "youtube.com", "tiktok.com", "wa.me",
                  "whatsapp.com")
# Telefone turco: opcional +90, DDD e 7 digitos, com separadores livres.
_TELEFONE = re.compile(r"(?:\+?90[\s.\-]*)?\(?0?\d{3}\)?[\s.\-]*\d{3}[\s.\-]*\d{2}[\s.\-]*\d{2}")
_SO_DIGITOS = re.compile(r"\D")


def _limpar(texto: str | None) -> str:
    t = _ESPACOS.sub(" ", (texto or "")).strip()
    # NFC para que "s cedilha" composto e decomposto nao virem duas empresas
    # diferentes na hora de deduplicar contra Esomar e Greenbook.
    t = unicodedata.normalize("NFC", t)
    return "" if t.lower() in _VAZIOS else t


# ---------------------------------------------------------------- codificacao

_META_CHARSET = re.compile(rb"""charset["'\s=]*([A-Za-z0-9_\-]+)""", re.I)
_CANDIDATOS = ("utf-8", "cp1254", "iso-8859-9")
_APELIDOS = {"utf8": "utf-8", "windows-1254": "cp1254", "iso8859-9": "iso-8859-9",
             "latin5": "iso-8859-9", "iso_8859-9": "iso-8859-9"}
_UM_BYTE = {"cp1254", "iso-8859-9", "latin-1", "iso-8859-1"}

# Assinatura de utf-8 lido como tabela de um byte: byte inicial de uma
# sequencia multibyte seguido de byte de continuacao. "Arastirma" virando
# "AraAtA+-rma" e o caso que queremos pegar.
_MOJIBAKE = re.compile(r"[Â-ÃÅÎÏ][-¿œž’€]")

_codificacoes_vistas: dict[str, int] = {}


def _decodificar(bruto: bytes, charset_http: str | None) -> tuple[str, str]:
    """
    Texto e nome da codificacao efetivamente usada.

    Ordem: cabecalho HTTP, meta charset, depois os candidatos do idioma. Um
    detalhe importante: cp1254 e iso-8859-9 mapeiam os 256 bytes possiveis e
    NUNCA levantam excecao. Se um deles vier declarado por engano, o decode
    "da certo" e devolve nome corrompido em silencio. Por isso, quando o
    vencedor e uma tabela de um byte, testamos o resultado contra a
    assinatura de mojibake e so entao aceitamos.
    """
    ordem: list[str] = []

    def somar(nome: str | None) -> None:
        if not nome:
            return
        n = _APELIDOS.get(nome.strip().lower(), nome.strip().lower())
        if n not in ordem:
            ordem.append(n)

    somar(charset_http)
    m = _META_CHARSET.search(bruto[:4096])
    if m:
        somar(m.group(1).decode("ascii", "ignore"))
    for c in _CANDIDATOS:
        somar(c)

    for nome in ordem:
        try:
            texto = bruto.decode(nome)
        except (UnicodeDecodeError, LookupError):
            continue
        if nome in _UM_BYTE and _MOJIBAKE.search(texto):
            try:
                return bruto.decode("utf-8"), f"utf-8 (corrigido de {nome})"
            except UnicodeDecodeError:
                pass
        return texto, nome
    return bruto.decode("utf-8", errors="replace"), "utf-8/replace"


def codificacoes_detectadas() -> dict[str, int]:
    return dict(_codificacoes_vistas)


def _registrar(codec: str) -> None:
    _codificacoes_vistas[codec] = _codificacoes_vistas.get(codec, 0) + 1


# Letras que so existem em turco. Servem de prova viva de que a codificacao
# resistiu: uma pagina de empresas turcas sem nenhuma delas e suspeita.
_LETRAS_TURCAS = set("ıİğĞşŞçÇöÖüÜ")


def tem_letras_turcas(texto: str) -> bool:
    return any(c in _LETRAS_TURCAS for c in texto)


# ------------------------------------------------------------------- robots

def _preparar_robots() -> dict[str, str]:
    """
    Situacao do robots.txt da TUAD, com uma ressalva que muda o resultado.

    www.tuad.org.tr NAO tem robots.txt. O servidor responde 200 com a pagina
    HTML padrao do site (1,3 MB) em vez de 404. Entregar esse HTML ao parser
    seria pedir problema: qualquer linha do documento que por acaso comecasse
    com "Allow:" ou "Disallow:" viraria regra inventada. Detectamos o HTML,
    registramos o dominio como "ausente" (sem regras) e seguimos, que e a
    convencao da web para robots inexistente.

    Nao ha Crawl-delay porque nao ha arquivo; usamos PAUSA_PADRAO.
    """
    relato: dict[str, str] = {}
    try:
        req = Request(f"{BASE}/robots.txt", headers={"User-Agent": UA})
        with _ABRIDOR.open(req, timeout=20) as r:
            bruto = r.read(2_000_000)
            ctype = (r.headers.get("Content-Type") or "").lower()
        cabeca = bruto[:400].lstrip().lower()
        if "html" in ctype or cabeca.startswith((b"<!doctype", b"<html")):
            robots_mod._cache[BASE] = ("ausente", None)
            relato[BASE] = ("sem robots.txt: o servidor devolve 200 com o HTML "
                            "do site; tratado como ausente, sem regras")
        else:
            texto = bruto.decode("utf-8-sig", errors="replace")
            regras = robots_mod.Robots(texto, UA)
            robots_mod._cache[BASE] = ("lido", regras)
            relato[BASE] = (f"lido: {len(regras.proibir)} Disallow, "
                            f"{len(regras.permitir)} Allow")
    except Exception as exc:
        # Falha de leitura nao e prova de permissao, mas tambem nao e
        # proibicao. Registramos para o relatorio final.
        robots_mod._cache[BASE] = ("falhou", None)
        relato[BASE] = f"falha de leitura ({type(exc).__name__}); padrao permitir"
    return relato


# ------------------------------------------------------------------- download

# Um unico opener com cookie jar: o modal exige o PHPSESSID da listagem.
_COOKIES = http.cookiejar.CookieJar()
_ABRIDOR = build_opener(HTTPCookieProcessor(_COOKIES), HTTPSHandler(context=_CTX))
# Sem cabecalho padrao: o User-Agent vai explicito em cada requisicao, o
# mesmo que passamos ao verificador de robots.
_ABRIDOR.addheaders = []


def sessao_ativa() -> bool:
    return any(c.name == "PHPSESSID" for c in _COOKIES)


def _tentar(func, *, tentativas: int = 3, base_espera: float = 2.0):
    """
    Repete com espera crescente.

    Timeout e 403 esporadico nao sao ausencia de dado: sem retentativa a
    empresa entraria na base com o campo vazio e ninguem saberia que houve
    falha de rede.
    """
    ultimo: Exception | None = None
    for i in range(tentativas):
        try:
            return func()
        except Exception as exc:
            ultimo = exc
            if i < tentativas - 1:
                time.sleep(base_espera * (i + 1))
    raise ultimo  # type: ignore[misc]


def _baixar(url: str, timeout: int = 40) -> str:
    if not robots_permitido(url, agente=UA):
        raise PermissionError(f"robots.txt proibe {url}")

    def uma_vez() -> str:
        req = Request(url, headers={"User-Agent": UA,
                                    "Accept-Language": "tr,en;q=0.7"})
        with _ABRIDOR.open(req, timeout=timeout) as r:
            bruto = r.read(8_000_000)
            charset = r.headers.get_content_charset()
        texto, usada = _decodificar(bruto, charset)
        _registrar(usada)
        return texto

    return _tentar(uma_vez)


def _abrir_ficha(id_membro: int, referer: str, timeout: int = 40) -> str:
    """HTML do modal. Corpo vazio aqui significa sessao perdida, nao ausencia."""
    if not robots_permitido(AJAX, agente=UA):
        raise PermissionError(f"robots.txt proibe {AJAX}")
    dados = urllib.parse.urlencode({"dosya": "uyecek", "tablo": "uyeler",
                                    "id": id_membro}).encode()

    def uma_vez() -> str:
        req = Request(AJAX, data=dados, headers={
            "User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": referer, "Accept-Language": "tr,en;q=0.7"})
        with _ABRIDOR.open(req, timeout=timeout) as r:
            bruto = r.read(2_000_000)
            charset = r.headers.get_content_charset()
        if not bruto.strip():
            raise RuntimeError("ficha vazia (sessao PHPSESSID perdida?)")
        texto, usada = _decodificar(bruto, charset)
        _registrar(usada)
        return texto

    return _tentar(uma_vez)


# -------------------------------------------------------------------- registro

@dataclass
class Empresa:
    id_membro: int
    nome: str = ""
    nome_latino: str = ""
    email: str = ""
    site: str = ""
    pais: str = PAIS
    telefone: str = ""
    endereco: str = ""
    cidade: str = ""
    descricao: str = ""
    tipo_associacao: str = ""
    iso_20252: str = ""
    logo: str = ""
    url_perfil: str = ""
    coletado_em: str = ""
    erro: str = ""


# ------------------------------------------------------------------- listagem

_MODAL = re.compile(r"modalAc\('uyecek',\s*'[^']*',\s*'uyeler',\s*(\d+)\)")


def listar_membros(*, verbose: bool = True) -> list[dict]:
    """
    Um dicionario por empresa: id, nome, logo e categoria.

    Nao ha paginacao nem rolagem infinita: cada categoria mora numa unica
    pagina e todos os cartoes vem no HTML. Contamos identificadores UNICOS,
    nao cartoes, porque o mesmo card aparece duas vezes em telas em que o
    tema repete a grade para o layout mobile.
    """
    membros: list[dict] = []
    vistos: set[int] = set()
    for rotulo, caminho in LISTAS.items():
        url = BASE + caminho
        sopa = BeautifulSoup(_baixar(url), "html.parser")
        cartoes = sopa.select("a.uyebar")
        achados = 0
        for a in cartoes:
            m = _MODAL.search(a.get("onclick") or "")
            if not m:
                continue
            ident = int(m.group(1))
            if ident in vistos:
                continue
            vistos.add(ident)
            titulo = a.select_one("div.baslik")
            img = a.select_one("div.resim img")
            membros.append({
                "id": ident,
                "nome": _limpar(titulo.get_text() if titulo else ""),
                "logo": (img.get("src") or "") if img else "",
                "tipo_associacao": rotulo,
                "url_listagem": url,
            })
            achados += 1
        if verbose:
            print(f"      {rotulo}: {achados} empresas "
                  f"({len(cartoes)} cartoes no HTML)")
        time.sleep(PAUSA_PADRAO)
    return membros


def ids_com_iso(*, verbose: bool = True) -> set[int]:
    """
    Identificadores da pagina de certificados ISO 20252 / GAB.

    Casamos por identificador, que e a chave estavel do CMS. Casar por nome
    seria pedir erro: a mesma empresa aparece como "AKADEMETRE ARASTIRMA VE
    DANISMANLIK LTD.STI" numa lista e com pontuacao diferente na outra.
    """
    url = BASE + LISTA_ISO
    sopa = BeautifulSoup(_baixar(url), "html.parser")
    ids = {int(m.group(1))
           for a in sopa.select("a.uyebar")
           for m in [_MODAL.search(a.get("onclick") or "")] if m}
    if verbose:
        print(f"      {len(ids)} empresas com ISO 20252 / GAB")
    return ids


# -------------------------------------------------------------------- extracao

# O nome turco ja e alfabeto latino. O que a base global costuma guardar e a
# forma sem diacritico, entao produzimos essa forma para permitir o cruzamento.
# NFKD nao resolve sozinho: "i sem ponto" e "I com ponto" nao se decompoem.
_DOBRA_TURCA = str.maketrans({"ı": "i", "İ": "I", "ğ": "g", "Ğ": "G",
                              "ş": "s", "Ş": "S", "ç": "c", "Ç": "C",
                              "ö": "o", "Ö": "O", "ü": "u", "Ü": "U"})


def dobrar_para_ascii(nome: str) -> str:
    t = (nome or "").translate(_DOBRA_TURCA)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def _texto_com_quebras(no) -> str:
    """Texto de um bloco preservando <br> como quebra de linha."""
    for br in no.find_all("br"):
        br.replace_with("\n")
    return no.get_text()


# Rotulos que a TUAD digita dentro do proprio bloco de endereco.
_ROTULO = re.compile(r"^(adres|adresi|tel|telefon|gsm|faks|fax|e-?posta|e-?mail|"
                     r"mail|web|site|internet)\s*[:.]\s*", re.I)


def _partir_bloco_endereco(bruto: str) -> tuple[str, str, str]:
    """
    Separa (endereco, email, telefone) do bloco livre `div.adres`.

    A TUAD guarda contato de dois jeitos, e as duas formas convivem:

      href="mailto:..." / href="tel:..."   ficha preenchida nos campos certos
      tudo dentro do texto de div.adres    ficha digitada num campo so

    Se lermos apenas os href, perdemos o e-mail de quem digitou tudo junto.
    Se lermos apenas o texto, o endereco fica com o e-mail grudado no fim.

    Duas regras que so aparecem depois de olhar os dados reais:

    1. Empresa com mais de um escritorio publica mais de um e-mail no mesmo
       bloco. Guardamos o primeiro como e-mail do registro, mas removemos
       TODOS do texto: manter o segundo dentro de `endereco` polui a coluna
       e faz o endereco casar com buscas por e-mail mais tarde.
    2. O bloco vem com rotulo digitado a mao ("Adres:", "Telefon:"). Sem
       tirar o rotulo, o endereco comeca com lixo e a linha que sobra do
       telefone vira um "Telefon:" solto no meio do endereco.
    """
    linhas = [_limpar(x) for x in (bruto or "").split("\n")]
    linhas = [x for x in linhas if x]

    email = ""
    telefone = ""
    restantes: list[str] = []
    for linha in linhas:
        linha = _ROTULO.sub("", linha).strip()

        achados = _EMAIL.findall(linha)
        if achados and not email:
            email = achados[0].lower()
        for e in achados:
            linha = linha.replace(e, " ")
        linha = _limpar(linha)

        # So aceitamos como telefone a linha que e praticamente so numero;
        # "No:4" e "A3 Blok, D:1-8" tem digitos e sao endereco.
        achado_tel = _TELEFONE.search(linha)
        if achado_tel:
            digitos = _SO_DIGITOS.sub("", linha)
            if len(digitos) >= 10 and len(linha) <= 30:
                if not telefone:
                    telefone = _limpar(achado_tel.group(0))
                linha = _limpar(linha.replace(achado_tel.group(0), " "))

        sobrou = _limpar(linha).strip(" ,;:|-")
        if sobrou and not _ROTULO.match(sobrou + ":"):
            restantes.append(sobrou)
    return ", ".join(restantes), email, telefone


# Ultima linha do endereco costuma ser "Bairro - Cidade" ou "Cidade".
_CIDADES = ("İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana",
            "Kocaeli", "Konya", "Gaziantep", "Kayseri", "Eskişehir", "Mersin",
            "Samsun", "Denizli", "Trabzon", "Sakarya", "Muğla", "Aydın")


def _cidade_do_endereco(endereco: str) -> str:
    dobrado = dobrar_para_ascii(endereco).lower()
    for cidade in _CIDADES:
        if dobrar_para_ascii(cidade).lower() in dobrado:
            return cidade
    return ""


def extrair_empresa(html: str, membro: dict, com_iso: bool) -> Empresa:
    reg = Empresa(
        id_membro=membro["id"],
        nome=membro["nome"],
        nome_latino=dobrar_para_ascii(membro["nome"]),
        logo=membro["logo"],
        tipo_associacao=membro["tipo_associacao"],
        iso_20252="sim" if com_iso else "nao",
        url_perfil=f"{membro['url_listagem']}?id={membro['id']}",
        coletado_em=datetime.now(timezone.utc).isoformat(),
    )
    sopa = BeautifulSoup(html, "html.parser")

    titulo = sopa.select_one("div.modal-body div.baslik")
    if titulo:
        nome_ficha = _limpar(titulo.get_text())
        # A ficha manda mais que a listagem quando as duas divergem: a
        # listagem trunca nomes longos em alguns temas.
        if nome_ficha and len(nome_ficha) >= len(reg.nome):
            reg.nome = nome_ficha
            reg.nome_latino = dobrar_para_ascii(nome_ficha)

    bloco = sopa.select_one("div.adres")
    endereco, email_texto, tel_texto = _partir_bloco_endereco(
        _texto_com_quebras(bloco) if bloco else "")

    # href tem prioridade sobre texto livre: e o campo estruturado da ficha.
    email_href = ""
    a_mail = sopa.select_one('a[href^="mailto:"]')
    if a_mail:
        achado = _EMAIL.search(urllib.parse.unquote(a_mail.get("href", "")))
        if achado:
            email_href = achado.group(0).lower()
    tel_href = ""
    a_tel = sopa.select_one('a[href^="tel:"]')
    if a_tel:
        tel_href = _limpar(a_tel.get("href", "")[4:])

    email = email_href or email_texto
    if email and email not in _EMAIL_INSTITUCIONAL:
        reg.email = email
    telefone = tel_href or tel_texto
    if telefone and _SO_DIGITOS.sub("", telefone) not in _TELEFONE_INSTITUCIONAL:
        reg.telefone = telefone

    reg.endereco = endereco[:300]
    reg.cidade = _cidade_do_endereco(endereco)

    corpo = sopa.select_one("div.bilgi")
    if corpo:
        reg.descricao = _limpar(corpo.get_text(" "))[:800]

    # A ficha as vezes traz o site da empresa como link externo. Redes
    # sociais ficam de fora: uma pagina de Instagram na coluna `site` faz a
    # base parecer ter site quando nao tem, e quebra o enriquecimento por
    # dominio la na frente.
    for a in sopa.select("div.modal-body a[href^=http]"):
        href = a.get("href", "")
        alvo = href.lower()
        if "tuad.org.tr" in alvo or any(r in alvo for r in _REDES_SOCIAIS):
            continue
        reg.site = href.split("?")[0][:200]
        break

    if not (reg.email or reg.telefone or reg.endereco or reg.descricao):
        # Registro legitimo, empresa associada de verdade; a TUAD e que nao
        # publicou contato. Marcamos para nao confundir com falha de rede.
        reg.erro = "ficha publicada sem dados de contato"
    return reg


def coletar(membros: list[dict], com_iso: set[int], *,
            delay: float = PAUSA_PADRAO, verbose: bool = True) -> list[Empresa]:
    saida: list[Empresa] = []
    for i, m in enumerate(membros, 1):
        try:
            reg = extrair_empresa(_abrir_ficha(m["id"], m["url_listagem"]),
                                  m, m["id"] in com_iso)
        except Exception as exc:
            reg = Empresa(id_membro=m["id"], nome=m["nome"],
                          nome_latino=dobrar_para_ascii(m["nome"]),
                          logo=m["logo"], tipo_associacao=m["tipo_associacao"],
                          iso_20252="sim" if m["id"] in com_iso else "nao",
                          url_perfil=f"{m['url_listagem']}?id={m['id']}",
                          coletado_em=datetime.now(timezone.utc).isoformat(),
                          erro=f"{type(exc).__name__}: {exc}"[:150])
        saida.append(reg)
        if verbose:
            marca = "." if not reg.erro else "!"
            print(f"  [{i:>3}/{len(membros)}] {marca} {reg.nome[:34]:34} | "
                  f"{reg.email[:30]:30} | {reg.telefone[:18]}")
        if i < len(membros):
            time.sleep(delay)
    return saida


COLUNAS = ["nome", "nome_latino", "email", "site", "pais", "telefone",
           "endereco", "cidade", "descricao", "tipo_associacao", "iso_20252",
           "logo", "id_membro", "url_perfil", "coletado_em", "erro"]


def exportar(empresas: list[Empresa], nome: str = "tuad") -> tuple[Path, Path]:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cj, cc = SAIDA / f"{nome}.json", SAIDA / f"{nome}.csv"
    cj.write_text(json.dumps([asdict(e) for e in empresas],
                             ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig: sem BOM o Excel turco le o CSV como cp1254 e quebra i, g e s.
    with cc.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS)
        w.writeheader()
        for e in empresas:
            d = asdict(e)
            w.writerow({k: d.get(k, "") for k in COLUNAS})
    return cj, cc
