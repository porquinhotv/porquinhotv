/* Lista todas as emissoes com a respetiva prova, por ano, da mais
   recente para a mais antiga. Le dados/emissoes.json e o resumo para os
   nomes dos canais. Nao calcula nada. */

(function () {
  "use strict";
  var el = PTVDOM.el;

  function tabela(linhas, nomeDe) {
    var t = el("table", { class: "tabela" });
    t.appendChild(el("thead", {}, [el("tr", {}, ["Data", "Canal", "Programa", "Prova"].map(function (h) { return el("th", { text: h }); }))]));
    var corpo = el("tbody");
    linhas.forEach(function (l) {
      var canal = el("td", { class: "canal", text: nomeDe[l.canal] || l.canal });
      canal.style.setProperty("--cor", PTVDOM.corDoCanal(l.canal));
      var data = el("td", { text: l.data });
      if (l.data_origem !== "declarada") { data.appendChild(el("span", { class: "parcial", text: " (publicação)" })); }
      corpo.appendChild(el("tr", {}, [
        data, canal,
        el("td", { text: l.programa + (l.titulo ? ": " + l.titulo : "") }),
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
      var resumo = r[1];
      /* Ambito visivel: o dataset guarda tudo desde 2019, o site mostra e
         conta a partir do corte que o resumo declara. Um resumo gerado
         antes de 2026-09-11 ainda nao traz `ambito`; nesse caso mostra-se
         tudo, como dantes. */
      var ambito = resumo.ambito || { visivel_desde: (resumo.tema && resumo.tema.desde) || "" };
      var todas = r[0].emissoes || [];
      var emissoes = todas.filter(function (e) { return e.data >= ambito.visivel_desde; });
      var foraDoAmbito = todas.length - emissoes.length;
      var nomeDe = {};
      resumo.por_canal.forEach(function (c) { nomeDe[c.canal] = c.nome; });
      var alvo = document.getElementById("conteudo");
      alvo.innerHTML = "";
      if (!emissoes.length) {
        alvo.appendChild(el("div", { class: "cartao vazio" }, [el("h2", { text: "Ainda sem dados" }), el("p", { text: "Ainda não há emissões registadas." })]));
        return;
      }
      if (foraDoAmbito) {
        var anoCorte = String(ambito.visivel_desde).slice(0, 4);
        alvo.appendChild(el("p", { class: "legenda-secao", text: foraDoAmbito + " " + (foraDoAmbito === 1 ? "emissão anterior" : "emissões anteriores") + " a " + anoCorte + " " + (foraDoAmbito === 1 ? "está registada" : "estão registadas") + " no conjunto de dados publicado, mas fora do âmbito do site. A Metodologia diz porquê." }));
      }
      var daImprensa = emissoes.filter(function (e) { return e.origem === "imprensa"; }).length;
      if (daImprensa) {
        alvo.appendChild(el("p", { class: "legenda-secao", text: daImprensa + " " + (daImprensa === 1 ? "emissão está provada" : "emissões estão provadas") + " por peças de imprensa que relatam ou anunciam a entrevista, e não pela página do canal. Uma prova vale o mesmo que a outra: a peça diz que a entrevista existiu e em que dia, e é isso que se conta." }));
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
