/* Pagina principal. Le dados/resumo.json e textos.json, e desenha.
   Nao calcula agregados novos: soma periodos a partir das reparticoes
   diarias e divide tempos pelas comparacoes. Tudo o resto vem feito. */

(function () {
  "use strict";

  var el = PTVDOM.el;
  var cor = PTVDOM.corDoCanal;

  var PERIODOS = [
    { id: "semana", tab: "Esta semana", frase: "esta semana" },
    { id: "mes", tab: "Este mês", frase: "este mês" },
    { id: "ano", tab: "Este ano", frase: "este ano" },
    { id: "sempre", tab: "Desde sempre", frase: "" }   // frase vem do resumo (desde_rotulo)
  ];
  var ESCALAS = [
    { id: "semana", tab: "Semanas", chave: "por_semana", campo: "semana" },
    { id: "mes", tab: "Meses", chave: "por_mes", campo: "mes" },
    { id: "ano", tab: "Anos", chave: "por_ano", campo: "ano" }
  ];

  var estado = { resumo: null, textos: null, periodo: "mes", escala: "mes", hoje: new Date() };

  function periodoAtual() {
    var p = PERIODOS.filter(function (x) { return x.id === estado.periodo; })[0];
    return { id: p.id, tab: p.tab, frase: p.frase || estado.resumo.tema.desde_rotulo };
  }

  function nomeDoCanal(id) {
    var c = estado.resumo.por_canal.filter(function (x) { return x.canal === id; })[0];
    return c ? c.nome : id;
  }

  function plural(n, um, varios) { return n === 1 ? "1 " + um : n + " " + varios; }

  /* Um periodo em que nenhuma emissao tem duracao apurada tem tempo zero,
     e escrever "menos de um minuto" ali seria publicar uma medicao que
     nao existe. Ver METODOLOGIA, seccao 6. */
  function tempoDe(bucket) {
    if (bucket.tempo_s > 0) {
      return PTV.duracaoLegivel(bucket.tempo_s) + (bucket.sem_duracao ? ", mais " + bucket.sem_duracao + " sem duração apurada" : "");
    }
    return bucket.sem_duracao ? "duração não apurada" : PTV.duracaoLegivel(0);
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

    if (t.emissoes === 0) {
      cartao.appendChild(el("p", { class: "numero-grande", text: "Nenhuma entrevista exclusiva", }));
      cartao.appendChild(el("p", { class: "comparacao", text: PTV.preencher("{periodo}, nada registado.", { periodo: p.frase.charAt(0).toUpperCase() + p.frase.slice(1) }) }));
      painel.appendChild(cartao);
      return;
    }

    var numero = el("p", { class: "numero-grande" });
    numero.appendChild(document.createTextNode(plural(t.entrevistas, "entrevista exclusiva", "entrevistas exclusivas")));
    var partes = [];
    if (t.emissoes !== t.entrevistas) { partes.push(plural(t.emissoes, "emissão", "emissões")); }
    // Quando todas as emissoes do periodo estao sem duracao apurada, o
    // tempo e zero e dizer "0 minutos no ar" seria uma medicao falsa.
    if (t.tempo_s > 0) { partes.push(PTV.duracaoLegivel(t.tempo_s) + " no ar"); }
    partes.push(p.frase);
    numero.appendChild(el("small", { text: partes.join(", ") }));
    cartao.appendChild(numero);

    if (t.sem_duracao > 0) {
      cartao.appendChild(el("p", {
        class: "nota-parcial",
        text: t.sem_duracao === t.emissoes
          ? "Não foi possível apurar a duração de nenhuma destas emissões. Estão provadas e contadas como entrevistas; o tempo no ar não é conhecido."
          : plural(t.sem_duracao, "emissão está", "emissões estão") + " sem duração apurada e não entra" + (t.sem_duracao === 1 ? "" : "m") + " no tempo acima. O tempo real é maior."
      }));
    }

    var comp = PTV.escolherComparacao(t.tempo_s, estado.textos.comparacoes, PTV.sementeDe(estado.periodo + intervalo.de));
    if (t.tempo_s > 0) { cartao.appendChild(el("p", {
      class: "comparacao",
      text: PTV.preencher(estado.textos.frases.periodo, {
        tempo: PTV.duracaoLegivel(t.tempo_s).charAt(0).toUpperCase() + PTV.duracaoLegivel(t.tempo_s).slice(1),
        periodo: p.frase,
        comparacao: PTV.comparar(t.tempo_s, comp, estado.textos.frases)
      })
    })); }

    var canais = PTV.somarCanais(estado.resumo.canal_por_dia, intervalo.de, intervalo.ate);
    var parciais = Object.keys(canais).reduce(function (n, id) { return n + canais[id].parciais; }, 0);
    if (parciais > 0) {
      cartao.appendChild(el("p", {
        class: "nota-parcial",
        text: plural(parciais, "emissão tem", "emissões têm") + " duração incompleta: só existem recortes online, e contou-se o que existe. O tempo real é maior."
      }));
    }
    painel.appendChild(cartao);
  }

  // ---- canais -------------------------------------------------------------

  function desenharCanais(painel, intervalo) {
    var canais = PTV.somarCanais(estado.resumo.canal_por_dia, intervalo.de, intervalo.ate);
    var lista = estado.resumo.por_canal.map(function (c) {
      var s = canais[c.canal] || { emissoes: 0, tempo_s: 0, parciais: 0, sem_duracao: 0 };
      return { id: c.canal, nome: c.nome, emissoes: s.emissoes, tempo_s: s.tempo_s, sem_duracao: s.sem_duracao };
    });
    var total = lista.reduce(function (n, c) { return n + c.tempo_s; }, 0);
    var ordenada = lista.slice().sort(function (a, b) { return b.tempo_s - a.tempo_s || a.nome.localeCompare(b.nome); });
    var p = periodoAtual();

    var secao = el("section", {}, [
      el("h2", { text: "Em que canais" }),
      el("p", { class: "legenda-secao", text: total > 0
        ? "Como se reparte o tempo de entrevistas exclusivas " + p.frase + ". A mesma entrevista emitida em dois canais conta nos dois."
        : "Sem entrevistas registadas " + p.frase + "." })
    ]);

    if (total > 0) {
      var empilhada = el("div", { class: "empilhada", role: "img", "aria-label": "Quota de tempo por canal" });
      ordenada.filter(function (c) { return c.tempo_s > 0; }).forEach(function (c) {
        var f = el("span", { title: c.nome + ": " + Math.round(c.tempo_s / total * 100) + "%" });
        f.style.width = (c.tempo_s / total * 100).toFixed(2) + "%";
        f.style.background = cor(c.id);
        empilhada.appendChild(f);
      });
      secao.appendChild(empilhada);
    }

    var ul = el("ul", { class: "canais" });
    ordenada.forEach(function (c) {
      var ponto = el("span", { class: "ponto" }); ponto.style.background = cor(c.id);
      var enchimento = el("span"); enchimento.style.width = (total ? c.tempo_s / total * 100 : 0).toFixed(1) + "%"; enchimento.style.background = cor(c.id);
      var valor;
      if (c.tempo_s > 0) {
        valor = plural(c.emissoes, "emissão", "emissões") + ", " + PTV.duracaoLegivel(c.tempo_s) + " (" + Math.round(c.tempo_s / total * 100) + "%)";
        if (c.sem_duracao > 0) { valor += ", mais " + c.sem_duracao + " sem duração apurada"; }
      } else if (c.emissoes > 0) {
        valor = plural(c.emissoes, "emissão", "emissões") + ", duração não apurada";
      } else {
        valor = "nada registado";
      }
      ul.appendChild(el("li", { class: c.tempo_s > 0 ? "" : "zero" }, [
        ponto,
        el("span", { class: "nome", text: c.nome }),
        el("span", { class: "pista" }, [enchimento]),
        el("span", { class: "valor", text: valor })
      ]));
    });
    secao.appendChild(ul);

    if (total > 0 && ordenada[0].tempo_s > 0) {
      var topo = ordenada[0];
      var comp = PTV.escolherComparacao(topo.tempo_s, estado.textos.comparacoes, PTV.sementeDe(topo.id + estado.periodo));
      secao.appendChild(el("p", {
        class: "comparacao",
        text: PTV.preencher(estado.textos.frases.canal, {
          canal: topo.nome,
          tempo: PTV.duracaoLegivel(topo.tempo_s),
          comparacao: PTV.comparar(topo.tempo_s, comp, estado.textos.frases)
        })
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
      el("p", { class: "legenda-secao", text: "Cada barra é o tempo de entrevistas exclusivas nesse período. Passe o rato ou use o teclado para ler os valores." })
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
    var max = Math.max.apply(null, serie.map(function (s) { return s.tempo_s; })) || 1;
    var svg = '<svg class="grafico" viewBox="0 0 ' + largura + ' ' + altura + '" role="group" aria-label="Tempo por período">';
    var anosVistos = {};
    serie.forEach(function (s, i) {
      var h = s.tempo_s / max * area;
      var x = i * passo;
      var rotulo = rotuloDoPeriodo(escala.campo, s[escala.campo]) + ": " + plural(s.emissoes, "emissão", "emissões") + ", " + tempoDe(s);
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
      leitura.textContent = rotuloDoPeriodo(escala.campo, s[escala.campo]) + ": " + plural(s.emissoes, "emissão", "emissões") + ", " + tempoDe(s);
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
      el("p", { class: "legenda-secao", text: "Contados sobre todo o histórico registado, por dia de emissão." }),
      grelha
    ]));
  }

  // ---- painel -------------------------------------------------------------

  function desenharPainel() {
    var painel = document.getElementById("painel");
    painel.innerHTML = "";
    if (!estado.resumo.totais.emissoes) {
      painel.appendChild(el("div", { class: "cartao vazio" }, [
        el("h2", { text: "Ainda sem dados" }),
        el("p", { text: "Ainda não há entrevistas registadas. Quando houver, aparecem aqui com prova em cada linha." })
      ]));
      return;
    }
    var intervalo = PTV.intervalo(estado.periodo, estado.hoje, estado.resumo.tema.desde);
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
      document.getElementById("gerado").textContent = "Última recolha: " + String(estado.resumo.gerado_em).replace("T", " ").replace("+00:00", " UTC");
      desenharPorquinho();
      desenharPainel();
    })
    .catch(function (erro) {
      document.getElementById("dias").textContent = "Dados indisponíveis.";
      PTVDOM.mostrarErro("Não foi possível carregar dados/resumo.json ou textos.json. " + erro.message);
    });
})();
