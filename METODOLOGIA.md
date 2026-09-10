# Metodologia

O Porquinho TV conta as entrevistas exclusivas dadas por André Ventura na televisão portuguesa. Este documento explica o que conta, o que não conta, de onde vêm os números e onde é que o método falha. Está escrito para quem quiser contestar um número, e é a única parte do site onde a linguagem é técnica.

## 1. A pergunta

Quantas entrevistas exclusivas deu André Ventura na televisão portuguesa desde a inscrição do partido?

A data de início é 16 de maio de 2019, dia em que o Diário da República publicou o registo do partido (2.ª série, n.º 94). Nada anterior entra, mesmo que exista.

## 2. O que conta

Uma **entrevista exclusiva** é um segmento de programa em que:

1. André Ventura é o único entrevistado;
2. há pelo menos um entrevistador do canal, em formato de pergunta e resposta;
3. o segmento foi emitido num dos nove canais medidos: RTP1, RTP2, SIC, TVI, SIC Notícias, RTP3, CNN Portugal, NOW e CMTV;
4. há prova pública de que aconteceu: a página ou o feed do próprio canal, ou uma peça de imprensa que relate a entrevista, nomeando o canal e fixando o dia. Ver a secção 8.

Programas de entretenimento com uma entrevista a solo contam. Noticiários com uma entrevista em estúdio contam.

**Não se conta o tempo.** Desde 10 de setembro de 2026 o site conta a existência de cada entrevista e não a sua duração: houve, ou foi anunciada, uma entrevista neste canal, neste dia, e há uma página pública que o prova. Ver a secção 5. Nunca houve duração mínima: o que separa uma entrevista de uma declaração é o formato, não o relógio, e um limite de duração deixaria de fora emissões reais só por serem curtas.

**O formato tem de estar provado.** No registo do canal escrito por uma pessoa, a prova é a leitura da página. Nas páginas de canal que a ferramenta colheu sozinha não há leitura humana nenhuma, e por isso vale a regra das fontes automáticas, abaixo. No clipping, desde 9 de setembro de 2026, é a peça cumprir as quatro condições descritas abaixo, verificadas pela ferramenta e confirmáveis por quem abrir a ligação: o texto tem de dizer entrevista, nomear um só canal e fixar o dia. Numa fonte automática, em que ninguém leu a página, o formato só se considera apurado quando o próprio canal lhe chama entrevista: o título contém a palavra, ou o programa é um dos programas de entrevista listados em `config/porquinho.yml`, ou a fonte foi configurada para um programa cujo formato é declarado. Uma peça com o nome no título e com data, mas sem nada que diga que é uma entrevista, não é uma entrevista por omissão: fica na quarentena como `formato_nao_apurado`, à espera de alguém que a leia.

Esta regra foi invertida a 8 de setembro de 2026. Até então bastava não haver termo de exclusão no título, e isso publicou como entrevistas exclusivas sete peças noticiosas curtas, uma delas de 55 segundos. A correção fica registada aqui porque um número que esteve errado e foi corrigido deve poder ser reconstituído por quem o leu antes.

## 3. O que não conta

- **Debates e painéis**: mais de um convidado a responder às mesmas perguntas.
- **Declarações**: perguntas à saída de um evento, reações, respostas a jornalistas em conferência de imprensa.
- **Diretos**: comícios, discursos, sessões parlamentares.
- **Rádio, podcast exclusivo, redes sociais**: só televisão. Um podcast só conta se for a gravação de um segmento emitido em televisão.

O site não lê nem caracteriza o conteúdo das entrevistas. Não avalia perguntas, não classifica respostas, não mede tom nem tempo. Conta emissões.

## 4. A unidade: a emissão

A unidade de contagem é a **emissão**: uma entrevista exclusiva, num canal, num dia. A mesma entrevista emitida em dois canais (por exemplo, em simultâneo na SIC e na SIC Notícias) são **duas emissões**, porque a pergunta que o site responde é em que canais houve entrevistas, e quantas. A repartição por canal e o total somam emissões.

