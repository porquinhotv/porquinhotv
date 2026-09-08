# Porquinho TV

Quantas entrevistas exclusivas deu André Ventura na televisão portuguesa, e quanto tempo ocuparam. Um site estático, uma contagem pública, uma fonte por linha.

O site publica, por período (semana, mês, ano, desde sempre): entrevistas exclusivas, emissões (uma por canal e dia), tempo no ar e quantas emissões estão provadas mas sem duração apurada. Mostra a repartição pelos nove canais generalistas e de informação, a evolução por semana, mês e ano, um calendário dia a dia e a lista completa de fontes. A mascote reage ao número de dias desde a última entrevista.

## Como funciona

- `config/entrevistas.yml` é o registo do canal: uma linha por emissão, com data, canal, programa, URL de prova e a duração declarada sempre que exista. É a fonte principal.
- `config/clipping.yml` é o último recurso: emissões provadas por peças de imprensa, para o que o canal nunca publicou ou já retirou. Entram identificadas como tal e nunca deslocam um registo do canal.
- Uma emissão sem duração apurada conta como entrevista e nunca como tempo. O site escreve "duração não apurada"; não escreve zero nem estima.
- `config/fontes.yml` declara as fontes automáticas: feeds de podcast (com duração) e feeds públicos de YouTube (sem duração, só detetam candidatos).
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
python -m http.server -d docs 8000
```

Antes de ativar uma fonte nova, `python -m ferramentas.descobrir <url>` mostra o que a página anuncia e o que o feed contém.

## Contribuir com uma emissão

Acrescentar uma linha a `config/entrevistas.yml` com os campos obrigatórios (`data`, `canal`, `programa`, `prova`) e, sempre que for possível apurá-la, `duracao_s` em segundos, tal como a página do canal a declara. Procurar a duração primeiro; omitir o campo só quando não existir forma pública de a saber. Se a prova for uma peça de imprensa e não o canal, a linha vai para `config/clipping.yml`. Sem URL de prova a linha é rejeitada pela suite de testes.

## Licenças

A fonte Fredoka em `docs/tipos` está sob a SIL Open Font License, incluída ao lado do ficheiro. A licença do código e dos dados está em `LICENSE`.
