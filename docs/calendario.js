/* Grelha anual. Colunas sao semanas, linhas dias da semana. Revela padroes
   de dia fixo e mudancas de grelha sem calcular nada de novo: le
   canal_por_dia do resumo.json e pinta. */

(function () {
  "use strict";

  var el = PTVDOM.el;
  var cor = PTVDOM.corDoCanal;
  var CEL = 13, ESPACO = 3, PASSO = CEL + ESPACO, ESQ = 34, TOPO = 22;
  var estado = { resumo: null, ano: null };

  function indexar(resumo) {
    var idx = {};
    (resumo.canal_por_dia || []).forEach(function (dia) {
      var lista = Object.keys(dia.canais).map(function (id) {
        var c = dia.canais[id];
        return { id: id, emissoes: c.emissoes, declarada: (c.declaradas || 0) >= c.emissoes };
      });
      lista.sort(function (a, b) { return b.emissoes - a.emissoes || a.id.localeCompare(b.id); });
      idx[dia.data] = lista;
    });
    return idx;
  }

  function nomes(resumo) {
    var m = {};
    resumo.por_canal.forEach(function (c) { m[c.canal] = c.nome; });
    return m;
  }

  function rotuloDia(iso, dia, nomeDe) {
    var partes = dia.map(function (c) {
      var vezes = c.emissoes === 1 ? "1 emissão" : c.emissoes + " emissões";
      return nomeDe[c.id] + ", " + vezes + (c.declarada ? "" : ", data de publicação");
    });
    var d = PTV.dataComDiaSemana(iso);
    return d.charAt(0).toUpperCase() + d.slice(1) + ": " + partes.join("; ");
  }

  function grelha(ano, idx, nomeDe) {
    var jan = new Date(Number(ano), 0, 1), dez = new Date(Number(ano), 11, 31);
    var inicio = PTV.inicioDaSemana(jan);
    var semanas = Math.ceil(((dez - inicio) / 86400000 + 1) / 7);
    var largura = ESQ + semanas * PASSO, altura = TOPO + 7 * PASSO;
    var svg = '<svg class="cal" width="' + largura + '" height="' + altura + '" viewBox="0 0 ' + largura + ' ' + altura + '" role="group" aria-label="Calendário de ' + ano + '">';
    ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"].forEach(function (n, linha) {
      svg += '<text class="cal-eixo" x="' + (ESQ - 6) + '" y="' + (TOPO + linha * PASSO + CEL - 2) + '" text-anchor="end">' + n + '</text>';
    });
    var mesVisto = {}, cursor = new Date(inicio);
    for (var s = 0; s < semanas; s++) {
      for (var linha = 0; linha < 7; linha++) {
        if (cursor.getFullYear() === Number(ano)) {
          var iso = PTV.paraIso(cursor), x = ESQ + s * PASSO, y = TOPO + linha * PASSO;
          if (!mesVisto[cursor.getMonth()] && cursor.getDate() <= 7 && linha === 0) {
            mesVisto[cursor.getMonth()] = true;
            svg += '<text class="cal-eixo" x="' + x + '" y="' + (TOPO - 8) + '">' + PTV.MESES[cursor.getMonth()].slice(0, 3) + '</text>';
          }
          var dia = idx[iso];
          if (!dia) {
            svg += '<rect class="cal-vazio" x="' + x + '" y="' + y + '" width="' + CEL + '" height="' + CEL + '" rx="2"></rect>';
          } else {
            var fatia = CEL / dia.length;
            svg += '<g class="cal-dia" data-data="' + iso + '" tabindex="0" role="img" aria-label="' + PTVDOM.escapar(rotuloDia(iso, dia, nomeDe)) + '">';
            dia.forEach(function (c, i) {
              var cc = cor(c.id);
              svg += '<rect class="' + (c.declarada ? "" : "cal-nao-declarada") + '" x="' + (x + i * fatia).toFixed(2) + '" y="' + y + '" width="' + fatia.toFixed(2) + '" height="' + CEL + '" rx="1.5" fill="' + (c.declarada ? cc : "none") + '" stroke="' + (c.declarada ? "none" : cc) + '"></rect>';
            });
            svg += '</g>';
          }
        }
        cursor.setDate(cursor.getDate() + 1);
      }
    }
    return svg + '</svg>';
  }

  function legenda(ano, idx, nomeDe) {
    var tot = {};
    Object.keys(idx).forEach(function (iso) {
      if (iso.slice(0, 4) !== ano) { return; }
      idx[iso].forEach(function (c) {
        var t = tot[c.id] || { emissoes: 0 };
        t.emissoes += c.emissoes; tot[c.id] = t;
      });
    });
    var ul = el("ul", { class: "canais" });
    Object.keys(tot).sort(function (a, b) { return tot[b].emissoes - tot[a].emissoes || a.localeCompare(b); }).forEach(function (id) {
      var ponto = el("span", { class: "ponto" }); ponto.style.background = cor(id);
      var vezes = tot[id].emissoes === 1 ? "1 emissão" : tot[id].emissoes + " emissões";
      ul.appendChild(el("li", {}, [ponto, el("span", { class: "nome", text: nomeDe[id] || id }), el("span", { class: "pista", style: "visibility:hidden" }), el("span", { class: "valor", text: vezes })]));
    });
    return ul;
  }

  function desenhar() {
    var alvo = document.getElementById("conteudo");
    alvo.innerHTML = "";
    var idx = indexar(estado.resumo), nomeDe = nomes(estado.resumo);
    var anos = Object.keys(idx).map(function (d) { return d.slice(0, 4); }).filter(function (a, i, arr) { return arr.indexOf(a) === i; }).sort();
    if (!anos.length) {
      alvo.appendChild(el("div", { class: "cartao vazio" }, [el("h2", { text: "Ainda sem dados" }), el("p", { text: "Ainda não há emissões registadas." })]));
      return;
    }
    if (anos.indexOf(estado.ano) === -1) { estado.ano = anos[anos.length - 1]; }
    var seletor = el("div", { class: "seletor", role: "tablist", "aria-label": "Ano" });
    anos.forEach(function (a) {
      var b = el("button", { type: "button", role: "tab", "aria-selected": String(a === estado.ano), text: a });
      b.addEventListener("click", function () { estado.ano = a; desenhar(); });
      seletor.appendChild(b);
    });
    alvo.appendChild(seletor);
    var leitura = el("p", { class: "leitura" });
    alvo.appendChild(leitura);
    var suporte = el("div", { class: "cal-holder", html: grelha(estado.ano, idx, nomeDe) });
    alvo.appendChild(suporte);
    function mostrar(iso) {
      leitura.textContent = rotuloDia(iso, idx[iso], nomeDe);
      Array.prototype.forEach.call(suporte.querySelectorAll("g.cal-dia"), function (g) { g.classList.toggle("ativa", g.getAttribute("data-data") === iso); });
    }
    Array.prototype.forEach.call(suporte.querySelectorAll("g.cal-dia"), function (g) {
      var iso = g.getAttribute("data-data");
      ["mouseenter", "focus", "click"].forEach(function (ev) { g.addEventListener(ev, function () { mostrar(iso); }); });
    });
    var doAno = Object.keys(idx).filter(function (d) { return d.slice(0, 4) === estado.ano; }).sort();
    if (doAno.length) { mostrar(doAno[doAno.length - 1]); }
    alvo.appendChild(el("h2", { text: "Canais em " + estado.ano }));
    alvo.appendChild(legenda(estado.ano, idx, nomeDe));
  }

  PTVDOM.carregar("dados/resumo.json")
    .then(function (r) { estado.resumo = r; PTVDOM.marcarGerado(r); desenhar(); })
    .catch(function (e) { document.getElementById("conteudo").innerHTML = ""; PTVDOM.mostrarErro("Não foi possível carregar dados/resumo.json. " + e.message); });
})();
