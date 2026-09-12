// Testes da logica pura do site. Correr: node --test tests/frontend
// Sem browser, sem dependencias. O que aqui se testa e o que o site
// afirma no ecra a partir do resumo.json e do textos.json.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PTV = require("../../docs/logica.js");
const textos = JSON.parse(fs.readFileSync(path.join(__dirname, "../../docs/textos.json"), "utf8"));

test("datas ISO sao construidas como datas locais", () => {
  const d = PTV.deIso("2024-03-10");
  assert.equal(d.getDate(), 10);
  assert.equal(d.getMonth(), 2);
  assert.equal(PTV.paraIso(d), "2024-03-10");
});

test("dias entre datas", () => {
  assert.equal(PTV.diasEntre("2026-09-01", "2026-09-07"), 6);
  assert.equal(PTV.diasEntre("2026-09-07", "2026-09-07"), 0);
  assert.equal(PTV.diasEntre("2025-12-31", "2026-01-01"), 1);
});

test("o site nao tem funcoes de tempo", () => {
  // Sairam a 2026-09-10 com a duracao. Se voltarem, e porque alguem
  // reintroduziu tempo num site que so conta existencias.
  for (const nome of ["duracaoLegivel", "comparar", "escolherComparacao", "sementeDe"]) {
    assert.equal(PTV[nome], undefined, nome);
  }
});

test("intervalo de periodos", () => {
  const hoje = new Date(2026, 8, 9); // quarta, 9 de setembro de 2026
  assert.deepEqual(PTV.intervalo("semana", hoje, "2019-05-16"), { de: "2026-09-07", ate: "2026-09-09" });
  assert.deepEqual(PTV.intervalo("mes", hoje, "2019-05-16"), { de: "2026-09-01", ate: "2026-09-09" });
  assert.deepEqual(PTV.intervalo("ano", hoje, "2019-05-16"), { de: "2026-01-01", ate: "2026-09-09" });
  assert.deepEqual(PTV.intervalo("sempre", hoje, "2019-05-16"), { de: "2019-05-16", ate: "2026-09-09" });
  const domingo = new Date(2026, 8, 13);
  assert.equal(PTV.intervalo("semana", domingo, "2019-05-16").de, "2026-09-07");
});

/* Cada entrada do resumo e uma entrevista desde 2026-09-11, por isso a
   soma de um periodo e uma soma. Ate essa data cada dia trazia tambem a
   lista das chaves de entrevista e esta funcao unia-as para nao contar
   duas vezes um simulcast. */
const porDia = [
  { data: "2026-09-01", entrevistas: 2 },
  { data: "2026-09-03", entrevistas: 1 },
  { data: "2026-09-05", entrevistas: 1 },
  { data: "2026-09-20", entrevistas: 1 },
];

test("somar um periodo", () => {
  const t = PTV.somar(porDia, "2026-09-01", "2026-09-04");
  assert.deepEqual(t, { entrevistas: 3 });
});

test("somar um periodo maior", () => {
  const t = PTV.somar(porDia, "2026-09-01", "2026-09-10");
  assert.deepEqual(t, { entrevistas: 4 });
});

test("somar fora do intervalo da zero", () => {
  assert.deepEqual(PTV.somar(porDia, "2027-01-01", "2027-12-31"), { entrevistas: 0 });
});

test("somar canais", () => {
  const cpd = [
    { data: "2026-09-01", canais: { sic: { entrevistas: 1, declaradas: 1 }, "sic-noticias": { entrevistas: 1, declaradas: 1 } } },
    { data: "2026-09-03", canais: { sic: { entrevistas: 1, declaradas: 1 } } },
    { data: "2026-09-05", canais: { cmtv: { entrevistas: 1, declaradas: 0 } } },
  ];
  const m = PTV.somarCanais(cpd, "2026-09-01", "2026-09-30");
  assert.deepEqual(m.sic, { entrevistas: 2 });
  assert.deepEqual(m["sic-noticias"], { entrevistas: 1 });
  assert.deepEqual(m.cmtv, { entrevistas: 1 });
});

/* O numero que o site escreve em grande e a soma dos numeros por canal
   tem de ser o mesmo. Enquanto a unidade era a emissao, a reparticao por
   canal somava mais do que o total sempre que houvesse simulcast, e o
   site tinha de escrever dois numeros para o explicar. */
test("a soma por canal fecha no total do periodo", () => {
  const dias = [
    { data: "2026-09-01", entrevistas: 2 },
    { data: "2026-09-02", entrevistas: 1 },
  ];
  const cpd = [
    { data: "2026-09-01", canais: { sic: { entrevistas: 1, declaradas: 1 }, cmtv: { entrevistas: 1, declaradas: 1 } } },
    { data: "2026-09-02", canais: { tvi: { entrevistas: 1, declaradas: 1 } } },
  ];
  const total = PTV.somar(dias, "2026-09-01", "2026-09-30").entrevistas;
  const mapa = PTV.somarCanais(cpd, "2026-09-01", "2026-09-30");
  const porCanal = Object.keys(mapa).reduce((n, id) => n + mapa[id].entrevistas, 0);
  assert.equal(porCanal, total);
});

