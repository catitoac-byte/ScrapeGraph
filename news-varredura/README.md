# News Varredura Internet

Vertical de inteligência sobre IA para embasar criativos, textos comerciais e a narrativa
de expertise da empresa em automação, IA e pesquisa de mercado.

A regra desta pasta é simples. Nenhum número entra num criativo sem fonte, URL e data.

## Varredura de referência

Primeira varredura completa em **2026-09-02**.

## Como está organizado

| Arquivo | O que cobre |
|---|---|
| `00-sumario-executivo.md` | Os 20 fatos mais citáveis, prontos para copy |
| `01-rankings-llms.md` | Rankings, benchmarks, quem lidera o quê |
| `02-abertos-vs-pagos.md` | Modelos de peso aberto contra proprietários, custo |
| `03-harness-e-agentes.md` | Harness, orquestração, MCP, agentes em produção |
| `04-skills-context-engineering.md` | Agent Skills, context engineering, progressive disclosure |
| `05-embeddings-rag.md` | Embeddings, MTEB, RAG agêntico, reranking, context rot |
| `06-metodologias-de-ponta.md` | RLVR, evals, LLM as judge, pós-treino |
| `07-mercado-adocao-roi.md` | Adoção corporativa, investimento, a taxa real de fracasso |
| `08-ia-pesquisa-de-mercado.md` | O setor de insights, GRIT, respondentes sintéticos |
| `09-fontes-para-acompanhar.md` | Livros, blogs, cursos, newsletters, papers, leaderboards |
| `10-achados-da-varredura.md` | O que a varredura automática trouxe de novo, com correções |
| `11-fundamentos-biblioteca.md` | Curadoria da bibliografia de fundamentos, com caminho legítimo |
| `dados/fatos-citaveis.csv` | Base estruturada de claims com fonte, data e nível de confiança |
| `dados/fontes.csv` | Catálogo de fontes com feed RSS quando existe |
| `dados/biblioteca-anthropic.csv` | Arquivo completo de 44 posts de engenharia e pesquisa da Anthropic |
| `raspar_news_ia.py` | Varredura recorrente por RSS, Atom e arXiv |

## Níveis de confiança

Toda afirmação carrega um nível. Isso define o que pode ir para um criativo público.

| Nível | Significado | Pode publicar |
|---|---|---|
| **A** | Fonte primária aberta e lida diretamente nesta varredura | Sim, com citação |
| **B** | Fonte primária citada por terceiro confiável, não aberta direto | Sim, checando o primário antes |
| **C** | Fonte secundária ou agregador de SEO | Não. Serve de pista, precisa de confirmação |

Números de nível C existem aqui de propósito. Eles indicam onde vale investir uma checagem,
não servem de munição para peça publicada.

## Rotina sugerida

1. Rodar `python3 raspar_news_ia.py` toda segunda. A saída datada cai em `dados/saida/`.
2. Ler o digest, promover o que for relevante para o arquivo temático correspondente.
3. Antes de qualquer peça, filtrar `dados/fatos-citaveis.csv` por `confianca` igual a A ou B.
4. Reconferir números de nível A a cada trimestre. Leaderboard muda rápido.

## O script de varredura

`raspar_news_ia.py` roda sem dependência externa, só biblioteca padrão.

```bash
python3 raspar_news_ia.py              # janela de 14 dias
python3 raspar_news_ia.py --dias 30    # janela maior
python3 raspar_news_ia.py --verificar  # testa se todas as fontes respondem
python3 raspar_news_ia.py --tudo       # sem filtro de palavra chave
```

Ele cobre 22 fontes vivas. Dezesseis por RSS ou Atom, seis por raspagem de HTML porque não
publicam feed, e mais quatro consultas ao arXiv. A saída são dois arquivos datados em
`dados/saida/`, um CSV para filtrar e um markdown para ler.

As fontes que não têm feed e precisam de checagem manual estão em `dados/fontes.csv` com
status `sem feed`. São justamente os leaderboards e os relatórios anuais, que mudam devagar e
compensam olhar de mês em mês.

Primeira execução em 2026-09-02, janela de 21 dias. 272 itens relevantes de 3.224 coletados.