Para quem preferir contar entrevistas e não emissões, o site mostra também **entrevistas distintas**: emissões agrupadas pela chave `entrevista`, que no registo curado é preenchida à mão quando há simulcast ou repetição. Sem chave, cada emissão é a sua própria entrevista. Os dois números aparecem lado a lado quando diferem.

## 5. Porque não há duração

Até 10 de setembro de 2026 o site somava também o tempo das entrevistas, a partir da duração que cada página declarava, e assinalava como não apurada a duração das emissões em que isso não era possível: eram 23 em 51. A duração foi retirada do projeto por decisão do autor, e a razão fica escrita.

O que este site quer responder é se a entrevista existiu, em que canal e em que dia. Uma notícia que diga "em entrevista à CMTV, ontem à noite" responde a isso por inteiro, e nunca responde à duração. Manter o tempo obrigava a tratar como incompleta quase metade das linhas, a distinguir "vídeo integral" de "recorte", e a ler a duração em páginas que muitos canais nem servem a uma máquina. Tudo isso era trabalho e complexidade ao serviço de um número que não é a pergunta.

Consequências, todas visíveis no site: não há totais de tempo, não há comparações de tempo, e a repartição por canal e a evolução são contagens de emissões. Uma peça curta que relate a entrevista prova-a tanto como o vídeo integral. O ficheiro de dados não tem o campo `duracao_s` nem o campo `parcial`, e o coletor recusa uma linha do registo que ainda os traga.

Quem quiser o tempo tem, em cada linha, a ligação para a página onde ele está, quando o canal a publicou.

## 6. Data de emissão

A data que conta é a data de emissão. Quando a fonte a declara (registo curado, sinopse com "emitida a 4 de setembro", data ISO no texto), é essa. Quando não declara, fica a data de publicação, e o registo diz `data_origem: publicacao`. No calendário, um dia com data de publicação aparece só com contorno. A data de publicação fica sempre guardada em `publicado_em`, para que a diferença seja auditável sem voltar à fonte.

Uma data declarada só é aceite se cair entre o dia da publicação e 45 dias antes. Fora dessa janela usa-se a data de publicação.

## 7. Fontes

As fontes têm uma hierarquia, e ela é deliberada: quando duas cobrem a mesma emissão, fica a que está mais acima nesta lista.

**1. Registo do canal** (`config/entrevistas.yml`). Uma linha por emissão, escrita por uma pessoa, com data, canal, programa e um URL da própria página ou do próprio feed do canal. É a fonte principal.

**2. Páginas de canal colhidas pela ferramenta** (`config/paginas_de_canal.yml`). A mesma coisa que a fonte 1, com uma diferença: a página foi lida pela ferramenta e não por uma pessoa. Por isso não tem a dispensa da fonte 1. O formato tem de estar provado pelo título, como em qualquer fonte automática, e a emissão tem de ser vista em duas rondas antes de ser publicada. Uma emissão que o registo escrito por uma pessoa já tenha não se repete aqui. O que esta fonte deixa de fora fica na quarentena com o motivo escrito: sobretudo as emissões que o canal titula com a citação em vez da palavra.

**3. Pesquisa do próprio canal**. É a fonte automática principal. O site do canal é interrogado pela sua própria pesquisa, uma vez por cada forma do nome, e de cada página de resultado recolhem-se os endereços de artigo desse domínio. Cada um é depois lido para extrair o que a página publica em formato normalizado (schema.org, OpenGraph): título, data, sinopse e etiquetas. Não é lida a apresentação da página, apenas estes campos, que os canais mantêm por causa dos motores de busca; é o que faz esta leitura sobreviver a uma remodelação do site em vez de passar a devolver zero em silêncio. Estes itens não entram na hora: ver a secção 8.

**4. Feeds de podcast**. Quando um canal publica um programa como podcast, o feed traz o título e a data de publicação. Um feed que mistura programas é classificado pelo título de cada item.

