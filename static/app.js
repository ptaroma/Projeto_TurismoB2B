const $ = (id) => document.getElementById(id);

const fmtBRL = (v) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(v || 0));

const state = {
  token: localStorage.getItem("tb2b_token") || "",
  refreshToken: localStorage.getItem("tb2b_refresh") || "",
  user: null,
  flights: [],
  selectedFlightId: null,
  quotes: [],
};

async function refreshAccessToken() {
  if (!state.refreshToken) return false;
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) return false;

    state.token = data.access_token;
    state.refreshToken = data.refresh_token || state.refreshToken;
    localStorage.setItem("tb2b_token", state.token);
    localStorage.setItem("tb2b_refresh", state.refreshToken);
    return true;
  } catch {
    return false;
  }
}

async function api(path, { method = "GET", body, auth = true, retried = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;

  const res = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && auth && !retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return api(path, { method, body, auth, retried: true });
    }
  }

  if (!res.ok) {
    throw new Error(data.detail || "Erro na API");
  }
  return data;
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function addDays(baseISO, days) {
  const d = new Date(`${baseISO}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function showAuth(msg = "") {
  $("authView").classList.remove("hidden");
  $("appView").classList.add("hidden");
  $("authMsg").textContent = msg;
}

function showApp() {
  $("authView").classList.add("hidden");
  $("appView").classList.remove("hidden");
  $("userBox").textContent = `${state.user?.name} (${state.user?.email})`;
}

function switchAuthTab(mode) {
  const loginTab = $("tabLogin");
  const registerTab = $("tabRegister");
  const loginForm = $("loginForm");
  const registerForm = $("registerForm");

  if (mode === "login") {
    loginTab.classList.add("active");
    registerTab.classList.remove("active");
    loginForm.classList.remove("hidden");
    registerForm.classList.add("hidden");
  } else {
    registerTab.classList.add("active");
    loginTab.classList.remove("active");
    registerForm.classList.remove("hidden");
    loginForm.classList.add("hidden");
  }
  $("authMsg").textContent = "";
}

function collectQuotePayload() {
  const airfare = Number($("airfareTotal").value || 0);
  const hotel = Number($("hotelTotal").value || 0);
  const car = Number($("carTotal").value || 0);
  const extras = Number($("extrasTotal").value || 0);
  const service = Number($("serviceFee").value || 0);
  const marginPct = Number($("marginPct").value || 0);

  const baseCost = airfare + hotel + car + extras + service;
  const marginValue = (baseCost * marginPct) / 100;
  const total = baseCost + marginValue;

  return {
    client_company: $("clientCompany").value.trim(),
    client_contact: $("clientContact").value.trim(),
    client_email: $("clientEmail").value.trim(),
    consultant_name: $("consultantName").value.trim(),
    origin: $("origin").value.trim().toUpperCase(),
    destination: $("destination").value.trim().toUpperCase(),
    departure_date: $("departureDate").value,
    return_date: $("returnDate").value,
    adults: Number($("adults").value || 1),
    cabin: $("cabin").value,
    airfare_total: airfare,
    hotel_total: hotel,
    car_total: car,
    extras_total: extras,
    service_fee: service,
    margin_pct: marginPct,
    base_cost: baseCost,
    margin_value: marginValue,
    total_to_client: total,
    validity_hours: Number($("validityHours").value || 24),
    notes: $("notes").value.trim(),
  };
}

function updateSummary() {
  const p = collectQuotePayload();
  $("kpiBase").textContent = fmtBRL(p.base_cost);
  $("kpiMargin").textContent = fmtBRL(p.margin_value);
  $("kpiTotal").textContent = fmtBRL(p.total_to_client);

  const validity = new Date(Date.now() + p.validity_hours * 3600000).toLocaleString("pt-BR");
  $("kpiValidity").textContent = validity;

  $("proposalText").value = [
    "PROPOSTA COMERCIAL | TURISMOB2B",
    `Cliente: ${p.client_company || "N/A"}`,
    `Contato: ${p.client_contact || "N/A"} | Email: ${p.client_email || "N/A"}`,
    `Consultor: ${p.consultant_name || state.user?.name || "N/A"}`,
    `Rota: ${p.origin} -> ${p.destination}`,
    `Datas: ${p.departure_date || "N/A"} a ${p.return_date || "N/A"}`,
    `PAX: ${p.adults} | Cabine: ${p.cabin}`,
    "--------------------------------",
    `Custo base: ${fmtBRL(p.base_cost)}`,
    `Margem: ${fmtBRL(p.margin_value)} (${p.margin_pct.toFixed(1)}%)`,
    `Valor cliente: ${fmtBRL(p.total_to_client)}`,
    `Validade: ${validity}`,
    "--------------------------------",
    `Observacoes: ${p.notes || "-"}`,
  ].join("\n");
}

function renderFlights() {
  const tbody = $("flightTable");
  tbody.innerHTML = "";

  if (!state.flights.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6">Sem opções. Clique em "Gerar Opções".</td>';
    tbody.appendChild(tr);
    return;
  }

  state.flights.forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="radio" name="flightOpt" value="${f.id}" ${
      state.selectedFlightId === f.id ? "checked" : ""
    }></td>
      <td>${f.cia}</td>
      <td>${f.voo}</td>
      <td>${f.conexoes}</td>
      <td>${f.duracao}</td>
      <td>${fmtBRL(f.preco)}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('input[name="flightOpt"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.selectedFlightId = r.value;
    });
  });
}

async function simulateFlights() {
  const payload = {
    origin: $("origin").value.trim().toUpperCase(),
    destination: $("destination").value.trim().toUpperCase(),
    adults: Number($("adults").value || 1),
    cabin: $("cabin").value,
  };
  const data = await api("/api/flight-options/simulate", { method: "POST", body: payload });
  state.flights = data;
  state.selectedFlightId = data[0]?.id || null;
  renderFlights();
}

function applySelectedFlight() {
  const item = state.flights.find((f) => f.id === state.selectedFlightId);
  if (!item) {
    alert("Selecione uma opção de voo primeiro.");
    return;
  }
  $("airfareTotal").value = item.preco;
  updateSummary();
}

function quoteCardHtml(q) {
  const p = q.payload || {};
  return `
    <div class="quote-item">
      <div>
        <b>${q.quote_name}</b>
        <small>${p.client_company || "Sem cliente"} | ${p.origin || "-"} -> ${p.destination || "-"} | ${fmtBRL(q.total_to_client)}</small><br>
        <small>${new Date(q.created_at).toLocaleString("pt-BR")}</small>
      </div>
      <div class="quote-actions">
        <button class="btn btn-secondary" data-load="${q.id}" type="button">Carregar</button>
        <button class="btn btn-ghost" data-del="${q.id}" type="button">Excluir</button>
      </div>
    </div>
  `;
}

function fillFormFromPayload(p) {
  $("clientCompany").value = p.client_company || "";
  $("clientContact").value = p.client_contact || "";
  $("clientEmail").value = p.client_email || "";
  $("consultantName").value = p.consultant_name || state.user?.name || "";
  $("origin").value = (p.origin || "GRU").toUpperCase();
  $("destination").value = (p.destination || "BSB").toUpperCase();
  $("departureDate").value = p.departure_date || "";
  $("returnDate").value = p.return_date || "";
  $("adults").value = p.adults || 1;
  $("cabin").value = p.cabin || "economy";
  $("airfareTotal").value = p.airfare_total || 0;
  $("hotelTotal").value = p.hotel_total || 0;
  $("carTotal").value = p.car_total || 0;
  $("extrasTotal").value = p.extras_total || 0;
  $("serviceFee").value = p.service_fee || 0;
  $("marginPct").value = p.margin_pct || 15;
  $("validityHours").value = p.validity_hours || 24;
  $("notes").value = p.notes || "";
  updateSummary();
}

async function loadQuotes() {
  const list = await api("/api/quotes", { auth: true });
  state.quotes = list;

  const box = $("quotesList");
  if (!list.length) {
    box.innerHTML = "<p class='muted'>Nenhuma cotação salva ainda.</p>";
    return;
  }

  box.innerHTML = list.map(quoteCardHtml).join("");

  box.querySelectorAll("[data-load]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-load"));
      const q = state.quotes.find((x) => x.id === id);
      if (!q) return;
      $("quoteName").value = q.quote_name;
      fillFormFromPayload(q.payload);
    });
  });

  box.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-del"));
      if (!confirm("Excluir esta cotação?")) return;
      await api(`/api/quotes/${id}`, { method: "DELETE" });
      await loadQuotes();
    });
  });
}

async function saveQuote() {
  const quoteName = $("quoteName").value.trim();
  if (!quoteName) {
    alert("Informe o nome da cotação.");
    return;
  }

  const payload = collectQuotePayload();
  await api("/api/quotes", {
    method: "POST",
    body: { quote_name: quoteName, payload },
  });

  await loadQuotes();
  alert("Cotação salva com sucesso.");
}

async function handleLogin(email, password) {
  const data = await api("/api/auth/login", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
  state.token = data.access_token || data.token;
  state.refreshToken = data.refresh_token || "";
  state.user = data.user;
  localStorage.setItem("tb2b_token", state.token);
  localStorage.setItem("tb2b_refresh", state.refreshToken);
}

async function handleRegister(name, email, password) {
  const data = await api("/api/auth/register", {
    method: "POST",
    auth: false,
    body: { name, email, password },
  });
  state.token = data.access_token || data.token;
  state.refreshToken = data.refresh_token || "";
  state.user = data.user;
  localStorage.setItem("tb2b_token", state.token);
  localStorage.setItem("tb2b_refresh", state.refreshToken);
}

async function initSession() {
  if (!state.token && !state.refreshToken) return false;

  if (!state.token && state.refreshToken) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) return false;
  }

  try {
    const me = await api("/api/auth/me");
    state.user = me;
    return true;
  } catch {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      localStorage.removeItem("tb2b_token");
      localStorage.removeItem("tb2b_refresh");
      state.token = "";
      state.refreshToken = "";
      return false;
    }

    const me = await api("/api/auth/me");
    state.user = me;
    return true;
  }
}

async function logout() {
  try {
    await api("/api/auth/logout", {
      method: "POST",
      body: { refresh_token: state.refreshToken || null },
    });
  } catch {
    // noop
  }
  state.token = "";
  state.refreshToken = "";
  state.user = null;
  localStorage.removeItem("tb2b_token");
  localStorage.removeItem("tb2b_refresh");
  showAuth("Sessão encerrada.");
}

function bindAuth() {
  $("tabLogin").addEventListener("click", () => switchAuthTab("login"));
  $("tabRegister").addEventListener("click", () => switchAuthTab("register"));

  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("authMsg").textContent = "";
    try {
      await handleLogin($("loginEmail").value.trim(), $("loginPassword").value);
      showApp();
      await loadQuotes();
      updateSummary();
    } catch (err) {
      $("authMsg").textContent = err.message;
    }
  });

  $("registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("authMsg").textContent = "";
    try {
      await handleRegister(
        $("registerName").value.trim(),
        $("registerEmail").value.trim(),
        $("registerPassword").value
      );
      showApp();
      $("consultantName").value = state.user.name;
      await loadQuotes();
      updateSummary();
    } catch (err) {
      $("authMsg").textContent = err.message;
    }
  });
}

function bindApp() {
  [
    "clientCompany",
    "clientContact",
    "clientEmail",
    "consultantName",
    "origin",
    "destination",
    "departureDate",
    "returnDate",
    "adults",
    "cabin",
    "airfareTotal",
    "hotelTotal",
    "carTotal",
    "extrasTotal",
    "serviceFee",
    "marginPct",
    "validityHours",
    "notes",
  ].forEach((id) => {
    $(id).addEventListener("input", updateSummary);
  });

  $("simulateBtn").addEventListener("click", async () => {
    try {
      await simulateFlights();
    } catch (err) {
      alert(err.message);
    }
  });

  $("applySelectedBtn").addEventListener("click", applySelectedFlight);
  $("saveQuoteBtn").addEventListener("click", async () => {
    try {
      await saveQuote();
    } catch (err) {
      alert(err.message);
    }
  });

  $("logoutBtn").addEventListener("click", logout);
}

async function init() {
  bindAuth();
  bindApp();

  const base = todayISO();
  $("departureDate").value = addDays(base, 14);
  $("returnDate").value = addDays(base, 19);

  const ok = await initSession();
  if (!ok) {
    showAuth("");
    return;
  }

  showApp();
  $("consultantName").value = state.user.name;
  await loadQuotes();
  updateSummary();
}

init();
