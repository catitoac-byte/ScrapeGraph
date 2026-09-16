# Fontes de dados do Google Maps para escala nacional

Pesquisa em páginas públicas, em 16/09/2026. Nenhuma conta foi criada.

## Resumo

- **Google Places API (oficial):** única opção licenciada. Traz no máximo 5 avaliações por loja, não traz horários de pico e só permite guardar o place_id sem prazo.
- **Outscraper, SerpApi e Bright Data:** coletam do próprio Google Maps e entregam avaliações completas. Outscraper e SerpApi confirmam horários de pico (`popular_times`). Na Bright Data isso não foi confirmado.
- **Recomendação para o piloto (16 a 20 lojas):** Outscraper. Custo quase zero, com pico, contagem por estrela, resposta do dono e corte por data.
- **Recomendação para escala nacional:** Outscraper é a mais barata, estimada em cerca de US$333 por mês para 2.000 lojas. Bright Data custa mais e entrega em S3 ou Snowflake, com contrato e SLA. Antes de fechar, confirmar por escrito os campos de pico e de estrelas.
- **Validação jurídica:** avaliar o uso de dados raspados num painel vendido a clientes. A política do Google para a API oficial exige mostrar o autor da avaliação, o que conflita com a regra de não exibir nomes.

## Estimativa de custo para 2.000 lojas (premissas no relatório completo)

| Fonte | Carga inicial (300 avaliações por loja) | Mensal (cerca de 15 avaliações novas por loja por semana) |
|---|---|---|
| Outscraper | cerca de US$803 | cerca de US$333 |
| Bright Data (Web Scraper API) | US$782 a US$903 | cerca de US$198 (a confirmar os campos) |
| SerpApi | plano de US$725 por um mês | plano de US$150 |
| Google Places API | não se aplica | cerca de US$25, sem pico e com só 5 avaliações |

## Pontos a confirmar

- Na Bright Data: `popular_times`, contagem por estrela e resposta do dono.
- Na Outscraper: webhook e modo assíncrono, e se a consulta cobra quando não há avaliação nova desde a data de corte.
- Na SerpApi: se a resposta do dono vem no JSON.

## Fontes

- https://developers.google.com/maps/billing-and-pricing/pricing
- https://developers.google.com/maps/documentation/places/web-service/policies
- https://cloud.google.com/maps-platform/terms/maps-service-terms
- https://brightdata.com/pricing/web-scraper
- https://brightdata.com/products/web-scraper/google-maps
- https://outscraper.com/pricing/
- https://outscraper.com/google-maps-reviews-api/
- https://serpapi.com/pricing
- https://serpapi.com/google-maps-api
- https://serpapi.com/google-maps-reviews-api
