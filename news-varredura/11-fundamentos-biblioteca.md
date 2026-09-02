# Biblioteca de fundamentos

Análise do repositório `MinhNguyenDS/AI-pdf-books` feita em 2026-09-02. 73 arquivos, 706 MB,
174 estrelas, último push em 18/jul/2026.

Este arquivo guarda a curadoria. Não guarda os PDFs.

---

## Aviso de direito autoral

O repositório redistribui livros da O'Reilly, Manning, Springer e MIT Press. A licença MIT
declarada cobre a estrutura do repositório, não o conteúdo dos livros. Na prática é um espelho
de material protegido.

A decisão aqui foi absorver a bibliografia e descartar os arquivos. Para cada título que vale a
pena, este arquivo aponta o caminho legítimo. Vários deles têm cópia oficial gratuita, o que
torna a pirataria desnecessária inclusive por conveniência.

## O diagnóstico em uma frase

É uma boa biblioteca de fundamentos com cobertura zero da camada de 2025 e 2026.

Nada ali trata de context engineering, harness, Agent Skills, MCP, RLVR, avaliação como
infraestrutura de produção ou recuperação híbrida com reranking. São exatamente os temas dos
arquivos `03` a `06` desta pasta. As duas coisas são complementares, não concorrentes. O
repositório cobre a base que não muda. A varredura cobre a camada que muda todo mês.

---

## Camada 1. Vale absorver de verdade

Sete títulos justificam investimento de tempo ou de dinheiro.

