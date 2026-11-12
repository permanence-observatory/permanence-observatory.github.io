# Arquitetura

Repositório do **Slum News Tracker** do Permanence Observatory: um mapa interativo (Leaflet) de notícias sobre assentamentos informais, publicado via GitHub Pages e regenerado automaticamente todo dia.

Hoje convivem dois sistemas, que rodam em paralelo e não dependem um do outro:

- **Mapa principal** (`index.html`): o sistema original, descrito logo abaixo.
- **Coletor diário e mapa experimental** (`pipeline/`, `data/gkg/`, `mapa/`): coleta dos arquivos brutos do GDELT GKG, classificação por um modelo de linguagem aberto, histórico diário e um mapa novo com filtros. Veja [Coletor diário e mapa experimental](#coletor-diário-e-mapa-experimental). O mapa principal só deve passar a usar o coletor depois que a qualidade for medida por algumas semanas.

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

## Coletor diário e mapa experimental

```
GitHub Actions (cron diário, 06:00 UTC, depois do mapa principal)
  └─ instala o Ollama e baixa o modelo aberto qwen2.5:7b (no próprio runner, sem custo)
  └─ python pipeline/collect_day.py            (dia UTC anterior)
       ├─ baixa os 96 arquivos de 15 min do GKG 2.1 (feed em inglês + feed traduzido de 65 idiomas)
       ├─ pré-filtro: tema SLUMS do GKG, nomes do dicionário de assentamentos (conferidos
       │  contra o país e, nos nomes ambíguos, a cidade que o GKG localizou), palavras-chave,
       │  ou palavra de remoção + palavra de moradia no título (porta de entrada das remoções)
       ├─ classifica cada título único com o modelo: relevância, temas, remoção e etapa,
       │  e o local mais específico citado ("bairro ou assentamento, cidade, país")
       ├─ regra de remoções: palavra de remoção que o modelo não chamou de remoção → revisão
       ├─ agrupa reimpressões da mesma notícia num assunto (story_id)
       └─ grava data/gkg/AAAA/MM/AAAA-MM-DD.jsonl e AAAA-MM-DD.summary.json
  └─ git add data/gkg && commit && pull --rebase
  └─ python pipeline/build_map_data.py         → mapa/events.json (depois do pull, com o histórico todo)
       └─ geocodifica o local lido pelo modelo com o GeoNames (pipeline/geocode.py, offline)
  └─ git commit --amend && push
```

- **Workflow:** `.github/workflows/collect-daily.yml`. Roda por `schedule` (só vale na `main`), por `workflow_dispatch` (com data opcional) e por push na branch `gkg-prototype` que mude o coletor. Commit do bot: `📥 Daily GKG collection - AAAA-MM-DD`. Leva de 1 a 2,5 h; o limite do runner é 6 h. Para recoletar vários dias, dispare um por vez ou até dois (um rodando e um na fila): o GitHub cancela a rodada que espera na fila quando outra entra. O job parte da branch como estava quando foi enfileirado; por isso o `events.json` é refeito só depois do `pull --rebase`, senão duas rodadas seguidas entram em conflito nele (foi o que derrubou a recoleta do dia 8 em 2026-11-11).
- **Código:** `pipeline/collect_day.py` (coletor), `pipeline/build_map_data.py` (dados do mapa experimental), `pipeline/review_batch.py` (lotes de revisão). O download, o filtro e as instruções do modelo ficam em `prototype/gkg_prototype.py` e `prototype/classify_llm.py`; o restante de `prototype/` são os testes que levaram a essas escolhas.
- **Histórico (`data/gkg/`):** cada linha é uma candidata, relevante ou não, com título, link, veículo, idioma, locais do GKG, critério do pré-filtro, relevância, temas, remoção e etapa, justificativa curta, `story_id`, e o modelo, a versão das instruções e a versão do coletor que a classificaram. Guardar também as não relevantes permite medir perdas e reclassificar o histórico com um modelo ou instrução melhor. Cerca de 600 candidatas e 0,6 MB por dia. O GKG bruto (cerca de 1,2 GB por dia) não é guardado: o GDELT mantém o arquivo público.
- **Resumo diário (`*.summary.json`):** candidatas, relevantes, assuntos relevantes, remoções do dia, sinalizadas para revisão, temas e maiores assuntos. Um salto ou queda brusca indica problema na rodada.
- **Mapa experimental (`mapa/`):** `mapa/index.html` é uma página estática editada à mão (não é gerada) que lê `mapa/events.json`. Um ponto por assunto relevante, com filtros por remoção e etapa, tema, período e busca. Publicado em `/mapa/` pelo GitHub Pages, com o mesmo basemap Esri do mapa principal.
- **Local de cada ponto (`pipeline/geocode.py`):** desde as instruções `2026-11-11.1` o modelo devolve o local mais específico do título (`place`, ex.: "Chembur, Mumbai, India"). O geocodificador o resolve offline com o GeoNames (CC BY 4.0): `cities500.zip` (cidades do mundo) e, só quando preciso, o arquivo completo do país (bairros e assentamentos), em cache em `.cache/geonames/` (fora do git; no Actions, `actions/cache`). A última parte que nomeia um país fixa o país; a parte mais geral restante é o contexto (cidade, estado, ou outro lugar como ilha ou condado); as partes mais específicas são procuradas a até 60 km da cidade ou dentro do estado. Precisão: `assentamento` (abaixo da cidade), `cidade`, `região` (estado ou província). Sem `place` utilizável, ou quando os locais do GDELT apontam o assentamento e o modelo só a cidade, vale o local do GDELT. Cada ponto grava a origem (`geo`: "modelo + GeoNames" ou "GDELT"). No teste de 2026-11-10: pontos no nível do assentamento passaram de 7 para 12 de 76, estados citados sozinhos passaram a aparecer como região (antes caíam numa cidade homônima) e várias cidades erradas do GDELT foram corrigidas (ex.: Igarapé Grande → Ananindeua, Jawhar → Mumbai).
- **Alertas:** se o coletor ou a atualização do mapa principal falhar, o workflow abre uma issue no repositório (o GitHub avisa por e-mail quem acompanha o repositório). O coletor falha de propósito quando o dia vem sem candidatas, com mais de 1/4 dos arquivos do GKG faltando, ou com mais de 1/5 das candidatas sem classificação (servidor do modelo com problema).
- **Auditoria do funil (`pipeline/audit_funnel.py`), uma vez por mês:** as revisões só medem o modelo sobre o que o pré-filtro deixou passar. A auditoria olha o outro lado: notícias do Sul global que **não** passaram no pré-filtro mas têm tema de moradia ou terra do GKG, ou palavra de assentamento ou ocupação no título. Sorteia uma amostra em duas metades (com palavra no título e só com o tema) e a envia como lote de revisão. A fração de "Sim" vezes o total de quase relevantes estima o que o sistema nunca vê. Primeira rodada (2026-11-10, 1/4 dos arquivos): 91 quase relevantes, só 4 com palavra de assentamento; o resto, em sua maioria, mercado imobiliário.
- **Revisão humana:** uma página de revisão fora do repositório recebe, a cada lote, todas as remoções e sinalizadas, uma amostra dos relevantes e uma amostra dos descartados, embaralhados. A pessoa responde sem ver a resposta do modelo. Os lotes são montados com `pipeline/review_batch.py`; títulos em idiomas que a equipe não lê recebem tradução.

## O que NÃO editar à mão

- **`index.html`**: é sobrescrito todo dia pelo bot. Qualquer mudança de layout, cor, texto, basemap ou JS do mapa deve ser feita no template dentro de `create_html_map()` em `gdelt_version_v21.py`. Lembre que ali é uma f-string: chaves literais de CSS/JS precisam ser dobradas (`{{` `}}`), inclusive nos placeholders de URL de tiles (`{{z}}/{{y}}/{{x}}`).
- **`index.old.html`**: snapshot antigo do mapa (renomeado em 2026-10-29). Nada o referencia; não editar nem regenerar.
- **`slum_news_map.html` / `slum_news_data.json`**: artefatos locais do script. O `.gitignore` só cobre `__pycache__/`, então cuidado para não commitá-los ao rodar localmente.
- **`data/gkg/`**: histórico gravado pelo bot do coletor. Não reescrever dias antigos à mão; uma reclassificação deve gerar novos arquivos com a nova versão do modelo ou das instruções registrada em cada linha.
- **`mapa/events.json`**: gerado por `pipeline/build_map_data.py` a cada rodada do coletor. Para mudar o que o mapa experimental mostra, mude o script ou `mapa/index.html`.
- Imagens na raiz (`banner_po.jpg`, logos, etc.) são usadas pelo `README.md`, não pelo mapa.

Como o bot commita em `main` todo dia, sempre faça `git pull` antes de trabalhar. Conflito em `index.html` se resolve aceitando qualquer lado: ele será regenerado na próxima execução.

## Decisões já tomadas

- **Custo zero.** O projeto não tem financiamento: toda fonte de dados, API, serviço e infraestrutura precisa ser gratuita (dados abertos, níveis gratuitos, GitHub Actions e GitHub Pages do repositório público, modelos abertos). Qualquer dependência de nível gratuito que possa acabar deve ter alternativa que funcione sem ela.
- **Modelos de IA podem fazer parte do método.** Modelos de linguagem e de processamento de texto podem ser usados na coleta, filtragem, geolocalização e classificação das notícias, desde que isso seja documentado como parte da metodologia (qual modelo, versão e instruções usadas) e que os resultados possam ser auditados (guardar o trecho do texto que justifica cada localização e classificação).
- **Fonte de dados do mapa principal: só GDELT DOC API** (sem chave de API). Outras fontes foram removidas ("GDELT only"). A DOC API limita e recusa pedidos (erro 429) mesmo com 30 s entre chamadas, e o script descarta essas respostas em silêncio.
- **Fonte de dados do coletor: arquivos brutos do GDELT GKG 2.1**, baixados direto (`data.gdeltproject.org/gdeltv2/`), sem limite de pedidos e em todos os idiomas, em cerca de 8 min por dia.
- **Modelo de classificação: qwen2.5:7b, servido pelo Ollama dentro do runner do GitHub Actions.** Escolhido em 2026-11-02 contra o gemma3:4b, que marcava quase tudo como relevante (concordância de 58% contra 90% numa amostra cega rotulada pela equipe). O GitHub Models foi desativado em 2026-07-30 e não serve como alternativa. As instruções ficam em `prototype/classify_llm.py` com versão (`PROMPT_VERSION`), gravada em cada linha do histórico. Passar pistas do pré-filtro ao modelo (tema SLUMS, nomes do dicionário) foi testado e piorou o resultado: o modelo tratou as pistas como prova.
- **Relevância ampla** (desde 2026-11-10, instruções `2026-11-10.1`): "Sim" para qualquer informação relevante sobre favelas e assentamentos informais, inclusive crime dentro deles, cultura e pessoas, desastres que atingem a área e políticas que os citam. "Não" só quando a palavra aparece por coincidência (time, marca, township dos EUA, "comunidade" genérica). Os dois conjuntos de referência de 2026-11 (`prototype/data/`) e o primeiro lote de revisão usaram a regra antiga, mais estrita (assentamento como tema central), e não são comparáveis.
- **Remoção é uma pergunta à parte e filtrável**, a prioridade do observatório. Em inglês o termo exibido é **"evictions"** (o usual da ONU e da imprensa para "forced evictions"); no código e no histórico o campo continua `removal`. Conta como remoção: remoção executada, ameaça ou anúncio, decisão judicial (autorizando ou impedindo) e reassentamento. Cada assunto tem também um ou mais temas (`removal`, `disaster`, `violence`, `housing_policy`, `infrastructure`, `land_conflict`, `protest`, `culture`, `economy`, `health_education`, `data`, `other`).
- **Remoção também é porta de entrada** (desde 2026-11-11): título ou link com palavra de remoção e palavra de moradia ou ocupação (casas, famílias, ocupação, viviendas, residents, settlement, logements...) entra como candidata mesmo sem tema SLUMS, nome ou palavra-chave. Num quarto do dia 10, isso trouxe 9 candidatas a mais (cerca de 36 por dia), entre elas demolições em Harare que antes ficavam de fora. As listas de palavras ficam em `prototype/gkg_prototype.py` e são compartilhadas pelo pré-filtro, pela regra de revisão e pela auditoria.
- **Nenhuma possível remoção é descartada em silêncio:** título ou link com palavra forte de remoção (eviction, demolição, desmantelamiento, despejo, remoção, déguerpissement...) e sinal de assentamento vai para revisão quando o modelo não a chamou de remoção. Palavras ambíguas em espanhol (desalojo, despejar) exigem termo de assentamento no próprio título.
- **Qualidade medida por revisão amostral**, separando remoção do resto: acerto (dos marcados como relevantes, quantos eram) e perda (dos descartados sorteados, quantos eram relevantes). Remoções são raras (de 1 a 5 por dia), então a medida delas leva semanas para ficar estável.
- **Geocodificação do mapa principal só pelo dicionário local**, sem serviço externo de geocoding. Vários slums usam a coordenada da cidade, de propósito. Para cobrir um novo lugar, adicione-o em `load_extended_database()` (isso também cria uma nova consulta, se for `type: 'slum'`).
- **Geocodificação do mapa experimental: modelo lê o local, GeoNames dá a coordenada** (desde 2026-11-11). Sem API de geocoding (Nominatim e afins têm limite de uso e exigem identificação); o GeoNames é um arquivo aberto baixado uma vez. O modelo só extrai o texto do local; quem escolhe a coordenada é uma regra determinística e auditável. Pedir o local ao modelo não mudou a classificação: no dia 10, das 645 candidatas em comum com a rodada anterior, a resposta de remoção foi a mesma em 643.
- **Sem filtro de data** nas consultas: cada consulta traz as 50 notícias mais recentes daquele termo, que podem ter semanas. A data de cada evento vem do `seendate` da GDELT (formato `AAAAMMDDTHHMMSSZ`); até 2026-11-02 um erro de leitura desse formato fazia todos os eventos receberem a data da rodada.
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

Coletor, sem o modelo (teste rápido do download, filtro e gravação):

```bash
python pipeline/collect_day.py --date 2026-11-09 --every 32 --no-llm --out /tmp/gkg
python pipeline/build_map_data.py
python -m http.server 8000   # e abra http://localhost:8000/mapa/
```

A classificação precisa de um servidor Ollama com o modelo (`ollama pull qwen2.5:7b`). Num computador com 8 GB de RAM ou menos ela fica lenta demais para medir; meça no runner do Actions.
