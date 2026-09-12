/* Pagina principal. Le dados/resumo.json e textos.json, e desenha.
   Nao calcula agregados novos: soma periodos a partir das reparticoes
   diarias. Tudo o resto vem feito. Conta uma coisa so, entrevistas
   exclusivas; nao ha tempo em lado nenhum desde 2026-09-10. */

(function () {
  "use strict";

  var el = PTVDOM.el;
  var cor = PTVDOM.corDoCanal;

  var PERIODOS = [
    { id: "semana", tab: "Esta semana", frase: "esta semana" },
    { id: "mes", tab: "Este mês", frase: "este mês" },
    { id: "ano", tab: "Este ano", frase: "este ano" },
    { id: "sempre", tab: "Desde sempre", frase: "" }   // tab e frase vem do resumo (ambito)
  ];
  var ESCALAS = [
    { id: "semana", tab: "Semanas", chave: "por_semana", campo: "semana" },
    { id: "mes", tab: "Meses", chave: "por_mes", campo: "mes" },
    { id: "ano", tab: "Anos", chave: "por_ano", campo: "ano" }
  ];

  var estado = { resumo: null, textos: null, periodo: "mes", escala: "mes", hoje: new Date() };

  /* O resumo passou a trazer o ambito visivel a 2026-09-11. Um resumo
     gerado antes ainda nao o traz; ate a recolha seguinte correr, o site
     le esse resumo e comporta-se como dantes, em vez de partir. */
  function ambito() {
    var r = estado.resumo;
    return r.ambito || { visivel_desde: r.tema.desde, rotulo: r.tema.desde_rotulo, tab: "" };
  }

  function periodoAtual() {
    var p = PERIODOS.filter(function (x) { return x.id === estado.periodo; })[0];
    return { id: p.id, tab: p.tab, frase: p.frase || ambito().rotulo };
  }

  function nomeDoCanal(id) {
    var c = estado.resumo.por_canal.filter(function (x) { return x.canal === id; })[0];
    return c ? c.nome : id;
  }

  function plural(n, um, varios) { return n === 1 ? "1 " + um : n + " " + varios; }

  /* A camada satirica vive toda em config/humor.yml e chega aqui pelo
     textos.json. Quando falta, o site desenha os numeros na mesma: o
     humor e um enfeite, o numero e que e o site. */
  function metricas() { return estado.textos.metricas || {}; }

  function legenda(chave) {
    var l = metricas().legendas || {};
    return l[chave] || "";
  }

  function acrescentarFrase(no, texto) {
    if (texto) { no.appendChild(el("p", { class: "comparacao", text: texto })); }
  }

  /* Um numero e uma unidade. Ate 2026-09-11 escreviam-se dois, as
     transmissoes e as entrevistas distintas, e quem lia o site tinha de
     perceber a diferenca antes de perceber o numero. */
  function contagemDe(bucket) {
    return plural(bucket.entrevistas, "entrevista exclusiva", "entrevistas exclusivas");
  }

  // ---- porquinho ---------------------------------------------------------

  function desenharPorquinho() {
    var porco = document.getElementById("porco");
    var dias = null;
    var ultima = estado.resumo.recordes.ultima_data;
    if (ultima) {
      dias = PTV.diasEntre(ultima, PTV.paraIso(estado.hoje));
      if (dias < 0) { dias = 0; }
    }
    var cabecalho = PTV.cabecalhoDias(dias, estado.textos);
    if (dias === null) {
      porco.setAttribute("data-mood", "sem-dados");
      document.getElementById("dias").textContent = cabecalho;
      document.getElementById("frase").textContent = "";
      return;
    }
    var humor = PTV.humorPara(dias, estado.textos);
    porco.setAttribute("data-mood", humor.id);
    var texto = cabecalho.replace(/(\d+ dias?|1 dia)/, "<b>$1</b>");
    document.getElementById("dias").innerHTML =
      texto + " " + PTVDOM.escapar(PTV.preencher(estado.textos.estado, { humor: humor.rotulo })).replace(humor.rotulo, "<b>" + PTVDOM.escapar(humor.rotulo) + "</b>");
    document.getElementById("frase").textContent = PTV.fraseDeHumor(humor, dias);

    function espantar() {
      porco.classList.remove("espantado");
      void porco.getBoundingClientRect();
      porco.classList.add("espantado");
      setTimeout(function () { porco.classList.remove("espantado"); }, 1300);
    }
    porco.addEventListener("click", espantar);
    porco.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); espantar(); }
    });
  }

  // ---- seletor de periodo -----------------------------------------------

  function desenharSeletor(painel, lista, atual, aoEscolher, rotulo) {
    var s = el("div", { class: "seletor", role: "tablist", "aria-label": rotulo });
    lista.forEach(function (p) {
      var b = el("button", { type: "button", role: "tab", "aria-selected": String(p.id === atual), text: p.tab });
      b.addEventListener("click", function () { aoEscolher(p.id); });
      s.appendChild(b);
    });
    painel.appendChild(s);
  }

  // ---- numero grande -----------------------------------------------------

  function desenharTotal(painel, intervalo) {
    var t = PTV.somar(estado.resumo.por_dia, intervalo.de, intervalo.ate);
    var p = periodoAtual();
    var cartao = el("section", { class: "cartao" });

    if (t.entrevistas === 0) {
      var vazio = el("p", { class: "numero-grande", text: "Nenhuma entrevista exclusiva" });
      vazio.appendChild(el("small", { text: p.frase }));
      cartao.appendChild(vazio);
      acrescentarFrase(cartao, PTV.fraseDeMetrica(metricas().total, 0, metricas().temporada));
      painel.appendChild(cartao);
      return;
    }

    var numero = el("p", { class: "numero-grande" });
    numero.appendChild(document.createTextNode(plural(t.entrevistas, "entrevista exclusiva", "entrevistas exclusivas")));
    // Por baixo do numero fica so o periodo. A mesma entrevista em dois
    // canais conta uma vez, e quando isso acontece quem o diz e a nota da
    // pagina de Fontes, ao lado das duas provas.
    numero.appendChild(el("small", { text: p.frase }));
    cartao.appendChild(numero);
    // A escada e pelo numero de entrevistas, que e o numero grande.
    acrescentarFrase(cartao, PTV.fraseDeMetrica(metricas().total, t.entrevistas, metricas().temporada));
    painel.appendChild(cartao);
  }

  // ---- canais -------------------------------------------------------------

  function desenharCanais(painel, intervalo) {
    var canais = PTV.somarCanais(estado.resumo.canal_por_dia, intervalo.de, intervalo.ate);
    var lista = estado.resumo.por_canal.map(function (c) {
      var s = canais[c.canal] || { entrevistas: 0 };
      return { id: c.canal, nome: c.nome, entrevistas: s.entrevistas };
    });
    var total = lista.reduce(function (n, c) { return n + c.entrevistas; }, 0);
    var ordenada = lista.slice().sort(function (a, b) { return b.entrevistas - a.entrevistas || a.nome.localeCompare(b.nome); });
    var p = periodoAtual();

    var secao = el("section", {}, [
      el("h2", { text: "Em que canais" }),
      el("p", { class: "legenda-secao", text: total > 0
        ? legenda("canais")
        : "Sem entrevistas registadas " + p.frase + "." })
    ]);

    if (total > 0) {
      var empilhada = el("div", { class: "empilhada", role: "img", "aria-label": "Quota de entrevistas exclusivas por canal" });
      ordenada.filter(function (c) { return c.entrevistas > 0; }).forEach(function (c) {
        var f = el("span", { title: c.nome + ": " + Math.round(c.entrevistas / total * 100) + "%" });
        f.style.width = (c.entrevistas / total * 100).toFixed(2) + "%";
        f.style.background = cor(c.id);
        empilhada.appendChild(f);
      });
      secao.appendChild(empilhada);
    }

    var ul = el("ul", { class: "canais" });
    ordenada.forEach(function (c) {
      var ponto = el("span", { class: "ponto" }); ponto.style.background = cor(c.id);
      var enchimento = el("span"); enchimento.style.width = (total ? c.entrevistas / total * 100 : 0).toFixed(1) + "%"; enchimento.style.background = cor(c.id);
      var valor = c.entrevistas > 0
        ? plural(c.entrevistas, "entrevista", "entrevistas") + " (" + Math.round(c.entrevistas / total * 100) + "%)"
        : "nada registado";
      ul.appendChild(el("li", { class: c.entrevistas > 0 ? "" : "zero" }, [
        ponto,
        el("span", { class: "nome", text: c.nome }),
        el("span", { class: "pista" }, [enchimento]),
        el("span", { class: "valor", text: valor })
      ]));
    });
    secao.appendChild(ul);

    /* A frase do lider so aparece quando ha repartição para comentar. Com
       duas entrevistas no periodo, "leva 50%" e uma frase sobre ruido: a
       percentagem esta certa e a graca nao. */
    var lider = ordenada[0];
    if (metricas().lider && total >= 3 && lider && lider.entrevistas >= 2) {
      acrescentarFrase(secao, PTV.preencher(metricas().lider, {
        canal: lider.nome, n: Math.round(lider.entrevistas / total * 100)
      }));
    }
    painel.appendChild(secao);
  }

  // ---- evolucao -----------------------------------------------------------

  function rotuloDoPeriodo(campo, valor) {
    if (campo === "mes") { var p = valor.split("-"); return PTV.MESES[Number(p[1]) - 1] + " de " + p[0]; }
    if (campo === "semana") { return "semana " + valor.slice(6) + " de " + valor.slice(0, 4); }
    return valor;
  }

  function desenharEvolucao(painel) {
    var escala = ESCALAS.filter(function (e) { return e.id === estado.escala; })[0];
    var serie = estado.resumo[escala.chave] || [];
    if (escala.id === "semana" && serie.length > 78) { serie = serie.slice(-78); }
    var secao = el("section", {}, [
      el("h2", { text: "Como tem evoluído" }),
      el("p", { class: "legenda-secao", text: legenda("evolucao") })
    ]);
    desenharSeletor(secao, ESCALAS, estado.escala, function (id) { estado.escala = id; desenharPainel(); }, "Escala");

    if (!serie.length) {
      secao.appendChild(el("p", { class: "legenda-secao", text: "Ainda sem dados." }));
      painel.appendChild(secao);
      return;
    }

    var largura = 1000, altura = 220, baixo = 30, cima = 6;
    var area = altura - baixo - cima;
    var passo = largura / serie.length;
    var max = Math.max.apply(null, serie.map(function (s) { return s.entrevistas; })) || 1;
    var svg = '<svg class="grafico" viewBox="0 0 ' + largura + ' ' + altura + '" role="group" aria-label="Entrevistas exclusivas por período">';
    var anosVistos = {};
    serie.forEach(function (s, i) {
      var h = s.entrevistas / max * area;
      var x = i * passo;
      var rotulo = rotuloDoPeriodo(escala.campo, s[escala.campo]) + ": " + contagemDe(s);
      svg += '<g class="coluna" data-i="' + i + '" tabindex="0" role="img" aria-label="' + PTVDOM.escapar(rotulo) + '">';
      svg += '<rect x="' + x.toFixed(1) + '" y="0" width="' + passo.toFixed(1) + '" height="' + (altura - baixo) + '" fill="transparent"></rect>';
      svg += '<rect class="barra" x="' + (x + passo * 0.15).toFixed(1) + '" y="' + (altura - baixo - h).toFixed(1) + '" width="' + (passo * 0.7).toFixed(1) + '" height="' + h.toFixed(1) + '" rx="2"></rect></g>';
      var ano = String(s[escala.campo]).slice(0, 4);
      if (!anosVistos[ano] && escala.id !== "ano") {
        anosVistos[ano] = true;
        var cx = x + passo / 2, ancora = "middle";
        if (cx < 20) { cx = 1; ancora = "start"; } else if (cx > largura - 20) { cx = largura - 1; ancora = "end"; }
        svg += '<text class="eixo" x="' + cx.toFixed(1) + '" y="' + (altura - 10) + '" text-anchor="' + ancora + '">' + ano + '</text>';
      } else if (escala.id === "ano") {
        svg += '<text class="eixo" x="' + (x + passo / 2).toFixed(1) + '" y="' + (altura - 10) + '" text-anchor="middle">' + ano + '</text>';
      }
    });
    svg += '<line class="base" x1="0" y1="' + (altura - baixo) + '" x2="' + largura + '" y2="' + (altura - baixo) + '"/></svg>';

    var leitura = el("p", { class: "leitura" });
    var suporte = el("div", { html: svg });
    function mostrar(i) {
      var s = serie[i];
      leitura.textContent = rotuloDoPeriodo(escala.campo, s[escala.campo]) + ": " + contagemDe(s);
      Array.prototype.forEach.call(suporte.querySelectorAll("g.coluna"), function (g) {
        g.classList.toggle("ativa", Number(g.getAttribute("data-i")) === i);
      });
    }
    Array.prototype.forEach.call(suporte.querySelectorAll("g.coluna"), function (g) {
      var i = Number(g.getAttribute("data-i"));
      ["mouseenter", "focus", "click"].forEach(function (ev) { g.addEventListener(ev, function () { mostrar(i); }); });
    });
    secao.appendChild(leitura);
    secao.appendChild(suporte);
    painel.appendChild(secao);
    mostrar(serie.length - 1);
  }

  // ---- recordes -----------------------------------------------------------

  function desenharRecordes(painel) {
    var r = estado.resumo.recordes;
    if (!r.ultima_data) { return; }
    var grelha = el("div", { class: "recordes" });
    grelha.appendChild(el("div", { class: "cartao" }, [
      el("h3", { text: "Última entrevista exclusiva" }),
      el("p", { text: PTV.dataLegivel(r.ultima_data) }),
      el("small", { text: PTV.dataComDiaSemana(r.ultima_data).split(",")[0] })
    ]));
    if (r.maior_jejum) {
      grelha.appendChild(el("div", { class: "cartao" }, [
        el("h3", { text: "Maior jejum" }),
        el("p", { text: plural(r.maior_jejum.dias, "dia", "dias") }),
        el("small", { text: "de " + PTV.dataLegivel(r.maior_jejum.de) + " a " + PTV.dataLegivel(r.maior_jejum.ate) })
      ]));
    }
    if (r.maior_maratona && r.maior_maratona.dias > 1) {
      grelha.appendChild(el("div", { class: "cartao" }, [
        el("h3", { text: "Maior maratona" }),
        el("p", { text: plural(r.maior_maratona.dias, "dia seguido", "dias seguidos") }),
        el("small", { text: "de " + PTV.dataLegivel(r.maior_maratona.de) + " a " + PTV.dataLegivel(r.maior_maratona.ate) })
      ]));
    }
    painel.appendChild(el("section", {}, [
      el("h2", { text: "Recordes" }),
      el("p", { class: "legenda-secao", text: legenda("recordes") }),
      grelha
    ]));
  }

  // ---- painel -------------------------------------------------------------

  function desenharPainel() {
    var painel = document.getElementById("painel");
    painel.innerHTML = "";
    if (!estado.resumo.totais.entrevistas) {
      painel.appendChild(el("div", { class: "cartao vazio" }, [
        el("h2", { text: "Ainda sem dados" }),
        el("p", { text: "Ainda não há entrevistas registadas. Quando houver, aparecem aqui com prova em cada linha." })
      ]));
      return;
    }
    var intervalo = PTV.intervalo(estado.periodo, estado.hoje, ambito().visivel_desde);
    var sempre = PERIODOS.filter(function (x) { return x.id === "sempre"; })[0];
    sempre.tab = ambito().tab || sempre.tab;
    desenharSeletor(painel, PERIODOS, estado.periodo, function (id) { estado.periodo = id; desenharPainel(); }, "Período");
    desenharTotal(painel, intervalo);
    desenharCanais(painel, intervalo);
    desenharEvolucao(painel);
    desenharRecordes(painel);
    painel.appendChild(el("p", { class: "legenda-secao" }, [
      el("a", { href: "calendario.html", text: "Ver o calendário, dia a dia, ano a ano" })
    ]));
  }

  Promise.all([PTVDOM.carregar("dados/resumo.json"), PTVDOM.carregar("textos.json")])
    .then(function (r) {
      estado.resumo = r[0];
      estado.textos = r[1];
      PTVDOM.marcarGerado(estado.resumo);
      desenharPorquinho();
      desenharPainel();
    })
    .catch(function (erro) {
      document.getElementById("dias").textContent = "Dados indisponíveis.";
      PTVDOM.mostrarErro("Não foi possível carregar dados/resumo.json ou textos.json. " + erro.message);
    });
})();
