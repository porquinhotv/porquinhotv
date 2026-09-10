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

const porDia = [
  { data: "2026-09-01", emissoes: 2, entrevistas_distintas: 1, chaves: ["k1"] },
  { data: "2026-09-03", emissoes: 1, entrevistas_distintas: 1, chaves: ["k2"] },
  { data: "2026-09-05", emissoes: 1, entrevistas_distintas: 1, chaves: ["k4"] },
  { data: "2026-09-20", emissoes: 1, entrevistas_distintas: 1, chaves: ["k3"] },
];

test("somar um periodo conta simulcast como uma entrevista", () => {
  const t = PTV.somar(porDia, "2026-09-01", "2026-09-04");
  assert.deepEqual(t, { emissoes: 3, entrevistas: 2 });
});

test("somar um periodo maior", () => {
  const t = PTV.somar(porDia, "2026-09-01", "2026-09-10");
  assert.deepEqual(t, { emissoes: 4, entrevistas: 3 });
});

test("somar fora do intervalo da zero", () => {
  assert.deepEqual(PTV.somar(porDia, "2027-01-01", "2027-12-31"), { emissoes: 0, entrevistas: 0 });
});

test("somar canais", () => {
  const cpd = [
    { data: "2026-09-01", canais: { sic: { emissoes: 1, declaradas: 1 }, "sic-noticias": { emissoes: 1, declaradas: 1 } } },
    { data: "2026-09-03", canais: { sic: { emissoes: 1, declaradas: 1 } } },
    { data: "2026-09-05", canais: { cmtv: { emissoes: 1, declaradas: 0 } } },
  ];
  const m = PTV.somarCanais(cpd, "2026-09-01", "2026-09-30");
  assert.deepEqual(m.sic, { emissoes: 2 });
  assert.deepEqual(m["sic-noticias"], { emissoes: 1 });
  assert.deepEqual(m.cmtv, { emissoes: 1 });
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
