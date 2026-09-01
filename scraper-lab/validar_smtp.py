"""
Sondagem SMTP da base, agrupada por dominio.

Uma conexao por dominio, varios RCPT na mesma sessao: menos handshakes,
menos ruido para o servidor e resultado bem mais rapido que abrir conexao
por endereco.

Nao envia mensagem. Remetente nulo e HELO neutro, entao nenhum dominio do
usuario aparece em lugar nenhum; o que se expoe e o IP desta maquina.

    uv run python -u validar_smtp.py
"""

import collections
import csv
import json
import smtplib
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scraper_lab.validar_email import (
    GRATUITOS, HELO_PADRAO, REMETENTE_PADRAO, _RECUSA_DE_POLITICA,
    mx_do_dominio,
)

SAIDA = Path("dados/saida")
LIMITE_POR_SESSAO = 20      # RCPT por conexao, para nao parecer varredura


def sondar_dominio(dominio: str, enderecos: list[str]) -> dict[str, str]:
    situacao, hosts = mx_do_dominio(dominio)
    if situacao != "ok" or not hosts:
        return {e: "sem_mx" for e in enderecos}

    saida: dict[str, str] = {}
    restantes = list(enderecos)
    while restantes:
        lote, restantes = restantes[:LIMITE_POR_SESSAO], restantes[LIMITE_POR_SESSAO:]
        try:
            s = smtplib.SMTP(timeout=10)
            s.connect(hosts[0], 25)
            # HELO precisa ser FQDN (RFC 2821). "localhost" fazia servidores
            # devolverem 550 antes mesmo de olhar o destinatario.
            try:
                s.ehlo(HELO_PADRAO)
            except smtplib.SMTPException:
                s.helo(HELO_PADRAO)
            s.docmd("MAIL FROM:", REMETENTE_PADRAO)
            for e in lote:
                try:
                    codigo, msg = s.docmd("RCPT TO:", f"<{e}>")
                except Exception:
                    saida[e] = "indeterminado"
                    continue
                texto = (msg.decode("utf-8", "replace") if isinstance(msg, bytes)
                         else str(msg)).lower()
                if codigo in (250, 251):
                    saida[e] = "aceito"
                elif codigo in (550, 551, 553, 554):
                    # 550 raramente e "caixa nao existe": quase sempre e
                    # bloqueio ao nosso IP ou politica do servidor.
                    saida[e] = ("indeterminado"
                                if any(m in texto for m in _RECUSA_DE_POLITICA)
                                else "recusado")
                else:
                    saida[e] = "indeterminado"
                time.sleep(0.3)
            s.quit()
        except (smtplib.SMTPException, socket.error, OSError):
            for e in lote:
                saida.setdefault(e, "indeterminado")
        time.sleep(0.5)
    return saida


if __name__ == "__main__":
    inicio = time.time()
    import sys
    arquivo = sys.argv[1] if len(sys.argv) > 1 else "validacao_brasil.csv"
    sufixo = "internacional" if "internacional" in arquivo else "brasil"
    regs = list(csv.DictReader(open(SAIDA / arquivo, encoding="utf-8-sig")))
    alvo = [r["email"] for r in regs if r["veredito"] in ("provavel", "indeterminado")]
    por_dominio: dict[str, list[str]] = collections.defaultdict(list)
    for e in alvo:
        por_dominio[e.split("@")[-1]].append(e)
    print(f"{len(alvo)} enderecos em {len(por_dominio)} dominios")
    print(f"uma conexao por dominio, ate {LIMITE_POR_SESSAO} RCPT por sessao\n")

    resultado: dict[str, str] = {}
    feitos = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {ex.submit(sondar_dominio, d, es): d for d, es in por_dominio.items()}
        for f in futuros:
            try:
                resultado.update(f.result())
            except Exception:
                pass
            feitos += 1
            if feitos % 100 == 0:
                c = collections.Counter(resultado.values())
                print(f"   {feitos}/{len(por_dominio)} dominios | {dict(c)} | "
                      f"{(time.time()-inicio)/60:.0f} min")

    destino = SAIDA / f"validacao_smtp_{sufixo}.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["email", "smtp", "gratuito"])
        for e, v in sorted(resultado.items()):
            w.writerow([e, v, e.split("@")[-1] in GRATUITOS])

    c = collections.Counter(resultado.values())
    corp = collections.Counter(v for e, v in resultado.items()
                               if e.split("@")[-1] not in GRATUITOS)
    print(f"\n{'='*54}")
    for k in ["aceito", "recusado", "indeterminado", "sem_mx"]:
        if c.get(k):
            print(f"  {k:16} {c[k]:>6}  ({100*c[k]//len(resultado)}%)")
    print(f"  {'-'*40}")
    print(f"  so dominios corporativos: {dict(corp)}")
    print(f"  tempo: {(time.time()-inicio)/60:.0f} min")
    print(f"  CSV: {destino}")
    print(f"{'='*54}")
