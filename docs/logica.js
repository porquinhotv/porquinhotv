/* Logica pura do site, sem DOM e sem pedidos. Carrega no browser como
   PTV e no Node como modulo, para que os testes em tests/frontend corram
   sem browser. Tudo o que aqui esta e uma funcao de entradas para saidas.

   Regra da casa: o site nao inventa contas. As unicas contas feitas aqui
   sao somas de periodo a partir das reparticoes diarias do resumo.json e
   diferencas de datas. Agregacoes novas vivem em recolha/resumo.py, com
   teste. Nao ha tempo em lado nenhum: desde 2026-09-10 o site conta
   emissoes e entrevistas, nunca minutos. */

(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) { module.exports = fabrica(); }
  else { raiz.PTV = fabrica(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  var DIAS_SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

  function dois(n) { return n < 10 ? "0" + n : String(n); }

  /* Datas ISO sao datas civis. new Date("2024-03-10") e UTC nos browsers e,
     num fuso a oeste, da o dia anterior. Construir sempre com o construtor
     local. Num site cujo assunto e em que dia as coisas aconteceram, isto
     nao e um detalhe. */
  function deIso(iso) {
    var p = iso.split("-").map(Number);
    return new Date(p[0], p[1] - 1, p[2]);
  }

  function paraIso(d) {
    return d.getFullYear() + "-" + dois(d.getMonth() + 1) + "-" + dois(d.getDate());
  }

  function diasEntre(deIsoStr, ateIsoStr) {
    var a = deIso(deIsoStr), b = deIso(ateIsoStr);
    return Math.round((b - a) / 86400000);
  }

  function dataLegivel(iso) {
    var d = deIso(iso);
    return d.getDate() + " de " + MESES[d.getMonth()] + " de " + d.getFullYear();
  }

  function dataComDiaSemana(iso) {
    var d = deIso(iso);
    return DIAS_SEMANA[d.getDay()] + ", " + dataLegivel(iso);
  }

  function inicioDaSemana(d) {
    var c = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var dia = c.getDay();
    c.setDate(c.getDate() + (dia === 0 ? -6 : 1 - dia));
    return c;
  }

  /* Intervalo [de, ate] em ISO para um periodo. `hoje` e uma Date; `desde`
     e o inicio do tema em ISO. */
  function intervalo(periodo, hoje, desde) {
    var de;
    if (periodo === "semana") { de = inicioDaSemana(hoje); }
    else if (periodo === "ano") { de = new Date(hoje.getFullYear(), 0, 1); }
    else if (periodo === "sempre") { de = deIso(desde); }
    else { de = new Date(hoje.getFullYear(), hoje.getMonth(), 1); }
    return { de: paraIso(de), ate: paraIso(hoje) };
  }

  /* Soma de um periodo a partir de por_dia. Entrevistas distintas contam
     pelas chaves de cada dia, por isso um simulcast conta uma vez. */
  function somar(porDia, de, ate) {
    var total = { emissoes: 0, entrevistas: 0 };
    var chaves = {};
    (porDia || []).forEach(function (dia) {
      if (dia.data < de || dia.data > ate) { return; }
      total.emissoes += dia.emissoes;
      (dia.chaves || []).forEach(function (k) { chaves[k] = true; });
    });
    total.entrevistas = Object.keys(chaves).length;
    return total;
  }

  /* Soma por canal num periodo, a partir de canal_por_dia. Devolve um mapa
     canal -> {emissoes}. */
  function somarCanais(canalPorDia, de, ate) {
    var mapa = {};
    (canalPorDia || []).forEach(function (dia) {
      if (dia.data < de || dia.data > ate) { return; }
      Object.keys(dia.canais).forEach(function (id) {
        var c = dia.canais[id];
        var m = mapa[id] || { emissoes: 0 };
        m.emissoes += c.emissoes;
        mapa[id] = m;
      });
    });
    return mapa;
  }

  /* ---- humor -------------------------------------------------------- */

  /* Degrau de uma escada de frases: o primeiro cujo limite ainda cobre o
     valor. O ultimo tem limite nulo e apanha o resto. Serve o humor, por
     dias, e as metricas, por numero de entrevistas. */
  function degrauPara(lista, valor, campo) {
    var chave = campo || "ate";
    for (var i = 0; i < lista.length; i++) {
      var limite = lista[i][chave];
      if (limite === null || limite === undefined || valor <= limite) { return lista[i]; }
    }
    return lista[lista.length - 1];
  }

  function humorPara(dias, textos) {
    return degrauPara(textos.humores, dias, "ate_dias");
  }

  /* Determinista pelo proprio numero, para a frase nao mudar a cada
     refresh e ser a mesma para toda a gente no mesmo dia. */
  function escolherFrase(frases, indice) {
    if (!frases || !frases.length) { return ""; }
    return frases[Math.abs(indice) % frases.length];
  }

  function fraseDeHumor(humor, dias) {
    return preencher(escolherFrase(humor.frases, dias), { dias: dias });
  }

  /* Frase satirica de uma metrica. Devolve "" quando nao ha escada
     configurada: a camada de humor pode faltar, o numero nao. */
  function fraseDeMetrica(escada, n) {
    if (!escada || !escada.length) { return ""; }
    return preencher(escolherFrase(degrauPara(escada, n).frases, n), { n: n });
  }

  function cabecalhoDias(dias, textos) {
    var c = textos.cabecalho;
    if (dias === null) { return c.sem_dados; }
    if (dias === 0) { return c.hoje; }
    if (dias === 1) { return c.um_dia; }
    return c.varios_dias.replace(/\{dias\}/g, String(dias));
  }

  /* ---- textos ------------------------------------------------------- */

  function preencher(template, valores) {
    return template.replace(/\{([a-z_]+)\}/g, function (tudo, chave) {
      return valores[chave] !== undefined ? String(valores[chave]) : tudo;
    });
  }

  return {
    MESES: MESES,
    DIAS_SEMANA: DIAS_SEMANA,
    dois: dois,
    deIso: deIso,
    paraIso: paraIso,
    diasEntre: diasEntre,
    dataLegivel: dataLegivel,
    dataComDiaSemana: dataComDiaSemana,
    inicioDaSemana: inicioDaSemana,
    intervalo: intervalo,
    somar: somar,
    somarCanais: somarCanais,
    degrauPara: degrauPara,
    humorPara: humorPara,
    fraseDeHumor: fraseDeHumor,
    fraseDeMetrica: fraseDeMetrica,
    cabecalhoDias: cabecalhoDias,
    preencher: preencher
  };
});
