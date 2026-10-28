# Radar de mercado: camada de coleta

Coleta sistemática de feeds, sitemaps e consultas para o radar semanal de temas, hipóteses, hypes e buzz em pesquisa, insights e inovação, por categoria de produto da Cassi.ai. Sem LLM: a coleta e a conferência literal são determinísticas, e o julgamento fica com os agentes. Código em `src/scraper_lab/radar.py`, comando em `raspar_radar.py`. Reaproveita `CachePaginas`, `robots.py` e `citacao_confere` da vertical `duvidas_mercado`.

## Ambiente (worktree sem Scrapegraph-ai ao lado)

O `pyproject.toml` aponta para `../Scrapegraph-ai`, que só existe no checkout principal. Na worktree, `uv run` sem flag tenta resolver esse caminho e falha. A solução que funciona:

1. `.venv` próprio da worktree (já criado, fora do git), criado com o Python do venv do checkout principal e com pytest instalado.
2. Um arquivo `.venv/lib/python3.12/site-packages/main_libs.pth` com uma linha que põe `scraper-lab/src` da worktree na frente de `sys.path` e adiciona o `site-packages` do checkout principal (`ScrapeGraph/scraper-lab/.venv`) como diretório de site. Assim `scraper_lab` vem da worktree e `scrapegraphai`, `bs4`, `lxml`, `pypdf`, `playwright` vêm do checkout principal.
3. Rodar sempre com `uv run --no-sync` (não tenta resolver nem sincronizar dependências).

Recriar do zero:

```
cd "<worktree>/scraper-lab"
M="/Users/cassianoalbuquerque/Antigravity Projects/ScrapeGraph/scraper-lab/.venv"
uv venv .venv --python "$M/bin/python"
uv pip install --python .venv/bin/python pytest pytest-asyncio
echo "import sys, site; site.addsitedir('$M/lib/python3.12/site-packages'); sys.path.insert(0, '$PWD/src')" \
  > .venv/lib/python3.12/site-packages/main_libs.pth
```

Comandos:

```
cd "/Users/cassianoalbuquerque/Antigravity Projects/ScrapeGraph-wt-duvidas/scraper-lab"
uv run --no-sync python raspar_radar.py coletar --config verticais/radar.config.fixture.json \
    --categoria synthetic --janela 90 --saida dados/saida/radar --teto-paginas 40
.venv/bin/python -m pytest -q          # 67 testes
```

## Comandos

```
raspar_radar.py coletar --config <radar.config.json> --categoria <cat> --janela <dias> --saida <dir>
                        [--teto-paginas N] [--teto-buscas N] [--dry-run] [--navegador]
raspar_radar.py conferir <arquivo_de_sinais.json> [--navegador]
raspar_radar.py feeds --config <cfg> [--janela 90] [--atualizar]
raspar_radar.py registrar-buscas <buscas.json>
```

### coletar

