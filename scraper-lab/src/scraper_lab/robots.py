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
from urllib.parse import urlparse
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


_cache: dict[str, Robots | None] = {}


def para(url: str, *, agente: str = UA_PADRAO, timeout: int = 15) -> Robots | None:
    """Robots do dominio da URL. Devolve None quando nao foi possivel ler."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base in _cache:
        return _cache[base]
    try:
        req = Request(base + "/robots.txt", headers={"User-Agent": agente})
        with urlopen(req, timeout=timeout) as r:
            texto = r.read(500_000).decode("utf-8", errors="replace")
        _cache[base] = Robots(texto, agente)
    except Exception:
        # Sem robots.txt legivel, o padrao da web e permitir.
        _cache[base] = None
    return _cache[base]


def permitido(url: str, *, agente: str = UA_PADRAO) -> bool:
    r = para(url, agente=agente)
    return True if r is None else r.permite(url)
