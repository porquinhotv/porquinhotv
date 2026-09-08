# Metodologia

O Porquinho TV conta as entrevistas exclusivas dadas por André Ventura na televisão portuguesa e o tempo que ocuparam. Este documento explica o que conta, o que não conta, de onde vêm os números e onde é que o método falha. Está escrito para quem quiser contestar um número, e é a única parte do site onde a linguagem é técnica.

## 1. A pergunta

Quantas entrevistas exclusivas deu André Ventura na televisão portuguesa desde a inscrição do partido, e quanto tempo ocuparam?

A data de início é 16 de maio de 2019, dia em que o Diário da República publicou o registo do partido (2.ª série, n.º 94). Nada anterior entra, mesmo que exista.

## 2. O que conta

Uma **entrevista exclusiva** é um segmento de programa em que:

1. André Ventura é o único entrevistado;
2. há pelo menos um entrevistador do canal, em formato de pergunta e resposta;
3. o segmento foi emitido num dos nove canais medidos: RTP1, RTP2, SIC, TVI, SIC Notícias, RTP3, CNN Portugal, NOW e CMTV;
4. há prova pública de que aconteceu: a página ou o feed do próprio canal, ou, em último recurso, uma peça de imprensa que o relate. Ver a secção 8.

Programas de entretenimento com uma entrevista a solo contam. Noticiários com uma entrevista em estúdio contam.

**Não há duração mínima.** O que separa uma entrevista de uma declaração é o formato, não o relógio: uma entrevista de oito minutos é uma entrevista, e um limite de duração deixaria de fora emissões reais só por serem curtas, o que deturparia a contagem em vez de a proteger.

## 3. O que não conta

- **Debates e painéis**: mais de um convidado a responder às mesmas perguntas.
- **Declarações**: perguntas à saída de um evento, reações, respostas a jornalistas em conferência de imprensa.
- **Diretos**: comícios, discursos, sessões parlamentares.
- **Rádio, podcast exclusivo, redes sociais**: só televisão. Um podcast só conta se for a gravação de um segmento emitido em televisão.

O site não lê nem caracteriza o conteúdo das entrevistas. Não avalia perguntas, não classifica respostas, não mede tom. Mede tempo.

## 4. A unidade: a emissão

A unidade de contagem é a **emissão**: uma entrevista exclusiva, num canal, num dia. A mesma entrevista emitida em dois canais (por exemplo, em simultâneo na SIC e na SIC Notícias) são **duas emissões**, porque a pergunta que o site responde é quanto tempo de antena houve, canal a canal. A repartição por canal e o total somam emissões.

Para quem preferir contar entrevistas e não emissões, o site mostra também **entrevistas distintas**: emissões agrupadas pela chave `entrevista`, que no registo curado é preenchida à mão quando há simulcast ou repetição. Sem chave, cada emissão é a sua própria entrevista. Os dois números aparecem lado a lado quando diferem.

## 5. Tempo

O tempo de uma emissão é a duração declarada pela fonte, em segundos, sem arredondar. Nunca é medido a cronómetro, estimado ou interpolado.

Com um só entrevistado não há rateio a fazer: tempo de emissão e tempo da pessoa são a mesma coisa.

## 6. Quando a duração não se apura

A duração é procurada sempre, e é procurada primeiro. Só quando não existe forma pública de a apurar é que a emissão entra sem ela: fica com `duracao_s` a nulo, conta como **entrevista** e **nunca** conta no tempo.

O site nunca escreve zero nem preenche a lacuna com uma estimativa. Escreve "duração não apurada" ao lado da emissão, e diz em cada período quantas emissões estão nessa situação. Um total de tempo neste site é sempre o tempo das emissões cuja duração foi apurada, e a contagem de emissões é sempre maior ou igual ao que esse tempo representa.

A razão de as contar mesmo assim: uma entrevista provada que não entrasse por falta de duração desapareceria da contagem de entrevistas, que é a pergunta principal do site. Perder o evento para proteger o tempo seria trocar um erro grande por um pequeno.

## 7. Duração incompleta

Caso diferente do anterior. Quando uma entrevista foi emitida mas o canal só publicou recortes, a emissão entra com a soma do que existe e fica marcada como **parcial**: há um tempo apurado, mas sabe-se que é inferior ao real. O site diz quantas emissões estão nessa situação em cada período e avisa que o tempo real é maior. O número publicado é um limite inferior declarado, nunca uma adivinha.

## 8. Data de emissão

A data que conta é a data de emissão. Quando a fonte a declara (registo curado, sinopse com "emitida a 4 de setembro", data ISO no texto), é essa. Quando não declara, fica a data de publicação, e o registo diz `data_origem: publicacao`. No calendário, um dia com data de publicação aparece só com contorno. A data de publicação fica sempre guardada em `publicado_em`, para que a diferença seja auditável sem voltar à fonte.

