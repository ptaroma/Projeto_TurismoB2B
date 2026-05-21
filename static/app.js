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
  option.label = `${airport.city} (${airport.iata}) - ${airport.name}`;
  return option;
}

function debounce(fn, waitMs) {
  let timer = null;
  return (...args) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => fn(...args), waitMs);
  };
}

function fillDatalist(datalist, airports) {
  datalist.innerHTML = "";
  airports.forEach((airport) => {
    datalist.appendChild(buildAirportOption(airport));
  });
}

async function loadAirports() {
  const airportInputs = Array.from(document.querySelectorAll(".airport-input"));
  if (!airportInputs.length) {
    return;
  }

  const initialAirports = await api("/api/public/airports?limit=5000");

  airportInputs.forEach((input, index) => {
    const datalist = document.createElement("datalist");
    datalist.id = `airports-list-${index + 1}`;
    input.setAttribute("list", datalist.id);
    input.insertAdjacentElement("afterend", datalist);

    fillDatalist(datalist, initialAirports);

    const refreshOptions = debounce(async () => {
      const query = input.value.trim();
      if (!query) {
        fillDatalist(datalist, initialAirports);
        return;
      }
      const encoded = encodeURIComponent(query);
      const airports = await api(`/api/public/airports?q=${encoded}&limit=120`);
      fillDatalist(datalist, airports);
    }, 220);

    input.addEventListener("input", () => {
      refreshOptions().catch(() => {
        fillDatalist(datalist, initialAirports);
      });
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

async function submitLeadForm(form) {
  const msg = form.querySelector(".form-msg");
  msg.textContent = "Enviando sua solicitacao...";
  msg.classList.remove("error", "success", "warning");

  try {
    const payload = collectFormData(form);
    const result = await api("/api/public/lead-quote", {
      method: "POST",
      body: payload,
    });

    if (result.email_sent) {
      msg.innerHTML = `<span class="msg-icon" aria-hidden="true">✔</span><span>${result.client_message}</span>`;
      msg.classList.add("success");
    } else {
      msg.innerHTML = `<span class="msg-icon" aria-hidden="true">!</span><span>${result.client_message}</span>`;
      msg.classList.add("warning");
    }
    form.reset();
  } catch (error) {
    msg.textContent = error.message;
    msg.classList.remove("success", "warning");
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