**5. Clipping de imprensa** (`config/clipping.yml`). Uma peça de imprensa escrita que diga, por palavras, que no dia X houve uma entrevista a André Ventura no canal Y é prova de que a emissão aconteceu, e de quando. Vale o mesmo que a página do canal: desde 10 de setembro de 2026 não há prova de primeira e prova de segunda, porque o que faz uma entrevista contar é existir uma prova pública que qualquer pessoa abre, e onde ela está hospedada não muda a sua credibilidade. O site marca estas emissões com a origem "imprensa", com a ligação para a peça, porque é um facto sobre a linha e não um aviso sobre a sua qualidade. Para contar, a peça tem de cumprir quatro condições que qualquer leitor verifica ao abri-la: nomeia o canal (não "a televisão"); diz entrevista, e não debate nem declarações; fixa o dia da emissão, que não é necessariamente o dia da peça; e relata a entrevista ("esteve ontem") ou anuncia-a com o dia fixado ("dá hoje entrevista às 19h"). Até 9 de setembro de 2026 só o relato contava; desde então contam as duas, porque uma entrevista anunciada a um canal raramente se cancela ou adia. Quando a prova é um anúncio, a data da peça (`publicado_em`, no ficheiro de dados publicado) é anterior à data da emissão. Várias peças sobre a mesma emissão contam uma vez: fica a publicada mais perto do dia, e um relato ganha a um anúncio.

Uma peça cuja página não se conseguiu ler não conta, mesmo que o título que o índice lhe deu pareça cumprir as condições: seria afirmar uma coisa sobre um texto que ninguém abriu. Fica assinalada como por ler, à espera de quem a abra.

Desde 9 de setembro de 2026 estas quatro condições são verificadas pela ferramenta e não por uma pessoa, e é essa verificação que decide se a peça conta. O que uma pessoa faz é vetar: pode retirar uma linha, nunca acrescentar uma que as condições rejeitem. A troca é assumida e tem um custo que se diz aqui: uma peça que engane as quatro condições passa a inflacionar uma contagem, em vez de ficar por decidir. Em contrapartida, a página de Fontes mostra a origem e a ligação de cada linha, e a repartição entre provas do canal e da imprensa é publicada, para que qualquer leitor refaça a verificação.

Até 8 de setembro de 2026 esta fonte era o último recurso, reservada ao que o canal não tinha publicado. Deixou de ser, por uma razão verificada nesse dia: seis dos nove canais não respondem a uma máquina, e os que respondem titulam as peças com a citação e deixam a palavra "entrevista" para o corpo do texto, que os índices não trazem. Com a regra antiga, das treze entrevistas da CMTV encontradas nesse dia por pesquisa direta, o registo tinha uma. A imprensa é muitas vezes o único rasto público de que a entrevista existiu. A repartição entre provas do canal e provas da imprensa é publicada na página de Fontes. Quando o canal e a imprensa provam a mesma emissão, há uma emissão e não duas: fica a do canal, por ser a que corre primeiro, e não por valer mais.

**6. Feeds públicos de YouTube**. Dizem que saiu um vídeo com o nome no título e a data de publicação. Passam pelo critério como qualquer fonte automática: o título tem de provar o formato e o bloco tem de ser visto em rondas distintas. Os que não dizem que são uma entrevista ficam na quarentena como `formato_nao_apurado`.

**Uma fonte que foi testada e recusada.** O arquivo da web portuguesa foi ensaiado como fonte para o histórico e devolveu zero resultados para o nome do sujeito no domínio de um canal generalista ao longo de sete anos, o que foi confirmado à mão. Uma fonte que devolve zero onde tem de haver resultados não é uma fonte, e não é usada. Fica registado aqui porque saber o que foi tentado e recusado faz parte do método.

**Motor de busca externo, como índice e nunca como prova.** A pesquisa do próprio canal é a primeira escolha, mas em cinco dos nove canais não serve: dois recusam pedidos automáticos, dois montam os resultados por JavaScript e não os põem na página que o servidor envia, e um não tem pesquisa. Para esses, a consulta passa por um motor de busca externo, restringida ao domínio do canal.

