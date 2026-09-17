// Favorito "Salvar dados da loja" (coleta assistida).
//
// Roda no navegador de quem esta navegando, sobre a ficha de uma loja aberta
// no Google Maps. Nao navega, nao busca e nao rola nada sozinho: le o que ja
// esta na tela e baixa um arquivo JSON. Rodar uma vez na aba "Visao geral"
// (ficha e horarios de pico) e outra na aba "Avaliacoes" (avaliacoes que a
// pessoa carregou). O importador junta os arquivos pela loja.
//
// Nome de quem avaliou nao e lido.
(function () {
  var main = document.querySelector('div[role="main"]');
  if (!main || location.host.indexOf("google.") < 0) {
    alert("Abra a ficha de uma loja no Google Maps e clique de novo.");
    return;
  }
  var lab = function (sel) { var e = main.querySelector(sel); return e ? e.getAttribute("aria-label") || "" : ""; };
  var depoisDoisPontos = function (s) { var i = s.indexOf(":"); return (i >= 0 ? s.slice(i + 1) : s).trim(); };
  var url = decodeURIComponent(location.href);
  var pid = (url.match(/!1s(0x[0-9a-f]+:0x[0-9a-f]+)/) || [])[1] || "";
  var ll = url.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
  var aba = (document.querySelector('button[role="tab"][aria-selected="true"]') || {}).innerText || "";
  var dias = ["domingo", "segunda-feira", "terca-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sabado"];
  var semAcento = function (s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); };

  var d = {
    formato: "vitrine-assistida-1",
    salvo_em: new Date().toISOString(),
    aba: aba.trim(),
    url: location.href.split("?")[0],
    place_id: pid,
    latitude: ll ? parseFloat(ll[1]) : null,
    longitude: ll ? parseFloat(ll[2]) : null,
    nome: main.getAttribute("aria-label") || "",
    categoria: ((main.querySelector('button[jsaction*="category"]') || {}).innerText || "").trim(),
    nota_txt: lab('span[aria-label*="estrelas"]'),
    total_txt: (Array.prototype.find.call(main.querySelectorAll('span[aria-label*="avaliações"]'),
      function (e) { return /^[\d.]+ avaliaç/.test(e.getAttribute("aria-label").trim()); }) || { getAttribute: function () { return ""; } }).getAttribute("aria-label"),
    endereco: depoisDoisPontos(lab('button[data-item-id="address"]')),
    localizada_em: lab('button[data-item-id="locatedin"]').replace(":", ""),
    telefone: depoisDoisPontos(lab('button[data-item-id^="phone:"]')),
    site: depoisDoisPontos(lab('a[data-item-id="authority"]')),
    plus_code: depoisDoisPontos(lab('button[data-item-id="oloc"]')),
    limitada: Array.prototype.some.call(document.querySelectorAll("span, div"), function (e) {
      return e.children.length === 0 && /visualização limitada do Google Maps/i.test(e.textContent) && e.offsetParent !== null;
    }),
    horario_funcionamento: {},
    horarios_pico: {},
    distribuicao_estrelas: {},
    topicos_avaliacoes: {},
    avaliacoes: []
  };

  main.querySelectorAll('button[aria-label*="Copiar horário"]').forEach(function (b) {
    var p = b.getAttribute("aria-label").split(",");
    if (p.length >= 2) d.horario_funcionamento[semAcento(p[0].trim())] = p[1].trim();
  });

  var grafico = main.querySelector(".C7xf8b");
  if (grafico) {
    Array.prototype.slice.call(grafico.children, 0, 7).forEach(function (bloco, i) {
      var horas = {};
      bloco.querySelectorAll("[aria-label]").forEach(function (e) {
        var m = e.getAttribute("aria-label").match(/(\d{2}):00\D+?(\d+)%/);
        if (m) horas[m[1]] = parseInt(m[2], 10);
      });
      d.horarios_pico[dias[i]] = horas;
    });
  }

  main.querySelectorAll('tr[aria-label*="estrela"]').forEach(function (tr) {
    var m = tr.getAttribute("aria-label").match(/(\d) estrelas?, ([\d.]+)/);
    if (m) d.distribuicao_estrelas[m[1]] = parseInt(m[2].replace(/\./g, ""), 10);
  });
  main.querySelectorAll('button[aria-label*="mencionado em"]').forEach(function (b) {
    var m = b.getAttribute("aria-label").match(/(.+), mencionado em ([\d.]+)/);
    if (m) d.topicos_avaliacoes[m[1]] = parseInt(m[2].replace(/\./g, ""), 10);
  });

  // Abre os textos cortados ("Mais") das avaliacoes ja carregadas
  main.querySelectorAll("button.w8nwRe").forEach(function (b) { b.click(); });

  setTimeout(function () {
    var vistos = {};
    main.querySelectorAll("div.jftiEf[data-review-id]").forEach(function (r) {
      var id = r.getAttribute("data-review-id");
      if (vistos[id]) return;
      vistos[id] = 1;
      var q = function (s) { var e = r.querySelector(s); return e ? e.innerText.trim() : ""; };
      var est = r.querySelector('span[role="img"][aria-label*="estrela"]');
      var texto = Array.prototype.find.call(r.querySelectorAll(".wiI7pd"), function (e) { return !e.closest(".CDe7pd"); });
      var resp = r.querySelector(".CDe7pd .wiI7pd") || r.querySelector(".CDe7pd");
      d.avaliacoes.push({
        id: id,
        estrelas_txt: est ? est.getAttribute("aria-label") : q(".fzvQIb"),
        data_relativa: q(".rsqaWe") || q(".xRkPPb"),
        texto: texto ? texto.innerText.trim() : "",
        resposta_proprietario: resp ? resp.innerText.trim() : "",
        local_guide: /Local Guide/i.test(q(".RfnDt")),
        fotos: r.querySelectorAll("button.Tya61d").length
      });
    });
    var nomeArq = "vitrine_" + (pid || "loja").replace(/[^0-9a-fx]/gi, "_") + "_" +
      semAcento(d.aba || "ficha").replace(/[^a-z]+/g, "-") + ".json";
    var blob = new Blob([JSON.stringify(d, null, 1)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = nomeArq;
    document.body.appendChild(a);
    a.click();
    a.remove();
    var picos = Object.keys(d.horarios_pico).length;
    alert("Salvo: " + d.nome + "\n" + "Aba: " + (d.aba || "?") + " · pico: " + picos + " dias · avaliações: " + d.avaliacoes.length +
      (d.limitada ? "\n\nAtenção: o Google mostrou a visualização limitada. Entre na sua conta Google e tente de novo." : ""));
  }, 900);
})();
