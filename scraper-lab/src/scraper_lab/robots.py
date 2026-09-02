"""
Verificador de robots.txt com suporte a curinga.

Por que nao usar urllib.robotparser: ele faz apenas casamento por prefixo
literal. Uma regra como

    Disallow: /company/*/email

nunca casa com /company/Foo/email, e o can_fetch devolve True para uma URL
explicitamente proibida. Alem disso, o read() dele busca o arquivo sem
User-Agent; sites que respondem 403 a isso deixam o parser em modo
"bloqueia tudo", o que silenciosamente zera qualquer coleta.

Aqui implementamos o comportamento que os buscadores usam de fato:
curinga `*`, ancora `$` e vitoria da regra mais especifica (a mais longa).
"""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

UA_PADRAO = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")


def _para_regex(padrao: str) -> re.Pattern:
    """Converte um caminho de robots.txt em expressao regular."""
    fim = padrao.endswith("$")
    if fim:
        padrao = padrao[:-1]
    partes = [re.escape(p) for p in padrao.split("*")]
    return re.compile("^" + ".*".join(partes) + ("$" if fim else ""))


class Robots:
    """Regras de um dominio para um dado agente."""

    def __init__(self, texto: str, agente: str = "*") -> None:
        self.permitir: list[tuple[int, re.Pattern]] = []
        self.proibir: list[tuple[int, re.Pattern]] = []
        self._bloqueados: set[str] = set()
        self._parsear(texto, agente)

    def _parsear(self, texto: str, agente: str) -> None:
        # O BOM (U+FEFF) sobrevive ao strip(): para o Python ele nao conta
        # como espaco. Deixando-o passar, a primeira chave de um arquivo
        # salvo em UTF-8 com BOM vira "\ufeffuser-agent", o teste de grupo
        # falha, o grupo inteiro e descartado e as regras dele somem em
        # silencio. Foi o que aconteceu com researchsociety.com.au, que
        # proibe tudo no primeiro grupo e passava a liberar tudo. Nenhum
        # token de robots.txt tem uso legitimo para esse caractere, entao
        # ele sai do texto todo. A limpeza mora aqui, e nao so no _buscar,
        # porque outros modulos constroem Robots(texto, agente) direto.
        texto = texto.replace("\ufeff", "")
        alvo = agente.lower()
        atuais: list[str] = []
        aplicavel = False
        for linha in texto.splitlines():
            linha = linha.split("#", 1)[0].strip()
            if not linha or ":" not in linha:
                continue
            chave, _, valor = linha.partition(":")
            chave, valor = chave.strip().lower(), valor.strip()

            if chave == "user-agent":
                # linhas de user-agent consecutivas formam um so grupo
                if not aplicavel or atuais == []:
                    atuais.append(valor.lower())
                else:
                    atuais = [valor.lower()]
                aplicavel = any(a == "*" or a in alvo for a in atuais)
                continue

            if chave in ("disallow", "allow"):
                if valor == "/" and chave == "disallow" and atuais:
                    self._bloqueados.update(a for a in atuais if a != "*")
                if not aplicavel or not valor:
                    if chave == "disallow" and not valor:
                        pass  # "Disallow:" vazio significa liberar tudo
                    continue
                destino = self.proibir if chave == "disallow" else self.permitir
                destino.append((len(valor), _para_regex(valor)))
                atuais = atuais  # mantem grupo
            else:
                atuais = atuais

    @property
    def agentes_bloqueados(self) -> list[str]:
        """Agentes com Disallow: / declarado, sem repeticao."""
        return sorted(self._bloqueados)

    def permite(self, url: str) -> bool:
        caminho = urlparse(url).path or "/"
        if urlparse(url).query:
            caminho += "?" + urlparse(url).query
        melhor_proibe = max((n for n, rx in self.proibir if rx.match(caminho)), default=-1)
        melhor_permite = max((n for n, rx in self.permitir if rx.match(caminho)), default=-1)
        # Allow mais especifico vence Disallow, como fazem os buscadores.
        return melhor_permite >= melhor_proibe if melhor_proibe >= 0 else True


# O certificado de varios sites e aceito pelo repositorio do sistema e nao
# pelo pacote embutido do Python. Sem isto o handshake falha, a leitura do
# robots.txt e abortada e a verificacao passa a liberar tudo em silencio.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

# (situacao, regras). situacao em: lido, ausente, falhou.
#   lido    o arquivo foi obtido e interpretado
#   ausente o servidor respondeu 404: nao existe robots.txt, e a convencao
#           da web e permitir
#   falhou  nao conseguimos ler (TLS, timeout, 5xx). NAO e prova de que o
#           acesso e livre, apenas ausencia de informacao
_cache: dict[str, tuple[str, "Robots | None"]] = {}

# Quem chama pode querer saber que a verificacao nao pode ser feita.
_avisados: set[str] = set()


def _buscar(base: str, agente: str, timeout: int) -> tuple[str, "Robots | None"]:
    ultimo = None
    for tentativa in range(3):
        for esquema in ("", "http://"):   # alguns hosts so servem em http
            alvo = (base if not esquema else esquema + base.split("://", 1)[1])
            try:
                req = Request(alvo + "/robots.txt", headers={"User-Agent": agente})
                with urlopen(req, timeout=timeout) as r:
                    # utf-8-sig descarta o BOM inicial; ver _parsear.
                    texto = r.read(500_000).decode("utf-8-sig", errors="replace")
                return "lido", Robots(texto, agente)
            except HTTPError as e:
                if e.code in (404, 410):
                    return "ausente", None
                ultimo = e
            except Exception as e:
                ultimo = e
        time.sleep(0.6 * (tentativa + 1))
    return "falhou", None


def situacao(url: str, *, agente: str = UA_PADRAO, timeout: int = 15) -> str:
    """lido, ausente ou falhou. Util para registrar no relatorio de coleta."""
    return _situacao_e_regras(url, agente=agente, timeout=timeout)[0]


def _situacao_e_regras(url: str, *, agente: str = UA_PADRAO,
                       timeout: int = 15) -> tuple[str, "Robots | None"]:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _cache:
        _cache[base] = _buscar(base, agente, timeout)
    return _cache[base]


def para(url: str, *, agente: str = UA_PADRAO, timeout: int = 15) -> "Robots | None":
    return _situacao_e_regras(url, agente=agente, timeout=timeout)[1]


def permitido(url: str, *, agente: str = UA_PADRAO, silencioso: bool = False) -> bool:
    """
    True quando a URL pode ser acessada.

    Falha de leitura devolve True, seguindo a convencao da web, porem avisa
    uma vez por dominio. Antes o erro era engolido, e um dominio com TLS
    quebrado passava a liberar ate caminhos que ele proibia explicitamente.
    """
    sit, regras = _situacao_e_regras(url, agente=agente)
    if sit == "falhou":
        base = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if base not in _avisados and not silencioso:
            _avisados.add(base)
            print(f"  [robots] {base}: nao foi possivel ler o robots.txt; "
                  f"seguindo com a convencao de permitir")
        return True
    return True if regras is None else regras.permite(url)
