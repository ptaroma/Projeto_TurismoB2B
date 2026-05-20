async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Nao foi possivel concluir a solicitacao.");
  }
  return data;
}

function buildAirportOption(airport) {
  const option = document.createElement("option");
  option.value = `${airport.city} (${airport.iata})`;
  option.textContent = `${airport.city} (${airport.iata})`;
  return option;
}

async function loadAirports() {
  const airports = await api("/api/public/airports?limit=90");
  const selects = Array.from(document.querySelectorAll(".airport-select"));

  selects.forEach((select) => {
    select.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Selecione";
    placeholder.disabled = true;
    placeholder.selected = true;
    select.appendChild(placeholder);

    airports.forEach((airport) => {
      select.appendChild(buildAirportOption(airport));
    });
  });
}

function toggleForm(button) {
  const card = button.closest(".trip-card");
  const form = card.querySelector(".quote-form");
  form.classList.toggle("hidden");
  if (!form.classList.contains("hidden")) {
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function collectFormData(form) {
  const card = form.closest(".trip-card");
  const travelType = card.getAttribute("data-travel-type") || "turismo";
  const get = (name) => (form.elements[name]?.value || "").trim();

  return {
    travel_type: travelType,
    full_name: get("full_name"),
    contact: get("contact"),
    email: get("email"),
    origin: get("origin"),
    destination: get("destination"),
    departure_date: get("departure_date"),
    return_date: get("return_date"),
    adults: Number(get("adults") || 1),
    children: Number(get("children") || 0),
    cabin: get("cabin"),
  };
}

function openDispatchTargets(result) {
  if (result.whatsapp_url) {
    window.open(result.whatsapp_url, "_blank", "noopener,noreferrer");
  }
  if (!result.email_sent && result.mailto_url) {
    window.location.href = result.mailto_url;
  }
}

async function submitLeadForm(form) {
  const msg = form.querySelector(".form-msg");
  msg.textContent = "Enviando sua solicitacao...";
  msg.classList.remove("error");

  try {
    const payload = collectFormData(form);
    const result = await api("/api/public/lead-quote", {
      method: "POST",
      body: payload,
    });

    openDispatchTargets(result);
    msg.textContent = "Seu pedido de Cotação foi enviado com sucesso. Obrigado por confiar em nosso trabalho.";
    form.reset();
  } catch (error) {
    msg.textContent = error.message;
    msg.classList.add("error");
  }
}

function bindEvents() {
  document.querySelectorAll("[data-open-form]").forEach((button) => {
    button.addEventListener("click", () => toggleForm(button));
  });

  document.querySelectorAll(".quote-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitLeadForm(form);
    });
  });
}

async function init() {
  bindEvents();
  await loadAirports();
}

init();