Uma data declarada só é aceite se cair entre o dia da publicação e 45 dias antes. Fora dessa janela usa-se a data de publicação.

## 9. Fontes

As fontes têm uma hierarquia, e ela é deliberada: quando duas cobrem a mesma emissão, fica a que está mais acima nesta lista.

**1. Registo do canal** (`config/entrevistas.yml`). Uma linha por emissão, escrita por uma pessoa, com data, canal, programa, um URL da própria página ou do próprio feed do canal e, sempre que exista, a duração declarada. É a fonte principal.

**2. Pesquisa do próprio canal**. É a fonte automática principal. O site do canal é interrogado pela sua própria pesquisa, uma vez por cada forma do nome, e de cada página de resultado recolhem-se os endereços de artigo desse domínio. Cada um é depois lido para extrair o que a página publica em formato normalizado (schema.org, OpenGraph): título, data e, quando existe, a duração declarada. Não é lida a apresentação da página, apenas estes campos, que os canais mantêm por causa dos motores de busca; é o que faz esta leitura sobreviver a uma remodelação do site em vez de passar a devolver zero em silêncio. Estes itens não entram na hora: ver a secção 10.

**3. Feeds de podcast**. Quando um canal publica um programa como podcast, o feed traz a duração e a data de publicação. Um feed que mistura programas é classificado pelo título de cada item.

**4. Clipping de imprensa** (`config/clipping.yml`). Último recurso, para emissões que o canal nunca publicou ou já retirou. Uma peça de imprensa escrita que diga, por palavras, que no dia X houve uma entrevista exclusiva a André Ventura no canal Y é prova de que a emissão aconteceu. Não é prova do seu conteúdo nem, quase nunca, da sua duração: por isso estas emissões entram muitas vezes sem duração apurada, e o site marca-as sempre com a origem "imprensa", com a ligação para a peça. Uma peça que apenas cite declarações não serve: tem de relatar uma entrevista.

**Detetores: feeds públicos de YouTube**. Dizem que saiu um vídeo com o nome no título, e mais nada. Nunca entram no dataset por esta via, mesmo agora que uma emissão pode entrar sem duração: numa fonte automática, a falta de duração significa "ainda não verificado", não "sem duração". Vão para a quarentena como `por_confirmar`, com o URL.

**Uma fonte que foi testada e recusada.** O arquivo da web portuguesa foi ensaiado como fonte para o histórico e devolveu zero resultados para o nome do sujeito no domínio de um canal generalista ao longo de sete anos, o que foi confirmado à mão. Uma fonte que devolve zero onde tem de haver resultados não é uma fonte, e não é usada. Fica registado aqui porque saber o que foi tentado e recusado faz parte do método.

**Motores de busca externos não são usados.** Não por preferência, mas porque respondem a pedidos automáticos com muro de consentimento ou verificação, o que faria da recolha uma coisa que funciona uma vez. A pesquisa do próprio canal é além disso a fonte primária, que é o que esta Metodologia manda procurar primeiro.

A repartição entre o que vem do canal e o que vem da imprensa é publicada, porque é uma medida da qualidade da própria cobertura.

Nenhuma fonte exige conta, chave ou credencial de terceiros.

## 10. O que fica de fora, e onde se vê

Nada é descartado em silêncio. Todo o item que uma fonte devolveu e que não entrou está em `dados/quarentena.json` com o motivo:

| Motivo | Significado |
|---|---|
| `sem_data` | a página não declara data nenhuma; sem dia não há emissão |
| `anterior_ao_inicio` | antes de 16 de maio de 2019 |
| `sem_sujeito` | o nome não aparece no título nem na descrição |
| `formato_nao_elegivel (x)` | debate, declaração, direto ou outro formato |
| `canal_desconhecido` | canal que não é um dos nove |
| `por_confirmar` | fonte automática sem duração; é um candidato a verificação humana |
| `aguarda_confirmacao (n de m)` | visto por fonte automática, ainda sem as rondas necessárias |
| `fragmento_ou_repetido` | outro item do mesmo bloco (canal, programa, dia) tem melhor prova |
| `ja_registado` | o registo curado já tem esta prova |

A quarentena é uma fotografia da última recolha, não um histórico.

### Confirmação em rondas

Uma emissão vinda de fonte automática não entra no dataset na primeira vez que é vista. Fica registada como candidata e só entra depois de o mesmo bloco (canal, programa, dia) ser encontrado em rondas distintas de recolha. O registo de avistamentos está em `dados/candidatos.json`, é append-only, e ao lado de cada linha publicada ficam dois números: em quantas rondas foi vista e por quantas fontes distintas.

O que isto protege, e o que não protege, dito sem enfeite:

