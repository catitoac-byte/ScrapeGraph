"""
Fabrica de configuracao de LLM para os grafos do ScrapeGraph.

Objetivo: trocar de provedor mexendo apenas no .env, sem tocar no codigo
dos scrapers. Hoje roda em modo manual (sem LLM). Amanha e uma linha:

    LLM_PROVIDER=deepseek
    DEEPSEEK_API_KEY=sk-...
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

# Janela de contexto por modelo. A lib tem a propria tabela, porem quando o
# modelo e desconhecido ela cai para 8192 SEM ERRO e trunca paginas longas
# (ver abstract_graph.py, atributo model_tokens_defaulted). Passamos o valor
# explicito para que isso nunca aconteca silenciosamente.
JANELAS: dict[str, int] = {
    "deepseek-chat": 128_000,
    "deepseek-v3": 128_000,
    "deepseek-v3.1": 128_000,
    "deepseek-r1": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
}

# Fallback por familia de provedor, usado quando o modelo nao esta no mapa
# acima (um "deepseek-v4" futuro, por exemplo).
JANELA_PADRAO_PROVEDOR: dict[str, int] = {
    "deepseek": 128_000,
    "openai": 128_000,
    "anthropic": 200_000,
    "ollama": 8_192,
}

ENV_DA_CHAVE: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

MODELO_PADRAO: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "ollama": "llama3.1",
}


class LLMNaoConfigurado(RuntimeError):
    """Nenhum provedor utilizavel. Mensagem explica exatamente o que falta."""


@dataclass(frozen=True)
class Provedor:
    nome: str
    modelo: str
    janela: int
    tem_chave: bool

    @property
    def pronto(self) -> bool:
        return self.nome == "ollama" or self.tem_chave


def _janela(provedor: str, modelo: str) -> int:
    if modelo in JANELAS:
        return JANELAS[modelo]
    return JANELA_PADRAO_PROVEDOR.get(provedor, 8_192)


def provedor_ativo() -> Provedor:
    """Le o .env e descreve o provedor configurado, sem levantar excecao."""
    nome = os.getenv("LLM_PROVIDER", "manual").strip().lower()
    modelo = os.getenv("LLM_MODEL", "").strip() or MODELO_PADRAO.get(nome, "")
    env_chave = ENV_DA_CHAVE.get(nome)
    tem_chave = bool(env_chave and os.getenv(env_chave, "").strip())
    return Provedor(nome, modelo, _janela(nome, modelo), tem_chave)


def build_graph_config(
    *,
    headless: bool = True,
    verbose: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    """
    Monta o graph_config do ScrapeGraph a partir do .env.

    Levanta LLMNaoConfigurado com instrucao acionavel quando falta provedor
    ou chave, em vez de deixar a lib falhar la dentro com erro obscuro.
    """
    p = provedor_ativo()

    if p.nome == "manual":
        raise LLMNaoConfigurado(
            "LLM_PROVIDER=manual: nenhum modelo conectado.\n"
            "Os grafos do ScrapeGraph precisam de um LLM para rodar.\n"
            "Para ativar, defina no .env:\n"
            "    LLM_PROVIDER=deepseek\n"
            "    DEEPSEEK_API_KEY=sk-...\n"
            "A camada de coleta (scraper_lab.coleta) funciona sem isso."
        )

    if p.nome not in MODELO_PADRAO:
        raise LLMNaoConfigurado(
            f"LLM_PROVIDER={p.nome} nao reconhecido. "
            f"Use um de: {', '.join(sorted(MODELO_PADRAO))}."
        )

    if not p.pronto:
        raise LLMNaoConfigurado(
            f"Provedor {p.nome} selecionado, porem {ENV_DA_CHAVE[p.nome]} "
            f"esta vazia no .env ({RAIZ / '.env'})."
        )

    llm: dict[str, Any] = {
        "model": f"{p.nome}/{p.modelo}",
        # Explicito de proposito: evita o fallback silencioso de 8192.
        "model_tokens": p.janela,
    }
    if p.nome != "ollama":
        llm["api_key"] = os.getenv(ENV_DA_CHAVE[p.nome], "")

    config: dict[str, Any] = {
        "llm": llm,
        "headless": headless,
        "verbose": verbose,
    }
    config.update(overrides)
    return config
