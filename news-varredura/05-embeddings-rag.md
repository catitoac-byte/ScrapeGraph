# Embeddings, recuperação e RAG

Coletado em 2026-09-02.

---

## MTEB, o estado do leaderboard

Aviso metodológico que precede qualquer citação. **MTEB v2, de 2026, não é comparável com
MTEB v1.** Os rankings também variam entre os boards English v2 e multilingual MMTEB. Citar
"primeiro lugar no MTEB" sem dizer qual board e qual versão é erro. **[B]**

O leaderboard oficial é um Space do Hugging Face que carrega por JavaScript e não pode ser
lido por fetch simples. A consulta precisa ser feita no navegador. Os números abaixo vieram de
busca e estão marcados como pista, não como fato publicável. **[C]**

| Modelo | Nota | Observação |
|---|---|---|
| tencent/KaLM-Embedding-Gemma3-12B | topo entre abertos | 11,76 bi de parâmetros, 3840 dimensões |
| Qwen3-Embedding 8B | cerca de 75% de média MTEB | aberto |
| NVIDIA NV-Embed-v2 | 72,31 no MTEB English | 4096 dimensões, contexto de 32K |
| Gemini Embedding | SOTA no MTEB multilingual em mar/2025 | hospedado |
| BAAI BGE-M3 | o mais baixado do Hugging Face | denso, esparso e multivetor num só modelo, 100+ idiomas |

O BGE-M3 merece destaque de arquitetura, não de ranking. Ele entrega recuperação densa,
esparsa e multivetor no mesmo modelo, o que reduz a complexidade da stack.

## A arquitetura padrão de 2026

O default deixou de ser embedding denso puro. O padrão atual é: **recuperação híbrida com BM25
mais denso, fusão por RRF, e reranker cross-encoder no fim.** **[B]**

| Camada | Função | Ganho reportado |
|---|---|---|
| BM25 | Casamento léxico exato, nomes, códigos, siglas | Cobre o ponto cego do denso |
| Denso | Similaridade semântica | Cobre paráfrase e sinônimo |
| RRF | Fusão dos dois rankings | Não exige calibrar escalas |
| Cross-encoder | Reordenação com interação bidirecional | 5 a 15 pontos de MRR em conjuntos difíceis |

## Context rot, o achado que muda projeto

Modelos com janela de 1 milhão de tokens ou mais ainda mostram degradação de 20% a 50% quando
o fato crítico está no meio da sequência. Conforme o contexto cresce, informação irrelevante
dilui o sinal mesmo com recuperação perfeita. **[B]**

A consequência prática desmonta um mito comercial inteiro. Janela gigante não elimina RAG. Ela
muda o problema de "achar o documento" para "posicionar o trecho certo na posição de alta
atenção". É exatamente isso que o reranking faz. Ele move os melhores trechos para onde o
modelo presta atenção.

Frase pronta para uso. Contexto de um milhão de tokens não é memória, é espaço. Quem enche o
espaço sem curadoria perde de 20% a 50% de desempenho no que estava no meio.

## RAG agêntico

A virada é de pipeline de recuperar e gerar em um passo para agente de recuperação em vários
passos. **[B]**

No RAG agêntico a recuperação vira uma ferramenta que o modelo pode chamar várias vezes dentro
do mesmo turno. O agente inspeciona a pergunta, decide se precisa de mais evidência, emite uma
nova busca com a consulta reescrita, e só gera a resposta final quando tem contexto suficiente.

O que isso muda no projeto:
- O custo por resposta deixa de ser fixo e passa a ser variável.
- A latência sobe e precisa de orçamento explícito.
- A avaliação precisa medir o caminho, não só a resposta.
- Reescrita de consulta vira componente de primeira classe.

## Checklist de recuperação para proposta técnica

1. Híbrido BM25 mais denso, com RRF. Denso puro ficou para trás.
2. Reranker cross-encoder obrigatório em conjunto difícil.
3. Medir posição do trecho relevante, não só se ele foi recuperado.
4. Definir orçamento de latência e de chamadas antes de adotar RAG agêntico.
5. Escolher o embedding pelo board certo. Multilingual para base em português, não English v2.
6. Reavaliar o embedding a cada seis meses. O campo se move rápido e a migração custa
   reindexação completa.

## Fontes

- [MTEB Leaderboard, Hugging Face](https://huggingface.co/spaces/mteb/leaderboard)
- [Redis, modelos de reranking para RAG em 2026](https://redis.io/blog/top-reranking-models-rag-accuracy/)
- [arXiv, recuperação para busca agêntica via interação direta com o corpus](https://arxiv.org/pdf/2605.05242)