**Protege** de um erro passageiro da recolha. Uma página que veio truncada, um campo malformado nesse dia, uma pesquisa que devolveu lixo por causa de uma remodelação a meio: qualquer destes injetaria uma emissão falsa numa recolha de leitura única. Exigir que o mesmo bloco reapareça noutra corrida elimina esta classe de erro.

**Não protege** de a fonte estar errada. Se a página do canal disser o que não é, dirá o mesmo em todas as rondas. Ler a mesma fonte mais vezes não a torna mais verdadeira. O que aumenta mesmo a fiabilidade é a corroboração por fontes diferentes, e é por isso que o número de fontes distintas é publicado ao lado do número de rondas: são coisas diferentes e o site não as confunde.

## 11. Fragmentos e prova repetida

Um canal publica muitas vezes a mesma entrevista como vídeo integral e vários recortes, e a imprensa noticia a mesma entrevista que o canal publicou. Para não contar quatro entrevistas onde houve uma, cada **bloco** (canal, programa, dia) fica com uma só emissão, pela seguinte ordem:

1. uma emissão com duração apurada ganha sempre a uma sem duração apurada;
2. entre duas com duração, fica a mais longa, porque a curta é tipicamente um recorte da longa;
3. entre duas sem duração, fica a que vier da fonte mais acima na hierarquia da secção 9.

As outras vão para a quarentena, e continuam visíveis lá. Canais diferentes são blocos diferentes, por isso o simulcast não é afetado por esta regra.

## 12. Períodos

O site mostra semana (de segunda a hoje), mês, ano e desde sempre. As somas de período são feitas no browser a partir das repartições diárias já agregadas. É a única conta feita no browser, e é uma soma.

Semanas na evolução seguem a norma ISO 8601 (começam à segunda, a semana 1 é a que contém a primeira quinta-feira do ano).

## 13. Comparações e humor

As frases do porquinho e as comparações ("dava para três jogos de futebol") são uma camada sobre os números, não um número. Cada comparação é uma divisão inteira do tempo medido por uma duração de referência. As referências são por definição (um jogo de futebol tem 90 minutos) ou aproximadas e assinaladas como tal ("cerca de"). A lista completa, com a nota de onde vem cada referência, está em `config/comparacoes.yml`.

O humor do porquinho depende só de uma coisa: quantos dias passaram desde a última emissão registada. As frases falam do porquinho e do tempo. Não falam de ninguém.

## 14. Limitações

- **Cobertura.** Os registos dependem de trabalho humano e do que os canais e a imprensa publicaram online. Uma entrevista emitida e nunca noticiada nem publicada não deixa rasto e não entra. Os números são um limite inferior.
- **Histórico.** Os anos anteriores ao início do site foram reconstruídos a partir de fontes online. A cobertura desses anos é a que foi possível encontrar e provar, e é onde há mais emissões sem duração apurada. A página de Fontes mostra exatamente o que está contado e de onde veio.
- **Tempo por período.** Como há emissões sem duração apurada, o tempo publicado num período é o tempo das emissões apuradas nesse período. Comparar o tempo de 2020 com o de 2026 compara também a qualidade dos arquivos dos canais, não só a antena. A contagem de entrevistas é a comparação mais segura entre anos.
- **Clipping.** Uma peça de imprensa prova que houve entrevista, não a duração nem o formato exato. É por isso o último recurso, é sempre identificada como tal, e nunca desloca um registo do próprio canal.
- **Duração online e duração em antena.** A duração declarada pelo canal na sua página pode diferir por segundos da duração em antena (genéricos, cortes). Usa-se a declarada porque é a única verificável por terceiros.
- **Critério de formato.** A fronteira entre entrevista e declaração longa é uma decisão editorial, e sem limite de duração é uma leitura do formato, feita por uma pessoa, caso a caso. O registo mostra sempre a prova, para que essa leitura possa ser contestada linha a linha.

## 15. Correções

Erros factuais são corrigidos e a correção fica visível no histórico do repositório. Os ficheiros de dados são escritos com chaves ordenadas para que cada alteração seja legível no diff. Nenhum registo perde a data em que entrou pela primeira vez (`primeira_vez`). Nunca se reescreve o histórico para esconder um erro.

## 16. Verificar

- `dados/emissoes.json`: todas as emissões, com prova.
- `dados/quarentena.json`: o que ficou de fora na última recolha, e porquê.
- `dados/resumo.json`: os agregados que o site mostra.
- `config/porquinho.yml`, `config/fontes.yml`: o critério e as fontes.
- `config/entrevistas.yml` e `config/clipping.yml`: os registos, linha a linha, com a prova de cada um.
- `recolha/criterio.py`: o código que aplica o critério, curto de propósito.

Quem discordar de uma linha tem tudo o que precisa para dizer qual e porquê.
