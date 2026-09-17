"""
Usuarios do Rival Pulse e as verticais que cada um abre.

    uv run python vitrine-web/usuarios.py listar
    uv run python vitrine-web/usuarios.py novo cliente-x moda supermercados
    uv run python vitrine-web/usuarios.py novo cassiano todas
    uv run python vitrine-web/usuarios.py acesso cliente-x moda
    uv run python vitrine-web/usuarios.py senha cliente-x            # gera outra
    uv run python vitrine-web/usuarios.py senha cliente-x --digitar  # voce escolhe
    uv run python vitrine-web/usuarios.py remover cliente-x
    uv run python vitrine-web/usuarios.py publicar                   # manda para a Vercel e redeploya

A senha aparece uma vez na tela (ou vai para --arquivo) e nunca fica guardada:
o cadastro local so tem o hash scrypt, em dados/saida/ (fora do git).
Nada muda no site ate rodar "publicar".
"""

import argparse
import getpass
import hashlib
import json
import os
import secrets
import string
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MODELO = Path(__file__).resolve().parent
LAB = MODELO.parent
PRODUTO = json.loads((MODELO / "produto.json").read_text(encoding="utf-8"))
CADASTRO = LAB / "dados" / "saida" / "rivalpulse_usuarios.json"
SITE = LAB / "sites" / PRODUTO["projeto"]
VERTICAIS = sorted(p.stem for p in (LAB / "verticais").glob("*.json"))


def carregar() -> dict:
    if CADASTRO.exists():
        return json.loads(CADASTRO.read_text(encoding="utf-8"))
    return {"usuarios": {}, "segredo_publicado": False}


def salvar(dados: dict) -> None:
    CADASTRO.parent.mkdir(parents=True, exist_ok=True)
    CADASTRO.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(CADASTRO, 0o600)


def gerar_senha() -> str:
    abc = string.ascii_letters + string.digits
    return "-".join("".join(secrets.choice(abc) for _ in range(n)) for n in (4, 5, 5))


def hash_senha(senha: str) -> str:
    # Mesmos parametros do scryptSync do Node (N=16384, r=8, p=1, 32 bytes)
    salt = secrets.token_hex(16)
    h = hashlib.scrypt(senha.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32)
    return f"{salt}:{h.hex()}"


def verticais(nomes: list[str]) -> list[str]:
    if nomes == ["todas"]:
        return ["*"]
    faltam = [n for n in nomes if n not in VERTICAIS]
    if faltam:
        raise SystemExit(f"vertical desconhecida: {', '.join(faltam)} (existem: {', '.join(VERTICAIS)})")
    return nomes


def entregar(usuario: str, senha: str, arquivo: str | None) -> None:
    linha = f"{usuario}\t{senha}\n"
    if arquivo:
        p = Path(arquivo).expanduser()
        with p.open("a", encoding="utf-8") as f:
            f.write(linha)
        os.chmod(p, 0o600)
        print(f"senha de {usuario} gravada em {p}")
    else:
        print(f"usuario: {usuario}\nsenha:   {senha}\n(guarde agora, ela nao fica registrada)")


def trocar_senha(dados: dict, usuario: str, digitar: bool, arquivo: str | None) -> None:
    if digitar:
        senha = getpass.getpass("nova senha: ").strip()
        if len(senha) < 10 or senha != getpass.getpass("repita: ").strip():
            raise SystemExit("senha curta (minimo 10) ou diferente na repeticao")
    else:
        senha = gerar_senha()
    dados["usuarios"][usuario]["h"] = hash_senha(senha)
    dados["usuarios"][usuario]["senha_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not digitar:
        entregar(usuario, senha, arquivo)


def vercel_env(nome: str, valor: str) -> None:
    kw = {"cwd": SITE, "capture_output": True, "text": True}
    subprocess.run(["vercel", "env", "rm", nome, "production", "--yes", "--scope", "cassiai"], **kw)
    r = subprocess.run(["vercel", "env", "add", nome, "production", "--sensitive", "--scope", "cassiai"], input=valor, **kw)
    if r.returncode:
        raise SystemExit(f"falhou ao gravar {nome}: {r.stderr.strip()[-300:]}")


def publicar(dados: dict) -> None:
    if not (SITE / ".vercel").exists():
        raise SystemExit(f"{SITE} ainda nao esta ligado a um projeto Vercel")
    env = {u: {"h": c["h"], "v": c["v"]} for u, c in dados["usuarios"].items()}
    vercel_env("RIVAL_USUARIOS", json.dumps(env, separators=(",", ":")))
    if not dados.get("segredo_publicado"):
        vercel_env("RIVAL_SEGREDO", secrets.token_hex(32))
        dados["segredo_publicado"] = True
        salvar(dados)
    subprocess.run(["vercel", "deploy", "--prod", "--yes", "--scope", "cassiai"], cwd=SITE, check=True,
                   stdout=subprocess.DEVNULL)
    print(f"publicado: {len(env)} usuarios em https://{PRODUTO['dominio']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    p = sub.add_parser("novo"); p.add_argument("usuario"); p.add_argument("verticais", nargs="+")
    p.add_argument("--digitar", action="store_true"); p.add_argument("--arquivo")
    p = sub.add_parser("acesso"); p.add_argument("usuario"); p.add_argument("verticais", nargs="+")
    p = sub.add_parser("senha"); p.add_argument("usuario")
    p.add_argument("--digitar", action="store_true"); p.add_argument("--arquivo")
    p = sub.add_parser("remover"); p.add_argument("usuario")
    sub.add_parser("publicar")
    a = ap.parse_args()

    dados = carregar()
    us = dados["usuarios"]
    nome = getattr(a, "usuario", "").strip().lower()
    if a.cmd in ("acesso", "senha", "remover") and nome not in us:
        raise SystemExit(f"usuario nao existe: {nome}")

    if a.cmd == "listar":
        for u, c in sorted(us.items()):
            print(f"{u:<20} {', '.join(c['v']).replace('*', 'todas')}")
        print("(nada publicado ainda)" if not dados.get("segredo_publicado") else "")
        return
    if a.cmd == "novo":
        if nome in us:
            raise SystemExit(f"usuario ja existe: {nome}")
        if not nome or not all(ch.isalnum() or ch in "-_." for ch in nome):
            raise SystemExit("usuario so com letras, numeros, - _ .")
        us[nome] = {"v": verticais(a.verticais), "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        trocar_senha(dados, nome, a.digitar, a.arquivo)
    elif a.cmd == "acesso":
        us[nome]["v"] = verticais(a.verticais)
    elif a.cmd == "senha":
        trocar_senha(dados, nome, a.digitar, a.arquivo)
    elif a.cmd == "remover":
        del us[nome]
    elif a.cmd == "publicar":
        publicar(dados)
        return
    salvar(dados)
    print("cadastro atualizado. Rode \"publicar\" para valer no site.")


if __name__ == "__main__":
    main()