O motor é um índice para chegar à página do canal, e mais nada. A prova de cada linha continua a ser o endereço do canal, que é lido e medido como qualquer outro; nenhum número vem do motor, e uma página que o motor devolva mas que não passe no critério fica na quarentena como todas as outras. Não é exigida conta nem chave.

De dez motores ensaiados em 8 de setembro de 2026, um respondeu com resultados utilizáveis a partir da máquina que corre a recolha. Os outros recusaram o pedido ou devolveram páginas sem resultados. Depender de um serviço que nos pode fechar a porta é uma fragilidade real deste método, e fica dita: se esse motor deixar de responder, os canais que dependem dele deixam de ser cobertos, e isso aparecerá como ausência de emissões novas, não como zero emissões.

A repartição entre o que vem do canal e o que vem da imprensa é publicada, porque é uma medida da qualidade da própria cobertura.

Nenhuma fonte exige conta, chave ou credencial de terceiros.

## 8. O que fica de fora, e onde se vê

Nada é descartado em silêncio. Todo o item que uma fonte devolveu e que não entrou está em `dados/quarentena.json` com o motivo:

| Motivo | Significado |
|---|---|
| `sem_data` | a página não declara data nenhuma; sem dia não há emissão |
| `anterior_ao_inicio` | antes de 16 de maio de 2019 |
| `sem_sujeito` | o nome não aparece no título nem na descrição |
| `formato_nao_elegivel (x)` | debate, declaração, direto ou outro formato |
| `formato_nao_apurado` | fonte automática em que nem o título nem o programa dizem que é uma entrevista; não é rejeição do formato, é a ausência dele |
| `canal_desconhecido` | canal que não é um dos nove |
| `aguarda_confirmacao (n de m)` | visto por fonte automática, ainda sem as rondas necessárias |
| `fragmento_ou_repetido` | outro item do mesmo bloco (canal, programa, dia) já provou a emissão |
| `ja_registado` | o registo curado já tem esta prova |

A quarentena é uma fotografia da última recolha, não um histórico.

### Confirmação em rondas

Há mais do que uma emissão por dia no mesmo canal com frequência: uma entrevista de manhã num programa de entretenimento e outra à noite num noticiário são duas emissões, e contam as duas. O que as separa é o nome do programa, que entra na chave. Quando o programa não é possível apurar em nenhuma das duas, elas partilham a chave e uma é tratada como excerto da outra: a contagem fica curta, nunca inflacionada, e a quarentena diz que foi isso que aconteceu.

Uma emissão vinda de fonte automática não entra no dataset na primeira vez que é vista. Fica registada como candidata e só entra depois de o mesmo bloco (canal, programa, dia) ser encontrado em rondas distintas de recolha. O registo de avistamentos está em `dados/candidatos.json`, é append-only, e ao lado de cada linha publicada ficam dois números: em quantas rondas foi vista e por quantas fontes distintas.

As rondas da reconstrução do histórico correm seguidas, numa só operação. Na recolha de todos os dias, a segunda ronda corre no mesmo dia, minutos depois da primeira, e só quando a primeira encontrou alguma coisa à espera de confirmação. Assim uma entrevista da noite anterior é publicada na manhã seguinte e não no dia a seguir a essa; nos dias em que não há nada, não há segunda leitura e não se incomodam os servidores de ninguém.

Uma segunda leitura minutos depois da primeira apanha menos do que uma leitura no dia seguinte: um site que sirva uma página defeituosa a manhã inteira engana as duas. É o preço de publicar no próprio dia, e fica dito aqui em vez de ficar escondido.

O que isto protege, e o que não protege, dito sem enfeite:

**Protege** de um erro passageiro da recolha. Uma página que veio truncada, um campo malformado nesse dia, uma pesquisa que devolveu lixo por causa de uma remodelação a meio: qualquer destes injetaria uma emissão falsa numa recolha de leitura única. Exigir que o mesmo bloco reapareça noutra corrida elimina esta classe de erro.

**Não protege** de a fonte estar errada. Se a página do canal disser o que não é, dirá o mesmo em todas as rondas. Ler a mesma fonte mais vezes não a torna mais verdadeira. O que aumenta mesmo a fiabilidade é a corroboração por fontes diferentes, e é por isso que o número de fontes distintas é publicado ao lado do número de rondas: são coisas diferentes e o site não as confunde.

