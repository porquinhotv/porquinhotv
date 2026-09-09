/* Lista todas as emissoes com a respetiva prova, por ano, da mais
   recente para a mais antiga. Le dados/emissoes.json e o resumo para os
   nomes dos canais. Nao calcula nada. */

(function () {
  "use strict";
  var el = PTVDOM.el;

  function tabela(linhas, nomeDe) {
    var t = el("table", { class: "tabela" });
    t.appendChild(el("thead", {}, [el("tr", {}, ["Data", "Canal", "Programa", "Duração", "Prova"].map(function (h) { return el("th", { text: h }); }))]));
    var corpo = el("tbody");
    linhas.forEach(function (l) {
      var canal = el("td", { class: "canal", text: nomeDe[l.canal] || l.canal });
      canal.style.setProperty("--cor", PTVDOM.corDoCanal(l.canal));
      var duracao;
      if (l.duracao_s === null || l.duracao_s === undefined) {
        // Nunca escrever zero nem deixar a celula vazia: a lacuna e um
        // facto sobre a fonte e tem de se ler como tal.
        duracao = el("td", {}, [el("span", { class: "parcial", text: "não apurada" })]);
      } else {
        duracao = el("td", { text: PTV.duracaoLegivel(l.duracao_s) });
        if (l.parcial) { duracao.appendChild(el("span", { class: "parcial", text: " (incompleta, só recortes)" })); }
      }
      var data = el("td", { text: l.data });
      if (l.data_origem !== "declarada") { data.appendChild(el("span", { class: "parcial", text: " (publicação)" })); }
      corpo.appendChild(el("tr", {}, [
        data, canal,
        el("td", { text: l.programa + (l.titulo ? ": " + l.titulo : "") }),
        duracao,
        el("td", {}, [
          el("a", { href: l.prova_url, rel: "noopener noreferrer", target: "_blank", text: l.origem === "imprensa" ? "notícia" : "ver" }),
          l.origem === "imprensa" ? el("span", { class: "parcial", text: " (imprensa)" }) : el("span", {})
        ])
      ]));
    });
    t.appendChild(corpo);
    return t;
  }

  Promise.all([PTVDOM.carregar("dados/emissoes.json"), PTVDOM.carregar("dados/resumo.json")])
    .then(function (r) {
      var emissoes = r[0].emissoes || [], resumo = r[1];
      var nomeDe = {};
      resumo.por_canal.forEach(function (c) { nomeDe[c.canal] = c.nome; });
      var alvo = document.getElementById("conteudo");
      alvo.innerHTML = "";
      if (!emissoes.length) {
        alvo.appendChild(el("div", { class: "cartao vazio" }, [el("h2", { text: "Ainda sem dados" }), el("p", { text: "Ainda não há emissões registadas." })]));
        return;
      }
      var semDuracao = emissoes.filter(function (e) { return e.duracao_s === null || e.duracao_s === undefined; }).length;
      var daImprensa = emissoes.filter(function (e) { return e.origem === "imprensa"; }).length;
      if (semDuracao || daImprensa) {
        var notas = [];
        if (daImprensa) { notas.push(daImprensa + " " + (daImprensa === 1 ? "emissão está provada" : "emissões estão provadas") + " por peças de imprensa que relatam ou anunciam a entrevista, e não pela página do canal; provam que existiu e quando, não a duração"); }
        if (semDuracao) { notas.push("em " + semDuracao + " " + (semDuracao === 1 ? "delas" : "casos") + " não foi possível apurar a duração, e por isso não contam no tempo"); }
        alvo.appendChild(el("p", { class: "legenda-secao", text: notas.join("; ") + "." }));
      }
      var porAno = {};
      emissoes.forEach(function (e) { (porAno[e.data.slice(0, 4)] = porAno[e.data.slice(0, 4)] || []).push(e); });
      Object.keys(porAno).sort().reverse().forEach(function (ano) {
        var linhas = porAno[ano].sort(function (a, b) { return b.data.localeCompare(a.data) || a.canal.localeCompare(b.canal); });
        var s = el("section", {}, [el("h2", { text: ano + ": " + linhas.length + (linhas.length === 1 ? " emissão" : " emissões") })]);
        s.appendChild(tabela(linhas, nomeDe));
        alvo.appendChild(s);
      });
    })
    .catch(function (e) { document.getElementById("conteudo").innerHTML = ""; PTVDOM.mostrarErro("Não foi possível carregar os dados. " + e.message); });
})();
