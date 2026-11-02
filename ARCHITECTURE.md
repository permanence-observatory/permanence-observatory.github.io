# Arquitetura

Repositório do **Slum News Tracker** do Permanence Observatory: um mapa interativo (Leaflet) de notícias sobre assentamentos informais, publicado via GitHub Pages e regenerado automaticamente todo dia.

## Como o sistema funciona

```
GitHub Actions (cron diário)
  └─ python gdelt_version_v21.py
       ├─ consulta a GDELT DOC API (uma requisição por termo de busca)
       ├─ geocodifica cada artigo pelo dicionário local de locais
       ├─ classifica o tipo de evento e extrai nº de afetados
       └─ escreve slum_news_map.html  (+ slum_news_data.json)
  └─ cp slum_news_map.html index.html
  └─ git add index.html && git commit && git push   (como github-actions[bot])
```

### O workflow (`.github/workflows/update-map.yml`)

- **Quando roda:** `cron: '0 0 * * *'` (00:00 UTC) e manualmente via `workflow_dispatch` na aba Actions. Na prática o GitHub atrasa jobs agendados: os commits do bot costumam chegar entre ~04:45 e 05:00 UTC.
- **Ambiente:** `ubuntu-latest`, Python 3.11, `pip install requests pandas` (o `pandas` só é usado no código de CSV, que está comentado).
- **Saída:** copia `slum_news_map.html` para `index.html` e commita **apenas** `index.html`, com a mensagem `🗺️ Daily map update - AAAA-MM-DD`. Se o mapa não mudou, não há commit. Se o script não gerar o HTML, o job falha. Antes do push o job faz `git pull --rebase`, porque a `main` pode receber commits durante a rodada (que leva cerca de 1 h); e o grupo de `concurrency` impede duas rodadas simultâneas.
- `slum_news_data.json` é gerado mas **não é commitado** (só existe no runner).
- `.github/workflows/archive/` está vazio (só `.gitkeep`).

### O script (`gdelt_version_v21.py`)

Uma única classe, `RefinedSlumMapper`:

1. `load_extended_database()`: dicionário fixo de locais (favelas/slums, cidades e países do Sul Global) com lat/lon. Adiciona automaticamente uma variante em Title Case de cada nome e algumas grafias sem acento. Hoje tem 450 entradas (225 slum, 151 city, 74 country).
2. `load_multilingual_keywords()`: palavras-chave em en/pt/es/fr.
3. `search_gdelt_only()`: para cada termo (nomes de slums + palavras-chave = 297 consultas), faz `GET https://api.gdeltproject.org/api/v2/doc/doc` com frase exata, `mode=artlist`, `maxrecords=50`, `sort=datedesc`, sem restrição de data. Respostas vazias ou que não são JSON são descartadas em silêncio. Dedup por URL.
4. `process_articles()`: `extract_location_from_text()` (regex com prioridade slum → cidade → país; artigo sem local conhecido é descartado), `extract_event_type()` (primeira palavra-chave que casar, na ordem do dicionário) e `extract_affected_count()`.
5. `create_html_map()`: monta o HTML inteiro (CSS + JS + dados como JSON embutido) numa única f-string e grava `slum_news_map.html`.

## O que NÃO editar à mão

- **`index.html`**: é sobrescrito todo dia pelo bot. Qualquer mudança de layout, cor, texto, basemap ou JS do mapa deve ser feita no template dentro de `create_html_map()` em `gdelt_version_v21.py`. Lembre que ali é uma f-string: chaves literais de CSS/JS precisam ser dobradas (`{{` `}}`), inclusive nos placeholders de URL de tiles (`{{z}}/{{y}}/{{x}}`).
- **`index.old.html`**: snapshot antigo do mapa (renomeado em 2026-10-29). Nada o referencia; não editar nem regenerar.
- **`slum_news_map.html` / `slum_news_data.json`**: artefatos locais do script. O `.gitignore` só cobre `__pycache__/`, então cuidado para não commitá-los ao rodar localmente.
- Imagens na raiz (`banner_po.jpg`, logos, etc.) são usadas pelo `README.md`, não pelo mapa.

Como o bot commita em `main` todo dia, sempre faça `git pull` antes de trabalhar. Conflito em `index.html` se resolve aceitando qualquer lado: ele será regenerado na próxima execução.

## Decisões já tomadas

- **Custo zero.** O projeto não tem financiamento: toda fonte de dados, API, serviço e infraestrutura precisa ser gratuita (dados abertos, níveis gratuitos, GitHub Actions e GitHub Pages do repositório público, modelos abertos). Qualquer dependência de nível gratuito que possa acabar deve ter alternativa que funcione sem ela.
- **Modelos de IA podem fazer parte do método.** Modelos de linguagem e de processamento de texto podem ser usados na coleta, filtragem, geolocalização e classificação das notícias, desde que isso seja documentado como parte da metodologia (qual modelo, versão e instruções usadas) e que os resultados possam ser auditados (guardar o trecho do texto que justifica cada localização e classificação).
- **Fonte de dados: só GDELT DOC API** (sem chave de API). Outras fontes foram removidas ("GDELT only").
- **Geocodificação só pelo dicionário local**, sem serviço externo de geocoding. Vários slums usam a coordenada da cidade, de propósito. Para cobrir um novo lugar, adicione-o em `load_extended_database()` (isso também cria uma nova consulta, se for `type: 'slum'`).
- **Sem filtro de data** nas consultas (o GDELT já devolve basicamente notícias recentes, ~0–7 dias).
- **CSV desativado**; só o JSON é gerado, e ele não é publicado.
- **Categoria "other"** aparece no mapa e tem botão de filtro, mas fica fora do gráfico de barras.
- **Legenda dinâmica**: as faixas de intensidade são calculadas em Python (`calculate_legend_intervals`) e repetidas em JS (`getIntensityColor`). Se mudar uma, mude a outra.
- **Basemap: Esri World Dark Gray** (`Canvas/World_Dark_Gray_Base` + `Canvas/World_Dark_Gray_Reference` para os rótulos), `maxZoom: 16`, atribuição Esri. O basemap anterior, **CARTO Dark Matter (`basemaps.cartocdn.com/dark_all`), passou a exigir chave de API e foi trocado** pelo Esri, que funciona sem chave. Não voltar para o CARTO. A troca foi feita no script em 2026-11-02, depois da execução daquele dia; o `index.html` só passa a usar o Esri a partir da próxima execução do workflow. Não há filtro CSS: os tiles da Esri já são escuros.

## Rodar localmente

```bash
pip install requests pandas
python gdelt_version_v21.py
```

Faz ~300 requisições sequenciais à GDELT; espere vários minutos. Abra `slum_news_map.html` no navegador para conferir. Não commite os arquivos gerados; o deploy é só pelo workflow.