## 9. Fragmentos e prova repetida

Um canal publica muitas vezes a mesma entrevista como vídeo integral e vários recortes, e a imprensa noticia a mesma entrevista que o canal publicou. Para não contar quatro entrevistas onde houve uma, cada **bloco** (canal, programa, dia) fica com uma só emissão: a que vier da fonte mais acima na hierarquia da secção 7. Até 10 de setembro de 2026 a duração desempatava primeiro (a mais longa ganhava ao recorte); sem duração, a ordem das fontes é o único critério, e está escrita em `config/fontes.yml`.

As outras vão para a quarentena, e continuam visíveis lá. Canais diferentes são blocos diferentes, por isso o simulcast não é afetado por esta regra.

## 10. Períodos

O site mostra semana (de segunda a hoje), mês, ano e desde sempre. As somas de período são feitas no browser a partir das repartições diárias já agregadas. É a única conta feita no browser, e é uma soma.

Semanas na evolução seguem a norma ISO 8601 (começam à segunda, a semana 1 é a que contém a primeira quinta-feira do ano).

## 11. Humor

As frases do porquinho são uma camada sobre os números, não um número. O humor depende só de uma coisa: quantos dias passaram desde a última emissão registada. As frases falam do porquinho e dos dias. Não falam de ninguém. As comparações de tempo ("dava para três jogos de futebol") saíram com a duração.

## 12. Limitações

- **Cobertura.** Os registos dependem de trabalho humano e do que os canais e a imprensa publicaram online. Uma entrevista emitida e nunca noticiada nem publicada não deixa rasto e não entra. Os números são um limite inferior.
- **Histórico.** Os anos anteriores ao início do site foram reconstruídos a partir de fontes online. A cobertura desses anos é a que foi possível encontrar e provar, e comparar 2020 com 2026 compara também a qualidade dos arquivos dos canais e da imprensa, não só a antena. A página de Fontes mostra exatamente o que está contado e de onde veio.
- **Clipping.** Uma peça de imprensa prova que houve entrevista e em que dia, não o formato exato, e herda os erros do jornalista: o canal do grupo trocado (SIC por SIC Notícias, TVI por CNN Portugal), o dia deslocado quando a peça sai no dia seguinte, e "entrevista" usada com largueza. Por isso é sempre identificada como tal, a data da peça fica registada quando é outra, e nunca desloca um registo do próprio canal. A contagem de emissões com prova de imprensa está na página de Fontes, para que se saiba quantas linhas assentam neste tipo de prova.
- **Critério de formato.** A fronteira entre entrevista e declaração longa é uma decisão editorial, e sem limite de duração é uma leitura do formato, feita por uma pessoa, caso a caso. O registo mostra sempre a prova, para que essa leitura possa ser contestada linha a linha. Nas fontes automáticas a leitura é substituída pela palavra do canal: o que o canal não chamou entrevista fica de fora, mesmo que o seja. É um erro por defeito, assumido: neste site é preferível ficar curto e dizê-lo a inflacionar.

## 13. Correções

Erros factuais são corrigidos e a correção fica visível no histórico do repositório. Os ficheiros de dados são escritos com chaves ordenadas para que cada alteração seja legível no diff. Nenhum registo perde a data em que entrou pela primeira vez (`primeira_vez`). Nunca se reescreve o histórico para esconder um erro.

## 14. Verificar

- `dados/emissoes.json`: todas as emissões, com prova.
- `dados/quarentena.json`: o que ficou de fora na última recolha, e porquê.
- `dados/resumo.json`: os agregados que o site mostra.
- `config/porquinho.yml`, `config/fontes.yml`: o critério e as fontes.
- `config/entrevistas.yml` e `config/clipping.yml`: os registos, linha a linha, com a prova de cada um.
- `recolha/criterio.py`: o código que aplica o critério, curto de propósito.

Quem discordar de uma linha tem tudo o que precisa para dizer qual e porquê.
