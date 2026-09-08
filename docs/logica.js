/* Logica pura do site, sem DOM e sem pedidos. Carrega no browser como
   PTV e no Node como modulo, para que os testes em tests/frontend corram
   sem browser. Tudo o que aqui esta e uma funcao de entradas para saidas.

   Regra da casa: o site nao inventa contas. As unicas contas feitas aqui
   sao somas de periodo a partir das reparticoes diarias do resumo.json,
   diferencas de datas, e a divisao das comparacoes. Agregacoes novas
   vivem em recolha/resumo.py, com teste. */

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

  function duracaoLegivel(segundos) {
    var s = Math.max(0, Math.round(segundos || 0));
    if (s < 60) { return "menos de um minuto"; }
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    var horas = h === 1 ? "1 hora" : h + " horas";
    var minutos = m === 1 ? "1 minuto" : m + " minutos";
    if (h === 0) { return minutos; }
    if (m === 0) { return horas; }
    return horas + " e " + minutos;
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
     pelas chaves de cada dia, por isso um simulcast conta uma vez.
     `sem_duracao` sao emissoes provadas cuja duracao nao foi apurada:
     entram em `emissoes` e nunca em `tempo_s`. O site tem de as dizer,
     senao um total baixo passa por medicao em vez de lacuna. */
  function somar(porDia, de, ate) {
    var total = { emissoes: 0, tempo_s: 0, entrevistas: 0, sem_duracao: 0 };
    var chaves = {};
    (porDia || []).forEach(function (dia) {
      if (dia.data < de || dia.data > ate) { return; }
      total.emissoes += dia.emissoes;
      total.tempo_s += dia.tempo_s;
      total.sem_duracao += dia.sem_duracao || 0;
      (dia.chaves || []).forEach(function (k) { chaves[k] = true; });
    });
    total.entrevistas = Object.keys(chaves).length;
    return total;
  }

  /* Soma por canal num periodo, a partir de canal_por_dia. Devolve um mapa
     canal -> {emissoes, tempo_s, parciais, sem_duracao}. */
  function somarCanais(canalPorDia, de, ate) {
    var mapa = {};
    (canalPorDia || []).forEach(function (dia) {
      if (dia.data < de || dia.data > ate) { return; }
      Object.keys(dia.canais).forEach(function (id) {
        var c = dia.canais[id];
        var m = mapa[id] || { emissoes: 0, tempo_s: 0, parciais: 0, sem_duracao: 0 };
        m.emissoes += c.emissoes;
        m.tempo_s += c.tempo_s;
        m.parciais += c.parciais || 0;
        m.sem_duracao += c.sem_duracao || 0;
        mapa[id] = m;
      });
    });
    return mapa;
  }

  /* ---- humor -------------------------------------------------------- */

  function humorPara(dias, textos) {
    var lista = textos.humores;
    for (var i = 0; i < lista.length; i++) {
      var limite = lista[i].ate_dias;
      if (limite === null || limite === undefined || dias <= limite) { return lista[i]; }
    }
    return lista[lista.length - 1];
  }

  /* Determinista pelo numero de dias, para a frase nao mudar a cada
     refresh e ser a mesma para toda a gente no mesmo dia. */
  function fraseDeHumor(humor, dias) {
    if (!humor.frases.length) { return ""; }
    return humor.frases[dias % humor.frases.length].replace(/\{dias\}/g, String(dias));
  }

  function cabecalhoDias(dias, textos) {
    var c = textos.cabecalho;
    if (dias === null) { return c.sem_dados; }
    if (dias === 0) { return c.hoje; }
    if (dias === 1) { return c.um_dia; }
    return c.varios_dias.replace(/\{dias\}/g, String(dias));
  }

  /* ---- comparacoes --------------------------------------------------- */

  function preencher(template, valores) {
    return template.replace(/\{([a-z_]+)\}/g, function (tudo, chave) {
      return valores[chave] !== undefined ? String(valores[chave]) : tudo;
    });
  }

  /* Texto da comparacao para um tempo em segundos: "3 jogos de futebol
     de 90 minutos", "nem uma sesta de 20 minutos". A conta e uma divisao
     inteira, arredondada para baixo. */
  function comparar(segundos, comparacao, frases) {
    var n = Math.floor((segundos || 0) / comparacao.unidade_s);
    var v = { n: n, artigo: comparacao.artigo, um: comparacao.um, varios: comparacao.varios };
    if (n === 0) { return preencher(frases.nenhuma, v); }
    if (n === 1) { return preencher(frases.uma, v); }
    return preencher(comparacao.aproximada ? frases.aproximada : frases.varias, v);
  }

  /* Escolhe a comparacao cuja unidade da um numero legivel (entre 1 e
     999 se possivel), com um desvio determinista para variar entre
     canais e periodos sem sortear. */
  function escolherComparacao(segundos, comparacoes, semente) {
    var candidatas = comparacoes.filter(function (c) {
      var n = Math.floor(segundos / c.unidade_s);
      return n >= 1 && n < 1000;
    });
    if (!candidatas.length) {
      // Ou tudo e demasiado grande (fica a maior unidade) ou zero (fica a menor).
      var ordenadas = comparacoes.slice().sort(function (a, b) { return a.unidade_s - b.unidade_s; });
      return segundos >= ordenadas[ordenadas.length - 1].unidade_s ? ordenadas[ordenadas.length - 1] : ordenadas[0];
    }
    var indice = Math.abs(semente || 0) % candidatas.length;
    return candidatas[indice];
  }

  function sementeDe(texto) {
    var h = 0;
    for (var i = 0; i < texto.length; i++) { h = (h * 31 + texto.charCodeAt(i)) >>> 0; }
    return h;
  }

  return {
    MESES: MESES,
    DIAS_SEMANA: DIAS_SEMANA,
    dois: dois,
    deIso: deIso,
    paraIso: paraIso,
    diasEntre: diasEntre,
    duracaoLegivel: duracaoLegivel,
    dataLegivel: dataLegivel,
    dataComDiaSemana: dataComDiaSemana,
    inicioDaSemana: inicioDaSemana,
    intervalo: intervalo,
    somar: somar,
    somarCanais: somarCanais,
    humorPara: humorPara,
    fraseDeHumor: fraseDeHumor,
    cabecalhoDias: cabecalhoDias,
    preencher: preencher,
    comparar: comparar,
    escolherComparacao: escolherComparacao,
    sementeDe: sementeDe
  };
});
