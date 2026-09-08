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

test("duracao legivel", () => {
  assert.equal(PTV.duracaoLegivel(30), "menos de um minuto");
  assert.equal(PTV.duracaoLegivel(60), "1 minuto");
  assert.equal(PTV.duracaoLegivel(3600), "1 hora");
  assert.equal(PTV.duracaoLegivel(9660), "2 horas e 41 minutos");
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
  { data: "2026-09-01", emissoes: 2, tempo_s: 3600, sem_duracao: 0, chaves: ["k1"] },
  { data: "2026-09-03", emissoes: 1, tempo_s: 900, sem_duracao: 0, chaves: ["k2"] },
  { data: "2026-09-05", emissoes: 1, tempo_s: 0, sem_duracao: 1, chaves: ["k4"] },
  { data: "2026-09-20", emissoes: 1, tempo_s: 1200, sem_duracao: 0, chaves: ["k3"] },
];

test("somar um periodo conta simulcast como uma entrevista", () => {
  const t = PTV.somar(porDia, "2026-09-01", "2026-09-04");
  assert.deepEqual(t, { emissoes: 3, tempo_s: 4500, entrevistas: 2, sem_duracao: 0 });
});

test("uma emissao sem duracao apurada conta como evento e nao como tempo", () => {
  const t = PTV.somar(porDia, "2026-09-01", "2026-09-10");
  assert.deepEqual(t, { emissoes: 4, tempo_s: 4500, entrevistas: 3, sem_duracao: 1 });
});

test("somar fora do intervalo da zero", () => {
  assert.deepEqual(PTV.somar(porDia, "2027-01-01", "2027-12-31"), { emissoes: 0, tempo_s: 0, entrevistas: 0, sem_duracao: 0 });
});

test("somar canais", () => {
  const cpd = [
    { data: "2026-09-01", canais: { sic: { emissoes: 1, tempo_s: 1800, parciais: 0, sem_duracao: 0 }, "sic-noticias": { emissoes: 1, tempo_s: 1800, parciais: 1, sem_duracao: 0 } } },
    { data: "2026-09-03", canais: { sic: { emissoes: 1, tempo_s: 900, parciais: 0, sem_duracao: 0 } } },
    { data: "2026-09-05", canais: { cmtv: { emissoes: 1, tempo_s: 0, parciais: 0, sem_duracao: 1 } } },
  ];
  const m = PTV.somarCanais(cpd, "2026-09-01", "2026-09-30");
  assert.deepEqual(m.sic, { emissoes: 2, tempo_s: 2700, parciais: 0, sem_duracao: 0 });
  assert.deepEqual(m["sic-noticias"], { emissoes: 1, tempo_s: 1800, parciais: 1, sem_duracao: 0 });
  assert.deepEqual(m.cmtv, { emissoes: 1, tempo_s: 0, parciais: 0, sem_duracao: 1 });
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

test("comparacoes sao uma divisao inteira", () => {
  const futebol = textos.comparacoes.find((c) => c.id === "futebol");
  assert.equal(PTV.comparar(5399, futebol, textos.frases), "nem um jogo de futebol de 90 minutos");
  assert.equal(PTV.comparar(5400, futebol, textos.frases), "um jogo de futebol de 90 minutos");
  assert.equal(PTV.comparar(16200, futebol, textos.frases), "3 jogos de futebol de 90 minutos");
  const voo = textos.comparacoes.find((c) => c.id === "voo");
  assert.equal(PTV.comparar(60000, voo, textos.frases), "cerca de 2 voos Lisboa a Nova Iorque");
});

test("escolha da comparacao da sempre um numero legivel quando existe", () => {
  for (const segundos of [1300, 5400, 36000, 400000, 5000000]) {
    for (let semente = 0; semente < 20; semente++) {
      const c = PTV.escolherComparacao(segundos, textos.comparacoes, semente);
      const n = Math.floor(segundos / c.unidade_s);
      assert.ok(n >= 1 && n < 1000, `segundos=${segundos} semente=${semente} n=${n}`);
    }
  }
  const pequena = PTV.escolherComparacao(10, textos.comparacoes, 3);
  assert.equal(pequena.id, "sesta");
});

test("semente e determinista", () => {
  assert.equal(PTV.sementeDe("rtp1"), PTV.sementeDe("rtp1"));
  assert.notEqual(PTV.sementeDe("rtp1"), PTV.sementeDe("rtp2"));
});
