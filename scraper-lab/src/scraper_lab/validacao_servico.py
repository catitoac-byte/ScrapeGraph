"""
Verificacao de caixa por servico externo.

Por que existe: confirmar que um endereco existe exige falar SMTP com o
servidor de destino a partir de um IP com boa reputacao. Desta maquina isso
nao funciona; o IP de saida esta em lista da Spamhaus e 32 de 40 recusas
medidas eram bloqueio ao nosso IP, nao caixa inexistente.

Os provedores aqui mantem IPs limpos e acordos com grandes provedores. O
modulo normaliza as respostas dos tres para o mesmo vocabulario, entao
trocar de fornecedor nao muda o resto do codigo.

Configuracao no .env:
    VALIDADOR=zerobounce | neverbounce | bouncer
    VALIDADOR_API_KEY=...
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

# Vocabulario unico, independente do fornecedor.
#   valido        a caixa existe
#   invalido      a caixa nao existe
#   arriscado     existe mas e descartavel, catch-all ou de funcao
#   indeterminado o servico nao concluiu
VEREDITOS = ("valido", "invalido", "arriscado", "indeterminado")


@dataclass
class Veredito:
    email: str
    status: str = "indeterminado"
    detalhe: str = ""
    provedor: str = ""
    catch_all: bool = False
    descartavel: bool = False
    papel: bool = False


class SemChave(RuntimeError):
    """Nenhum provedor configurado."""


def _get(url: str, timeout: int = 30) -> dict:
    with urlopen(Request(url, headers={"User-Agent": "scraper-lab/1.0"}),
                 timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(url: str, corpo: dict, cabecalhos: dict, timeout: int = 30) -> dict:
    req = Request(url, data=json.dumps(corpo).encode(),
                  headers={"Content-Type": "application/json", **cabecalhos})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# --------------------------------------------------------------------------
# Adaptadores
# --------------------------------------------------------------------------

def _zerobounce(email: str, chave: str) -> Veredito:
    d = _get("https://api.zerobounce.net/v2/validate?" +
             urlencode({"api_key": chave, "email": email, "ip_address": ""}))
    bruto = (d.get("status") or "").lower()
    mapa = {"valid": "valido", "invalid": "invalido",
            "catch-all": "arriscado", "spamtrap": "invalido",
            "abuse": "arriscado", "do_not_mail": "arriscado",
            "unknown": "indeterminado"}
    return Veredito(
        email=email, status=mapa.get(bruto, "indeterminado"),
        detalhe=(d.get("sub_status") or bruto)[:60], provedor="zerobounce",
        catch_all=bruto == "catch-all",
        descartavel=(d.get("sub_status") or "") == "disposable",
        papel=(d.get("sub_status") or "") == "role_based",
    )


def _neverbounce(email: str, chave: str) -> Veredito:
    d = _get("https://api.neverbounce.com/v4/single/check?" +
             urlencode({"key": chave, "email": email}))
    bruto = (d.get("result") or "").lower()
    mapa = {"valid": "valido", "invalid": "invalido",
            "catchall": "arriscado", "disposable": "arriscado",
            "unknown": "indeterminado"}
    marcas = d.get("flags") or []
    return Veredito(
        email=email, status=mapa.get(bruto, "indeterminado"),
        detalhe=(", ".join(marcas) or bruto)[:60], provedor="neverbounce",
        catch_all=bruto == "catchall", descartavel="disposable_email" in marcas,
        papel="role_account" in marcas,
    )


def _bouncer(email: str, chave: str) -> Veredito:
    d = _post("https://api.usebouncer.com/v1.1/email/verify",
              {"email": email}, {"x-api-key": chave})
    bruto = (d.get("status") or "").lower()
    razao = (d.get("reason") or "")
    mapa = {"deliverable": "valido", "undeliverable": "invalido",
            "risky": "arriscado", "unknown": "indeterminado"}
    return Veredito(
        email=email, status=mapa.get(bruto, "indeterminado"),
        detalhe=(razao or bruto)[:60], provedor="bouncer",
        catch_all=razao == "accepted_email",
        descartavel=(d.get("domain") or {}).get("disposable") == "yes",
        papel=(d.get("account") or {}).get("role") == "yes",
    )


_ADAPTADORES = {"zerobounce": _zerobounce, "neverbounce": _neverbounce,
                "bouncer": _bouncer}


def provedor_configurado() -> tuple[str, str]:
    nome = (os.getenv("VALIDADOR") or "").strip().lower()
    chave = (os.getenv("VALIDADOR_API_KEY") or "").strip()
    if not nome or not chave:
        raise SemChave(
            "Nenhum provedor configurado. No .env defina:\n"
            "    VALIDADOR=zerobounce   (ou neverbounce, bouncer)\n"
            "    VALIDADOR_API_KEY=...\n"
            "Sem isso, use apenas as camadas de DNS em scraper_lab.validar_email."
        )
    if nome not in _ADAPTADORES:
        raise SemChave(f"VALIDADOR={nome} desconhecido. "
                       f"Use um de: {', '.join(sorted(_ADAPTADORES))}.")
    return nome, chave


def verificar(email: str, *, tentativas: int = 3) -> Veredito:
    nome, chave = provedor_configurado()
    adaptador = _ADAPTADORES[nome]
    for n in range(tentativas):
        try:
            return adaptador(email, chave)
        except Exception as exc:
            if n == tentativas - 1:
                return Veredito(email=email, status="indeterminado",
                                detalhe=f"{type(exc).__name__}"[:40], provedor=nome)
            time.sleep(1.5 * (n + 1))
    return Veredito(email=email, provedor=nome)


def verificar_lote(emails: list[str], *, trabalhadores: int = 8,
                   verbose: bool = True) -> list[Veredito]:
    nome, _ = provedor_configurado()
    if verbose:
        print(f"verificando {len(emails)} enderecos via {nome}")
    with ThreadPoolExecutor(max_workers=trabalhadores) as ex:
        return list(ex.map(verificar, emails))
