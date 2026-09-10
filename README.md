# Porquinho TV

Quantas entrevistas exclusivas deu André Ventura na televisão portuguesa. Um site estático, uma contagem pública, uma fonte por linha.

O site publica, por período (semana, mês, ano, desde sempre): entrevistas exclusivas e emissões (uma por canal e dia). Não conta tempo: desde 2026-09-10 conta só a existência de cada entrevista. Mostra a repartição pelos nove canais generalistas e de informação, a evolução por semana, mês e ano, um calendário dia a dia e a lista completa de fontes. A mascote reage ao número de dias desde a última entrevista.

## Como funciona

- `config/entrevistas.yml` é o registo do canal: uma linha por emissão, com data, canal, programa e URL de prova. É a fonte principal.
- `config/clipping.yml` são as emissões provadas por peças de imprensa: a peça nomeia o canal, diz entrevista e fixa o dia, relatando a entrevista ou anunciando-a. Provam que a emissão existiu e quando, que é tudo o que se conta, e valem o mesmo que a página do canal. Entram identificadas como tal e nunca deslocam um registo do canal.
- `config/fontes.yml` declara as fontes automáticas. A principal é a pesquisa do próprio site de cada canal: pede a pesquisa do canal por cada forma do nome, recolhe os endereços de artigo desse domínio e lê de cada página o que ela publica em schema.org e OpenGraph. Não há seletores de HTML de nenhum site, e por isso a leitura sobrevive a uma remodelação em vez de passar a devolver zero em silêncio.
- Uma emissão vinda de fonte automática não entra na primeira vez que é vista: só entra depois de o mesmo bloco aparecer em rondas distintas. O registo de avistamentos está em `docs/dados/candidatos.json`, e ao lado de cada linha ficam as rondas e o número de fontes distintas que a viram. Ver a Metodologia para o que isto protege e o que não protege.
- `recolha/` aplica o critério em `config/porquinho.yml`, escreve `docs/dados/emissoes.json` (append-only), `docs/dados/quarentena.json` (tudo o que ficou de fora, com motivo) e `docs/dados/resumo.json` (os agregados).
- `docs/` é o site. Zero dependências externas: sem CDN, sem fontes remotas, sem analytics. A fonte tipográfica é servida localmente, licença OFL ao lado.
- Uma GitHub Action corre a recolha todos os dias e publica as alterações.

A [Metodologia](METODOLOGIA.md) diz o que conta, o que não conta e onde o método falha.

## Correr localmente

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .      # 68 testes, offline
node --test tests/frontend/*.test.js           # 13 testes a logica do site, sem browser
python -m recolha.principal --dry-run          # nao escreve nada
python -m recolha.principal                    # escreve docs/dados
python -m recolha.principal --paginas 15       # mais fundo no tempo (historico)
python -m http.server -d docs 8000
```

Antes de ativar uma fonte nova, `python -m ferramentas.descobrir <url>` mostra o que a página anuncia e o que o feed contém.

`python -m ferramentas.levantamento` (ou o workflow `levantamento`, a pedido) sonda as páginas dos nove canais declaradas em `config/levantamento.yml`, resolve os canais de YouTube e conta no arquivo.pt o que existe por domínio e por ano. Escreve `levantamento/`, que não faz parte do site. É o passo antes de qualquer adaptador novo.

## Contribuir com uma emissão

Para acrescentar ou retirar uma emissão à mão, usar `config/curadoria.yml`: a lista `entrevistas` precisa apenas de `data`, `canal` e `prova` (mais `origem: imprensa` se a prova for uma notícia), e a lista `remover` leva a `prova` e o `motivo`. Uma linha removida passa a aparecer na quarentena com o motivo, em vez de desaparecer.

Para uma linha do registo principal, acrescentar a `config/entrevistas.yml` com os campos obrigatórios (`data`, `canal`, `prova`). Não há campo de duração: uma linha que traga `duracao_s` ou `parcial` é recusada pelo coletor. Se a prova for uma peça de imprensa e não o canal, a linha vai para `config/clipping.yml`. Sem URL de prova a linha é rejeitada pela suite de testes.

## Licenças

A fonte Fredoka em `docs/tipos` está sob a SIL Open Font License, incluída ao lado do ficheiro. A licença do código e dos dados está em `LICENSE`.
