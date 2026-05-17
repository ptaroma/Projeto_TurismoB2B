const $ = (id) => document.getElementById(id);

const fmtBRL = (v) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    Number(v || 0)
  );

const state = {
  opcoes: [],
  selecionadaId: null,
};

function hojeISO() {
  return new Date().toISOString().slice(0, 10);
}

function addDias(baseISO, dias) {
  const d = new Date(`${baseISO}T12:00:00`);
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

function seedBase() {
  const origem = $("origem").value.trim().toUpperCase();
  const destino = $("destino").value.trim().toUpperCase();
  const adultos = Number($("adultos").value || 1);
  const cabine = $("cabine").value;

  let base = 850 + adultos * 320;
  if (cabine === "premium_economy") base *= 1.38;
  if (cabine === "business") base *= 2.6;
  base += (origem.charCodeAt(0) || 70) + (destino.charCodeAt(0) || 66);
  return base;
}

function gerarOpcoes() {
  const base = seedBase();
  const cias = ["G3", "LA", "AD", "2Z", "JJ"];
  const opcoes = [];

  for (let i = 0; i < 5; i += 1) {
    const fator = 0.86 + i * 0.09;
    const conexoes = i % 3;
    const preco = Math.round((base * fator + conexoes * 120) * 100) / 100;
    const voo = `${cias[i]}${1200 + i * 37}`;
    const duracao = `${2 + conexoes}h ${15 + i * 10}m`;

    opcoes.push({
      id: `sim_${Date.now()}_${i}`,
      cia: cias[i],
      voo,
      conexoes,
      duracao,
      preco,
    });
  }

  state.opcoes = opcoes.sort((a, b) => a.preco - b.preco);
  state.selecionadaId = state.opcoes[0]?.id || null;
  renderOpcoes();
}

function renderOpcoes() {
  const tbody = $("tabelaOpcoes");
  tbody.innerHTML = "";

  if (state.opcoes.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6">Sem opcoes ainda. Clique em "Gerar opcoes simuladas".</td>';
    tbody.appendChild(tr);
    return;
  }

  state.opcoes.forEach((op) => {
    const tr = document.createElement("tr");
    tr.className = "fade-in";
    tr.innerHTML = `
      <td><input type="radio" name="opcao" value="${op.id}" ${
      op.id === state.selecionadaId ? "checked" : ""
    }></td>
      <td>${op.cia}</td>
      <td>${op.voo}</td>
      <td>${op.conexoes}</td>
      <td>${op.duracao}</td>
      <td>${fmtBRL(op.preco)}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('input[name="opcao"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.selecionadaId = input.value;
    });
  });
}

function aplicarSelecionada() {
  const op = state.opcoes.find((x) => x.id === state.selecionadaId);
  if (!op) {
    alert("Nenhuma opcao selecionada.");
    return;
  }
  $("tarifaAerea").value = op.preco;
  calcularResumo();
}

function dadosCotacaoAtual() {
  const custoBase =
    Number($("tarifaAerea").value || 0) +
    Number($("hotelTotal").value || 0) +
    Number($("carroTotal").value || 0) +
    Number($("extrasTotal").value || 0) +
    Number($("taxaServico").value || 0);

  const margem = Number($("margemPct").value || 0) / 100;
  const markup = custoBase * margem;
  const valorCliente = custoBase + markup;

  const validadeHoras = Number($("validadeHoras").value || 24);
  const validade = new Date(Date.now() + validadeHoras * 60 * 60 * 1000);

  return {
    clienteEmpresa: $("clienteEmpresa").value.trim(),
    clienteConsultor: $("clienteConsultor").value.trim(),
    clienteContato: $("clienteContato").value.trim(),
    clienteEmail: $("clienteEmail").value.trim(),
    origem: $("origem").value.trim().toUpperCase(),
    destino: $("destino").value.trim().toUpperCase(),
    dataIda: $("dataIda").value,
    dataVolta: $("dataVolta").value,
    adultos: Number($("adultos").value || 1),
    cabine: $("cabine").value,
    custoBase,
    markup,
    valorCliente,
    validadeISO: validade.toISOString(),
    createdAtISO: new Date().toISOString(),
  };
}

function atualizarPreview(c) {
  const txt = [
    `PROPOSTA COMERCIAL - TURISMOB2B`,
    `Cliente: ${c.clienteEmpresa || "N/A"}`,
    `Contato: ${c.clienteContato || "N/A"} | Email: ${c.clienteEmail || "N/A"}`,
    `Consultor: ${c.clienteConsultor || "N/A"}`,
    `Rota: ${c.origem} -> ${c.destino}`,
    `Datas: ${c.dataIda || "N/A"} a ${c.dataVolta || "N/A"}`,
    `Passageiros: ${c.adultos} | Cabine: ${c.cabine}`,
    `-----------------------------------------------`,
    `Custo base: ${fmtBRL(c.custoBase)}`,
    `Markup: ${fmtBRL(c.markup)}`,
    `Valor cliente: ${fmtBRL(c.valorCliente)}`,
    `Validade: ${new Date(c.validadeISO).toLocaleString("pt-BR")}`,
    `-----------------------------------------------`,
    `Observacao: valores simulados para testes internos.`,
  ].join("\n");

  $("previewProposta").value = txt;
}

function calcularResumo() {
  const c = dadosCotacaoAtual();
  $("kpiCusto").textContent = fmtBRL(c.custoBase);
  $("kpiMarkup").textContent = fmtBRL(c.markup);
  $("kpiCliente").textContent = fmtBRL(c.valorCliente);
  $("kpiValidade").textContent = new Date(c.validadeISO).toLocaleString("pt-BR");
  atualizarPreview(c);
}

function getHistorico() {
  try {
    return JSON.parse(localStorage.getItem("tb2b_cotacoes") || "[]");
  } catch {
    return [];
  }
}

function setHistorico(lista) {
  localStorage.setItem("tb2b_cotacoes", JSON.stringify(lista));
}

function salvarCotacao() {
  const atual = dadosCotacaoAtual();
  const historico = getHistorico();
  historico.unshift(atual);
  setHistorico(historico.slice(0, 30));
  renderHistorico();
  alert("Cotacao salva no historico local.");
}

function renderHistorico() {
  const box = $("historico");
  box.innerHTML = "";
  const historico = getHistorico();

  if (historico.length === 0) {
    box.innerHTML = "<p class='muted'>Nenhuma cotacao salva ainda.</p>";
    return;
  }

  historico.forEach((item) => {
    const div = document.createElement("div");
    div.className = "historico-item";
    div.innerHTML = `
      <div>
        <b>${item.clienteEmpresa || "Sem cliente"}</b>
        <small>${item.origem} -> ${item.destino} | ${fmtBRL(item.valorCliente)}</small>
      </div>
      <small>${new Date(item.createdAtISO).toLocaleString("pt-BR")}</small>
    `;
    box.appendChild(div);
  });
}

function exportarJSON() {
  const payload = {
    geradoEm: new Date().toISOString(),
    cotacaoAtual: dadosCotacaoAtual(),
    historico: getHistorico(),
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cotacoes_turismob2b_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function limparTela() {
  [
    "clienteEmpresa",
    "clienteConsultor",
    "clienteContato",
    "clienteEmail",
    "tarifaAerea",
    "hotelTotal",
    "carroTotal",
    "extrasTotal",
  ].forEach((id) => {
    $(id).value = "";
  });

  $("taxaServico").value = "80";
  $("margemPct").value = "15";
  state.opcoes = [];
  state.selecionadaId = null;
  renderOpcoes();
  calcularResumo();
}

function bind() {
  [
    "tarifaAerea",
    "hotelTotal",
    "carroTotal",
    "extrasTotal",
    "taxaServico",
    "margemPct",
    "validadeHoras",
    "clienteEmpresa",
    "clienteConsultor",
    "clienteContato",
    "clienteEmail",
    "origem",
    "destino",
    "dataIda",
    "dataVolta",
    "adultos",
    "cabine",
  ].forEach((id) => {
    $(id).addEventListener("input", calcularResumo);
  });

  $("btnGerarOpcoes").addEventListener("click", () => {
    gerarOpcoes();
    calcularResumo();
  });

  $("btnAplicarSelecionado").addEventListener("click", aplicarSelecionada);
  $("btnSalvar").addEventListener("click", salvarCotacao);
  $("btnExportar").addEventListener("click", exportarJSON);
  $("btnLimpar").addEventListener("click", limparTela);
}

function init() {
  const hoje = hojeISO();
  $("dataIda").value = addDias(hoje, 14);
  $("dataVolta").value = addDias(hoje, 19);
  renderOpcoes();
  renderHistorico();
  bind();
  calcularResumo();
}

init();