1. Lê `fontes_feeds` e `consultas[categoria]` do config. Chave ausente vira aviso (em `meta.avisos`), nunca erro.
2. Feeds RSS e Atom: itens com data (`pubDate`, `published`, `updated`, `dc:date`) dentro de `[hoje - janela, hoje + 1 dia]`. Item sem data ou fora da janela é descartado. Sitemaps: URLs com `lastmod` (ou `news:publication_date`) na janela; índice de sitemap abre até 6 filhos, só os com `lastmod` na janela. Por fonte ficam no máximo 300 itens, os mais novos.
3. Consultas: Brave com `BUSCA_PROVIDER=brave` e `BRAVE_API_KEY`, que é o buscador do projeto (`sinteticos.py`, `duvidas_mercado.py`). Não existe buscador sem chave que o projeto use e que seja permitido: `html.duckduckgo.com` dá desafio anti-robô (está em `bloqueios_conhecidos`) e o RSS do Bing proíbe `/search` no robots.txt, então nenhum dos dois é usado. Sem chave, a coleta usa só os resultados registrados à mão com `registrar-buscas` (`dados/cache/radar/buscas.json`) e segue com feeds. O fato fica em `meta.busca` e em `consultas_usadas`.
4. Prioridade para abrir páginas: só entram itens de feed ou sitemap que tenham palavra do vocabulário no título, resumo ou slug da URL; o resto conta em `itens_de_feed` mas não gasta página. A ordem alterna entre publicadores (rodízio) até o teto de páginas.
5. Cada página abre pelo `CachePaginas` (cache em disco em `dados/cache/radar/paginas`, pausa de 1,2 s por domínio, robots.txt, HTTP 401/403/429/451/999 vira `not accessible` e não se insiste). Chromium só com `--navegador`.
6. Trechos: parágrafos da página que contêm termo do vocabulário da categoria, reconstruídos a partir das linhas do texto guardado (linha de link inline volta para o parágrafo; título e menu são descartados). Pontuação: 1 por termo do vocabulário e 2 por termo de sinal. Ficam até 5, na ordem da página, cortados em 500 caracteres em fronteira de palavra. Todo trecho é literal: o teste confere cada um com `citacao_confere` contra o texto guardado.
7. Candidato exige pelo menos um trecho. Se a página declara data fora da janela (mesmo que o sitemap diga que mudou na janela), é descartado. `data_pagina` é a data da página; sem ela, a data do item; sem ambas, a data da página (`not found`).
8. Deduplica por URL canônica (sem `utm_*`, fragmento, barra final, host em minúsculas).

Saída `<saida>/candidatos-<categoria>.json`:

```
{"meta": {"categoria", "janela_dias", "data_corrida", "fontes_lidas", "itens_de_feed", "paginas_abertas",
          "consultas_usadas", "bloqueados": [{"url", "estado", "motivo"}],
          // extras: "avisos", "fontes_com_falha", "itens_na_janela", "itens_com_vocabulario",
          //         "paginas_do_cache", "busca", "dry_run"},
 "candidatos": [{"url", "publicador", "titulo", "data_pagina", "idioma", "consulta_ou_feed", "trechos": [str],
                 "cache_path", "score"}]}
```

`paginas_abertas` conta as abertas na rede nesta corrida; as que vieram do cache ficam em `paginas_do_cache`. `bloqueados` traz robots, 403 e 429 (`not accessible`) e também páginas que falharam (`erro`, por exemplo 404). `idioma` é detectado no texto (en, pt, es) e cai no idioma da fonte quando inconclusivo. `consulta_ou_feed` vale `feed: <publicador> (<url>)` ou `consulta: <texto>`. `score` e os campos extras de `meta` são aditivos.

### conferir

Para cada `sinais[].evidencias[].valor`, confere a presença literal no texto da página. Normaliza espaços, aspas e apóstrofos tipográficos e travessões; reticências (`...` ou `…`) separam fragmentos que precisam aparecer todos e na ordem. A página vem de `evidencias[].url` (ou `fonte`, ou `sinais[].url`), do cache, e é aberta (com robots) se não houver cache. Evidência sem URL é procurada em todas as páginas do cache. Violação: valor ausente ou vazio, página que não abre (inclui robots) e citação que não está no texto. Imprime as violações, grava `<arquivo>.conferencia.json` (`arquivo` + `.conferencia.json`) e sai com 1 se houver alguma.

### feeds

Para cada fonte do config: status HTTP, tipo detectado (rss, atom, sitemap, índice), número de itens, data do mais novo, itens na janela e `estado`: `vivo` (mais novo dentro da janela), `parado`, `sem_datas`, `invalido`, `fora` (não respondeu ou robots). `--atualizar` grava o resultado em `status` dentro de cada fonte do config. Sempre baixa de novo (sem cache de feed).

## Formato do config

Escrito pela squad do radar. A camada lê só as chaves abaixo e tolera as ausentes. Exemplo completo em `verticais/radar.config.fixture.json`.

