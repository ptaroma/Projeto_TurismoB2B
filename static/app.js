const $ = (id) => document.getElementById(id);

const fmtBRL = (v) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(v || 0));

const state = {
  token: localStorage.getItem("tb2b_token") || "",
  refreshToken: localStorage.getItem("tb2b_refresh") || "",
  user: null,
  flights: [],
  selectedFlightId: null,
  hotels: [],
  selectedHotelId: null,
  cars: [],
  selectedCarId: null,
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

function getTripNights() {
  const departure = $("departureDate").value;
  const ret = $("returnDate").value;
  if (!departure || !ret) return 1;

  const d1 = new Date(`${departure}T12:00:00`);
  const d2 = new Date(`${ret}T12:00:00`);
  const diffMs = d2.getTime() - d1.getTime();
  const nights = Math.ceil(diffMs / 86400000);
  return Math.max(1, nights);
}

function renderHotels() {
  const tbody = $("hotelTable");
  tbody.innerHTML = "";

  if (!state.hotels.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6">Sem opções. Clique em "Gerar Opções".</td>';
    tbody.appendChild(tr);
    return;
  }

  state.hotels.forEach((h) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="radio" name="hotelOpt" value="${h.id}" ${
      state.selectedHotelId === h.id ? "checked" : ""
    }></td>
      <td>${h.hotel}</td>
      <td>${h.diarias}</td>
      <td>${h.regime}</td>
      <td>${h.categoria}</td>
      <td>${fmtBRL(h.preco)}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('input[name="hotelOpt"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.selectedHotelId = r.value;
    });
  });
}

function simulateHotels() {
  const destination = $("destination").value.trim().toUpperCase() || "BSB";
  const adults = Number($("adults").value || 1);
  const nights = getTripNights();

  const destinationFactor = destination.charCodeAt(0) % 5;
  const baseDaily = 220 + adults * 45 + destinationFactor * 20;
  const templates = [
    { hotel: "Urban Stay", categoria: "3*", regime: "Sem cafe", factor: 1.0 },
    { hotel: "Prime Comfort", categoria: "4*", regime: "Cafe incluso", factor: 1.28 },
    { hotel: "Signature Suites", categoria: "5*", regime: "Meia pensao", factor: 1.65 },
    { hotel: "Business Hub", categoria: "4*", regime: "Cafe incluso", factor: 1.18 },
    { hotel: "Boutique Select", categoria: "4*", regime: "Sem cafe", factor: 1.1 },
  ];

  state.hotels = templates.map((t, i) => ({
    id: `hotel_${i + 1}`,
    hotel: t.hotel,
    categoria: t.categoria,
    regime: t.regime,
    diarias: nights,
    preco: Number((baseDaily * nights * t.factor).toFixed(2)),
  }));
  state.hotels.sort((a, b) => a.preco - b.preco);
  state.selectedHotelId = state.hotels[0]?.id || null;
  renderHotels();
}

function applySelectedHotel() {
  const item = state.hotels.find((h) => h.id === state.selectedHotelId);
  if (!item) {
    alert("Selecione uma opção de hospedagem primeiro.");
    return;
  }
  $("hotelTotal").value = item.preco;
  updateSummary();
}

function renderCars() {
  const tbody = $("carTable");
  tbody.innerHTML = "";

  if (!state.cars.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6">Sem opções. Clique em "Gerar Opções".</td>';
    tbody.appendChild(tr);
    return;
  }

  state.cars.forEach((c) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="radio" name="carOpt" value="${c.id}" ${
      state.selectedCarId === c.id ? "checked" : ""
    }></td>
      <td>${c.locadora}</td>
      <td>${c.modelo}</td>
      <td>${c.categoria}</td>
      <td>${c.diarias}</td>
      <td>${fmtBRL(c.preco)}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('input[name="carOpt"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.selectedCarId = r.value;
    });
  });
}

function simulateCars() {
  const adults = Number($("adults").value || 1);
  const nights = getTripNights();
  const destination = $("destination").value.trim().toUpperCase() || "BSB";
  const destinationFactor = destination.charCodeAt(1) % 4;
  const baseDaily = 95 + adults * 18 + destinationFactor * 12;

  const templates = [
    { locadora: "Localiza", modelo: "Onix", categoria: "Economico", factor: 1.0 },
    { locadora: "Movida", modelo: "HB20", categoria: "Compacto", factor: 1.12 },
    { locadora: "Unidas", modelo: "Corolla", categoria: "Sedan", factor: 1.54 },
    { locadora: "Foco", modelo: "Renegade", categoria: "SUV", factor: 1.72 },
    { locadora: "Enterprise", modelo: "Compass", categoria: "SUV Premium", factor: 1.96 },
  ];

  state.cars = templates.map((t, i) => ({
    id: `car_${i + 1}`,
    locadora: t.locadora,
    modelo: t.modelo,
    categoria: t.categoria,
    diarias: nights,
    preco: Number((baseDaily * nights * t.factor).toFixed(2)),
  }));
  state.cars.sort((a, b) => a.preco - b.preco);
  state.selectedCarId = state.cars[0]?.id || null;
  renderCars();
}

function applySelectedCar() {
  const item = state.cars.find((c) => c.id === state.selectedCarId);
  if (!item) {
    alert("Selecione uma opção de carro primeiro.");
    return;
  }
  $("carTotal").value = item.preco;
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

  $("simulateFlightBtn").addEventListener("click", async () => {
    try {
      await simulateFlights();
    } catch (err) {
      alert(err.message);
    }
  });

  $("applyFlightBtn").addEventListener("click", applySelectedFlight);
  $("simulateHotelBtn").addEventListener("click", simulateHotels);
  $("applyHotelBtn").addEventListener("click", applySelectedHotel);
  $("simulateCarBtn").addEventListener("click", simulateCars);
  $("applyCarBtn").addEventListener("click", applySelectedCar);
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
  renderFlights();
  renderHotels();
  renderCars();

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
