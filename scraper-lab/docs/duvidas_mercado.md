# Vertical duvidas_mercado

Perguntas, dores, objeções e mitos do mercado por produto da Cassi.ai, em citação literal com URL e data. Configuração em `verticais/duvidas_mercado.json`, código em `src/scraper_lab/duvidas_mercado.py`, comando em `raspar_duvidas_mercado.py`. PRD em `portfolio-content-output/videos-linkedin/varredura-mercado/PRD_E_PROMPT.md`.

## Como rodar

```
uv run python raspar_duvidas_mercado.py --produto dash-lab --dry-run            # plano de buscas, sem rede
uv run python raspar_duvidas_mercado.py --produto dash-lab --pendentes          # consultas ainda sem busca
uv run python raspar_duvidas_mercado.py --produto dash-lab --registrar buscas.json
uv run python raspar_duvidas_mercado.py --produto dash-lab --produto video-lab --teto-buscas 10
uv run python raspar_duvidas_mercado.py --todos                                 # os 15, teto 30 cada
```

Busca: com `BUSCA_PROVIDER=brave` e `BRAVE_API_KEY` no ambiente as buscas rodam sozinhas. Sem isso, o operador roda as consultas de `--pendentes` em qualquer buscador e registra os resultados com `--registrar` (lista de `{produto, varredura, consulta, idioma, resultados:[{url}]}`). O teto vale por produto (`--teto-buscas`, máximo 30) e por varredura (P1 a P4, repartido na proporção 10/8/6/6). Resultado de busca só indica onde olhar: nenhum achado nasce de snippet.

Extração: com `LLM_PROVIDER=manual` (padrão) por padrões de linguagem em en, pt e es; com provedor configurado, o LLM propõe e a mesma conferência literal descarta o que não estiver na página. Achados escritos à mão podem entrar em `dados/cache/duvidas_mercado/fichas/<slug>.json` (lista no formato do schema) e passam pelo mesmo validador.

Retomada: páginas ficam em `dados/cache/duvidas_mercado/paginas/` e buscas em `buscas.json`. Rodar de novo não reabre página guardada. Bloqueio (403, 429, 999, robots.txt) vira `not accessible` e não se insiste.

## Onde sai

`dados/saida/duvidas_mercado/<slug>.json` (ou o diretório de `--saida`), no formato de `achados.schema.json`. Relatórios em `_relatorio/` (`resumo.json`, `recall-<slug>.json`). O validador roda ao fim de cada produto e a corrida termina com código 1 se houver violação: citação ausente do texto guardado da página, URL sem http(s), enum fora do schema, id duplicado, `top_perguntas` inexistente, nome da lista de clientes, travessão ou contraste proibido em texto nosso, valor ou gratuidade no ângulo.

## Copiar para o repositório de conteúdo

Depois de conferir, copiar só os arquivos de produto, não a pasta `_relatorio`:

```
cp dados/saida/duvidas_mercado/*.json \
   ~/Antigravity\ Projects/portfolio-content-output/videos-linkedin/varredura-mercado/achados/
python3 ~/Antigravity\ Projects/portfolio-content-output/videos-linkedin/varredura-mercado/validar_achados.py
```

Cuidado: a cópia sobrescreve achados feitos à mão com o mesmo slug. Compare com `_relatorio/recall-<slug>.json` antes.

## Limites conhecidos

Sem LLM não há tradução para o português (`pt` fica ausente em achados em en e es), `grupo` só distingue fornecedor, comentarista, associação e academia (comprador em primeira pessoa entra por ficha), e `tema` e `angulo_video` são montados de `tema_pt`, `trabalho_pt` e `hoje_pt` de cada produto no config.