```
{
 "fontes_feeds": [{"publicador": "Retail Dive", "idioma": "en", "tipo": "rss|atom|sitemap|auto",
                   "url": "...", "incluir": "regex opcional de URL para sitemap"}],
 "consultas":    {"synthetic": {"en": ["..."], "pt": ["..."], "es": ["..."]}},
 "vocabulario":  {"synthetic": {"en": ["synthetic", ...], "pt": [...], "es": [...]}},
 "termos_de_sinal": {"en": ["trend", "hype", ...], "pt": [...], "es": [...]},
 "bloqueios_conhecidos": {"linkedin.com": "HTTP 999"}
}
```

Tolerâncias: `fontes_feeds` também como dicionário `{publicador: {...}}`; uma fonte pode trazer `feed` e `sitemap` juntos (viram duas); `tipo` ausente é deduzido da URL; `idioma` ausente assume `en` com aviso; fonte sem URL é ignorada com aviso; `vocabulario` e `consultas` aceitam lista simples no lugar de dicionário por idioma; sem `vocabulario` da categoria o vocabulário é derivado das palavras de 5+ letras das consultas (com aviso); sem `termos_de_sinal`, valem os padrões do projeto em en, pt e es (`trend`, `hype`, `survey finds`, `report`, `launch`, `tendência`, `pesquisa mostra`, `lançamento`, `tendencia` e outros). O vocabulário casa sem diferenciar maiúscula ou acento, no início da palavra (`synthetic` pega `synthetically`, `sintético` pega `sinteticos`).

## Feeds do setor

Lista viva em `verticais/radar_feeds.json`, com o status da última medição em cada fonte (o arquivo já tem o formato de `fontes_feeds`; a outra squad pode copiar o array). Medição de 27/10/2026, `feeds --atualizar`: 18 vivas, 3 paradas, 1 sem datas, 1 fora do formato removida.

| Idioma | Vivos (feed ou sitemap) |
|---|---|
| en | Quirk's (sitemap), GreenBook (sitemap de artigos), ESOMAR (sitemap), Retail Dive, Customer Experience Dive, MarTech, Marketing Dive, Marketing Week, podcasts GreenBook, The Exchange, Insights & Innovators (MRII) e Data Gurus |
| pt | Meio & Mensagem, Consumidor Moderno, Mercado & Consumo, Fast Company Brasil, ABEP |
| es | Merca2.0, Marketing Directo |

Paradas ou sem uso na janela: Research Live (feed `/feed/rss.php` parado desde jan/2025), MRS (sitemap sem datas úteis), Detrás del Insight (podcast, último episódio em jun/2026), Mundo do Marketing (sitemap sem datas, site em Framer e `/feed-rss` é página HTML). Sem feed público: Insights Association, ESOMAR Research World (`rwconnect.esomar.org`, coberto pelo sitemap do ESOMAR), blog da IIEX (coberto pelo sitemap do GreenBook), podcast do Quirk's. O CX Dive vive em `customerexperiencedive.com`, porque `cxdive.com` não resolve. Reexecutar `feeds --atualizar` semanalmente mantém a lista honesta.

## Corrida real de 27/10/2026

`coletar --categoria synthetic --janela 90 --teto-paginas 40` com `verticais/radar.config.fixture.json` (23 fontes): 23 fontes lidas, 1.208 itens na janela, 43 com vocabulário, 40 páginas abertas, 18 candidatos (todos em inglês, 58 trechos, todos literais), 3 bloqueados (todos `erro` HTTP 404: o feed do podcast GreenBook aponta episódios para um host de staging, `greenbookgbb.wpengine.com`), 0 consultas (sem chave Brave). Não houve `not accessible` por robots nesta corrida. Os itens em pt e es não citaram o vocabulário de `synthetic` na janela. Saída em `dados/saida/radar/` (fora do git).

## Limites

Páginas montadas por JavaScript voltam quase vazias sem `--navegador`. Trecho depende de o texto guardado conservar o parágrafo: tabela e gráfico não entram. Sitemap sem `lastmod` não serve para janela. O resumo do feed ajuda a priorizar, mas nenhum trecho nasce dele: só do texto da página aberta.