test("humor nos limites", () => {
  assert.equal(PTV.humorPara(0, textos).id, "euforico");
  assert.equal(PTV.humorPara(1, textos).id, "euforico");
  assert.equal(PTV.humorPara(2, textos).id, "contente");
  assert.equal(PTV.humorPara(3, textos).id, "contente");
  assert.equal(PTV.humorPara(4, textos).id, "triste");
  assert.equal(PTV.humorPara(6, textos).id, "triste");
  assert.equal(PTV.humorPara(7, textos).id, "deprimido");
  assert.equal(PTV.humorPara(13, textos).id, "deprimido");
  assert.equal(PTV.humorPara(14, textos).id, "hibernacao");
  assert.equal(PTV.humorPara(400, textos).id, "hibernacao");
});

test("nenhuma frase fica com placeholder por preencher", () => {
  for (let dias = 0; dias <= 40; dias++) {
    const h = PTV.humorPara(dias, textos);
    const f = PTV.fraseDeHumor(h, dias);
    assert.doesNotMatch(f, /\{[a-z_]+\}/, `dias=${dias}: ${f}`);
    assert.doesNotMatch(PTV.cabecalhoDias(dias, textos), /\{[a-z_]+\}/);
  }
  assert.equal(PTV.cabecalhoDias(null, textos), textos.cabecalho.sem_dados);
  assert.equal(PTV.cabecalhoDias(0, textos), textos.cabecalho.hoje);
  assert.match(PTV.cabecalhoDias(5, textos), /5 dias/);
});

test("os textos nao trazem comparacoes de tempo", () => {
  assert.equal(textos.comparacoes, undefined);
  assert.equal(textos.frases, undefined);
});

test("a escada das metricas cobre qualquer numero e nao deixa placeholder", () => {
  // Um degrau em falta ou um placeholder a mais escrevia "{n}" no ecra,
  // que e exactamente o que a validacao do gerador tenta impedir.
  for (let n = 0; n <= 200; n++) {
    const f = PTV.fraseDeMetrica(textos.metricas.total, n, textos.metricas.temporada);
    assert.notEqual(f, "", `n=${n}`);
    assert.doesNotMatch(f, /\{[a-z_]+\}/, `n=${n}: ${f}`);
  }
  // Sem camada de humor o site desenha os numeros na mesma.
  assert.equal(PTV.fraseDeMetrica([], 3), "");
  assert.equal(PTV.fraseDeMetrica(undefined, 3), "");
});

test("o ordinal da temporada sai da contagem e nao do texto da frase", () => {
  // A frase dizia "ja ia na terceira temporada" com o ordinal escrito a
  // mao. Com as 59 entrevistas publicadas a 2026-09-12 isso era falso, e
  // o separador "Este ano" mostrava a mesma frase a partir das 11.
  const t = textos.metricas.temporada;
  assert.equal(PTV.temporadaDe(t, 59), "quinta");
  assert.equal(PTV.temporadaDe(t, 48), "quarta");
  assert.equal(PTV.temporadaDe(t, 49), "quinta");
  assert.equal(PTV.temporadaDe(t, 60), "quinta");
  assert.equal(PTV.temporadaDe(t, 61), "sexta");
  // Abaixo da segunda temporada e acima da ultima configurada nao ha
  // ordinal nenhum, e e isso que impede o site de inventar um numero.
  assert.equal(PTV.temporadaDe(t, 11), "");
  assert.equal(PTV.temporadaDe(t, 12 * 12 + 1), "");
  assert.equal(PTV.temporadaDe(undefined, 59), "");
});

test("uma frase sem ordinal disponivel cede o lugar a outra do mesmo degrau", () => {
  // Sem esta cedencia a frase saia com o ordinal vazio, que e a mesma
  // classe de defeito que ela veio corrigir.
  const m = textos.metricas;
  assert.match(PTV.fraseDeMetrica(m.total, 59, m.temporada), /quinta temporada/);
  for (const n of [11, 14, 12 * 12 + 2]) {
    const f = PTV.fraseDeMetrica(m.total, n, m.temporada);
    const ordinal = PTV.temporadaDe(m.temporada, n);
    if (!ordinal) { assert.doesNotMatch(f, / temporada/, `n=${n}: ${f}`); }
  }
});

test("a frase do canal lider preenche o nome e a percentagem", () => {
  const f = PTV.preencher(textos.metricas.lider, { canal: "Canal A", n: 42 });
  assert.match(f, /Canal A/);
  assert.match(f, /42/);
  assert.doesNotMatch(f, /\{[a-z_]+\}/);
});
