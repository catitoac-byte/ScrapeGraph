"""
Validacao de e-mail em camadas, da mais barata a mais invasiva.

  1. sintaxe        regex conforme a pratica; custo zero, risco zero
  2. MX             o dominio tem servidor de e-mail? Consulta DNS pura,
                    nao encosta em servidor de correio
  3. classificacao  descartavel, gratuito, papel (contato@, info@)
  4. SMTP           pergunta ao servidor se a caixa existe, SEM enviar nada

Sobre a camada 4 e a reputacao: ela nao envia mensagem e nao usa nenhum
dominio do usuario. Usamos remetente nulo (MAIL FROM: <>), que e o padrao
de verificacao, e um HELO neutro. O que fica exposto e o IP desta maquina,
nunca o dominio de quem contrata. Ainda assim, provedores grandes costumam
aceitar qualquer destinatario (catch-all), entao o resultado dela e
indicativo, e as camadas 1 a 3 sao as conclusivas.
"""

from __future__ import annotations

import re
import smtplib
import socket
import threading
import time
from dataclasses import dataclass, field

import dns.resolver

# Pratico, nao a RFC inteira: cobre o que aparece em cadastro real.
_SINTAXE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}@"
    r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")

GRATUITOS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br",
             "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "live.com",
             "msn.com", "icloud.com", "globo.com", "aol.com", "protonmail.com",
             "hotmail.com.br", "outlook.com.br", "me.com", "gmail.com.br"}

DESCARTAVEIS = {"mailinator.com", "10minutemail.com", "guerrillamail.com",
                "tempmail.com", "yopmail.com", "trashmail.com", "sharklasers.com",
                "throwawaymail.com", "temp-mail.org", "getnada.com"}

# Caixas de funcao: chegam a um time, nao a uma pessoa. Uteis, porem com
# taxa de resposta menor que a de um contato nominal.
PAPEL = {"contato", "contact", "info", "sac", "atendimento", "comercial",
         "vendas", "financeiro", "adm", "administrativo", "suporte", "support",
         "faleconosco", "hello", "rh", "juridico", "compras", "marketing",
         "no-reply", "noreply", "postmaster", "abuse", "webmaster"}


@dataclass
class Resultado:
    email: str
    valido_sintaxe: bool = False
    tem_mx: bool = False
    mx_situacao: str = ""
    mx: str = ""
    gratuito: bool = False
    descartavel: bool = False
    papel: bool = False
    smtp: str = ""          # aceito | recusado | indeterminado | nao testado
    veredito: str = ""      # invalido | arriscado | provavel | valido
    motivo: str = ""


_cache_mx: dict[str, tuple[str, list[str]]] = {}
_trava_mx = threading.Lock()


def _consulta(dominio: str, tipo: str, timeout: float):
    r = dns.resolver.Resolver()
    r.lifetime = r.timeout = timeout
    return r.resolve(dominio, tipo)


def mx_do_dominio(dominio: str, timeout: float = 6.0, tentativas: int = 3
                  ) -> tuple[str, list[str]]:
    """
    Devolve (situacao, hosts) com situacao em: ok, sem_mx, indeterminado.

    A distincao importa. Tratar timeout como ausencia de MX marcou 643
    enderecos do gmail como invalidos numa primeira versao. Falha de
    consulta nao e prova de nada, e so NXDOMAIN/NoAnswer sao conclusivos.
    """
    with _trava_mx:
        if dominio in _cache_mx:
            return _cache_mx[dominio]

    situacao, hosts = "indeterminado", []
    for tentativa in range(tentativas):
        try:
            resp = _consulta(dominio, "MX", timeout)
            hosts = sorted(str(x.exchange).rstrip(".") for x in resp)
            situacao = "ok" if hosts else "sem_mx"
            break
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            # Sem MX o correio pode ir para o registro A (RFC 5321).
            try:
                _consulta(dominio, "A", timeout)
                situacao, hosts = "ok", [dominio]
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                situacao, hosts = "sem_mx", []
            except Exception:
                situacao = "indeterminado"
            break
        except Exception:
            situacao = "indeterminado"
            time.sleep(0.4 * (tentativa + 1))

    if situacao != "indeterminado":
        with _trava_mx:
            _cache_mx[dominio] = (situacao, hosts)
    return situacao, hosts