| Título | Por que | Onde obter |
|---|---|---|
| **AI Engineering**, Chip Huyen | Já era a recomendação número um do arquivo `09`. O repositório confirma o consenso | [huyenchip.com/books](https://huyenchip.com/books/), O'Reilly |
| **Designing Machine Learning Systems**, Chip Huyen | Complementar ao anterior. Drift, retreino, avaliação | [huyenchip.com/books](https://huyenchip.com/books/), O'Reilly |
| **Build a Large Language Model (From Scratch)**, Raschka | O mesmo autor do Ahead of AI, que já está no nosso catálogo de feeds. Código aberto e gratuito no GitHub | [github.com/rasbt/LLMs-from-scratch](https://github.com/rasbt/LLMs-from-scratch), Manning |
| **Speech and Language Processing**, Jurafsky e Martin | O livro-texto de PNL. A 3ª edição é atualizada continuamente | **Gratuito e oficial**, [web.stanford.edu/~jurafsky/slp3](https://web.stanford.edu/~jurafsky/slp3/) |
| **Storytelling with Data**, Knaflic | O sleeper hit da lista para uma casa de insights. Não é sobre IA, é sobre a entrega. Resolve o problema do arquivo `08` sobre insight que não vira decisão | Editora |
| **Practical Statistics for Data Scientists** | Base quantitativa para quem entrega pesquisa. Amostragem, significância, viés | O'Reilly |
| **Building Applications with AI Agents**, O'Reilly | O único da lista que toca sistemas multiagente. Triangula com o material da Anthropic no arquivo `03` | O'Reilly |

## Camada 2. Gratuitos e legítimos, vale linkar no onboarding

| Título | Link oficial |
|---|---|
| Python Data Science Handbook, VanderPlas | [jakevdp.github.io/PythonDataScienceHandbook](https://jakevdp.github.io/PythonDataScienceHandbook/) |
| Python for Data Analysis, 3ª ed, McKinney | [wesmckinney.com/book](https://wesmckinney.com/book/) |
| Prompt Engineering Guide | [promptingguide.ai](https://www.promptingguide.ai/) |
| The Probability and Statistics Cookbook | Distribuição livre do autor |
| Stanford, cheatsheet de transformers e LLMs | Stanford CS |

Acréscimo que falta no repositório e é gratuito. **Dive into Deep Learning**, em
[d2l.ai](https://d2l.ai/). Substitui com vantagem o *Fundamentals of Deep Learning* da lista,
porque é mantido e traz implementação em PyTorch, JAX e TensorFlow.

## Camada 3. Os papers, todos livres no arXiv

Vinte e seis arquivos na pasta `Paper`, catorze deles são artigos identificados só pelo ID.
Resolvidos abaixo. Todos são gratuitos e legítimos no arXiv, então o repositório não agrega
nada aqui além da curadoria.

Os cinco que sustentam diretamente o que já escrevemos:

| ID | Título | Onde entra |
|---|---|---|
| 2306.05685 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | Fundamenta o arquivo `06` sobre evals e o próprio Arena do arquivo `01` |
| 2305.20050 | Let's Verify Step by Step | Supervisão de processo, o precursor direto do RLVR do arquivo `06` |
| 2408.08435 | Automated Design of Agentic Systems | Desenho automático de sistema agêntico, dialoga com o harness do arquivo `03` |
| 2501.14249 | Humanity's Last Exam | O HLE que citamos no arquivo `02` para mostrar onde o gap aberto contra fechado persiste |
| 2408.08921 | Graph Retrieval-Augmented Generation, A Survey | Complementa o arquivo `05`, que não cobre RAG em grafo |

Os demais, por ordem de utilidade para nós:

| ID | Título |
|---|---|
| 2311.12022 | GPQA, A Graduate-Level Google-Proof Q&A Benchmark |
| 2406.01574 | MMLU-Pro, benchmark mais robusto de compreensão multitarefa |
| 2107.03374 | Evaluating Large Language Models Trained on Code, origem do HumanEval |
| 2401.05566 | Sleeper Agents, LLMs enganosos que sobrevivem ao treino de segurança |
| 2408.12599 | Controllable Text Generation for LLMs, A Survey |
| 2410.03131 | Code Comprehension then Auditing for Unsupervised LLM Evaluation |
| 1910.13461 | BART |
| 2001.08210 | mBART, pré-treino multilíngue |
| 2111.09543 | DeBERTaV3 |

Os quatro últimos são de arquitetura pré-LLM. Valem como história, não como operação.

Fora os artigos, a pasta traz dois materiais de método que valem para o time.
**How to Read a Paper** e **The Craft of Research**. Ler paper com método é habilidade
subestimada num time que precisa citar fonte primária.

## Camada 4. Pular

| Título | Motivo |
|---|---|
| NLTK Cookbook, NLP with Python, Foundations of Statistical NLP | PNL pré-LLM, de 1999 a 2009. História, não prática |
| Hands-On ML with Scikit-Learn and TensorFlow | Edição antiga. E não treinamos modelo do zero |
| Data Mining Concepts and Techniques, 3ª ed | De 2011, acadêmico |
| Exploratory Data Analysis with R | Somos casa Python |
| FastAPI, dois livros | Framework web genérico, não é diferencial nosso |
| Python for DevOps, AWS serverless, GenAI on Kubernetes | Infraestrutura, fora do nosso foco |
| Database Internals | Livro excelente, prioridade errada |
| Os três arquivos em vietnamita | Barreira de idioma |
| Generative AI with LangChain, 2024 | LangChain mudou muito desde 2024. Documentação atual vale mais |
| Designing Large Language Model Applications, 2023 | Anterior à era de agentes. Superado pelo que está nos arquivos `03` e `04` |

## O que a biblioteca não cobre, e nós já cobrimos

Esta é a parte que interessa para posicionamento. Nenhum dos 73 arquivos trata de:

- Context engineering e progressive disclosure. Arquivo `04`.
- Desenho de harness e arquitetura planner, generator, evaluator. Arquivo `03`.
- Agent Skills e MCP como padrão aberto. Arquivos `03` e `04`.
- RLVR e o pós-treino que explica os modelos de raciocínio. Arquivo `06`.
- Avaliação como infraestrutura de produção, com calibração e amostragem. Arquivo `06`.
- Recuperação híbrida, reranking, context rot e late interaction. Arquivo `05`.
- Qualquer coisa sobre pesquisa de mercado e insights. Arquivo `08`.

A conclusão prática. A biblioteca serve de camada de fundamentos para quem entra no time. A
vertical de varredura serve de camada de atualidade para quem escreve e vende. Manter as duas
separadas, com a biblioteca mudando devagar e a varredura mudando toda semana.

## Decisão

1. Não clonar os 706 MB. A bibliografia foi absorvida aqui.
2. Adquirir de forma legítima os sete títulos da camada 1. Assinatura da O'Reilly resolve
   cinco deles de uma vez e sai mais barato que comprar avulso.
3. Linkar os gratuitos da camada 2 no material de integração de quem entra no time.
4. Baixar do arXiv os cinco papers prioritários da camada 3 e anexá-los como leitura de apoio
   dos arquivos `02`, `03`, `05` e `06`.
5. Ignorar as camadas 4.