def validar(email: str, *, smtp: bool = False) -> Resultado:
    e = (email or "").strip().lower()
    res = Resultado(email=e)
    if not _SINTAXE.match(e) or e.count("@") != 1:
        res.veredito, res.motivo = "invalido", "sintaxe"
        return res
    res.valido_sintaxe = True

    local, dominio = e.split("@")
    res.gratuito = dominio in GRATUITOS
    res.descartavel = dominio in DESCARTAVEIS
    res.papel = local.split("+")[0] in PAPEL

    if res.descartavel:
        res.veredito, res.motivo = "invalido", "dominio descartavel"
        return res

    situacao, hosts = mx_do_dominio(dominio)
    res.mx_situacao = situacao
    res.tem_mx = situacao == "ok"
    res.mx = hosts[0] if hosts else ""
    if situacao == "sem_mx":
        res.veredito, res.motivo = "invalido", "dominio nao recebe e-mail"
        return res
    if situacao == "indeterminado":
        res.veredito, res.motivo = "indeterminado", "consulta DNS falhou"
        return res

    if smtp:
        res.smtp = _sondar_smtp(res.mx, e)
        if res.smtp == "recusado":
            res.veredito, res.motivo = "invalido", "servidor recusou a caixa"
            return res

    if res.smtp == "aceito":
        res.veredito = "valido"
        res.motivo = "MX ok e caixa aceita"
    else:
        res.veredito = "provavel"
        res.motivo = "MX ok"
    if res.papel:
        res.motivo += "; caixa de funcao"
    return res


# Um 550 quase nunca significa "a caixa nao existe". Estas expressoes marcam
# recusa por reputacao do IP de origem ou politica do servidor, e devem ser
# lidas como indeterminado. Sem isto, 32 de 40 recusas foram classificadas
# como caixa inexistente quando eram bloqueio ao nosso proprio IP.
_RECUSA_DE_POLITICA = (
    "blocked", "block list", "blacklist", "spamhaus", "barracuda", "spamcop",
    "policy", "service unavailable", "not authenticated", "relay", "denied",
    "reputation", "helo", "rate limit", "too many", "greylist", "try again",
    "temporarily", "unauthorized", "banned", "abuse", "rbl", "dnsbl",
)

# HELO precisa ser FQDN pela RFC 2821: "localhost" faz varios servidores
# devolverem 550 sem sequer avaliar o destinatario.
HELO_PADRAO = "mail.invalid"
REMETENTE_PADRAO = "<>"


def _sondar_smtp(host: str, email: str, timeout: float = 8.0,
                 helo: str = HELO_PADRAO) -> str:
    """
    Pergunta ao servidor se a caixa existe. Nunca envia mensagem.

    Devolve aceito, recusado ou indeterminado. "recusado" so quando o
    servidor recusa o destinatario por si, nao quando recusa a nossa
    conexao. Resultado confiavel exige IP com boa reputacao; de IP
    residencial ou movel a maioria das respostas sai indeterminada.
    """
    try:
        s = smtplib.SMTP(timeout=timeout)
        s.connect(host, 25)
        try:
            s.ehlo(helo)
        except smtplib.SMTPException:
            s.helo(helo)
        s.docmd("MAIL FROM:", REMETENTE_PADRAO)
        codigo, msg = s.docmd("RCPT TO:", f"<{email}>")
        s.quit()
        texto = msg.decode("utf-8", "replace").lower() if isinstance(msg, bytes) else str(msg).lower()
        if codigo in (250, 251):
            return "aceito"
        if codigo in (550, 551, 553, 554):
            if any(m in texto for m in _RECUSA_DE_POLITICA):
                return "indeterminado"
            return "recusado"
        return "indeterminado"
    except (smtplib.SMTPException, socket.error, OSError):
        return "indeterminado"
