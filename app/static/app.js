const eventSelect = document.querySelector("#event-select");
const eventHeader = document.querySelector("#event-header");
const boutsContainer = document.querySelector("#bouts");
const shareButton = document.querySelector("#share-button");
const gradeButton = document.querySelector("#grade-button");
const message = document.querySelector("#message");
const score = document.querySelector("#score");

let currentEvent = null;
let picks = {};
let gradeResults = {};

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function selectedPickCount() {
  return Object.keys(picks).length;
}

function updateControls() {
  const count = selectedPickCount();
  shareButton.disabled = !currentEvent || count === 0;
  gradeButton.disabled = !currentEvent || count === 0;
}

function showPickCount() {
  setMessage(`${selectedPickCount()} of ${currentEvent.bouts.length} bouts picked`);
}

function renderScore(report) {
  const { wins, losses, pending, void: voidCount, percentage } = report.summary;
  score.replaceChildren();
  [
    `${wins} W`,
    `${losses} L`,
    `${pending} pending`,
    `${voidCount} void`,
    percentage === null ? null : `${percentage}%`,
  ]
    .filter(Boolean)
    .forEach((text) => {
      const item = document.createElement("span");
      item.textContent = text;
      score.append(item);
    });
  score.hidden = false;
}

function renderEvent() {
  eventHeader.hidden = false;
  eventHeader.replaceChildren();
  const title = document.createElement("h2");
  title.textContent = currentEvent.name;
  const meta = document.createElement("p");
  meta.className = "event-meta";
  meta.textContent = `${new Date(currentEvent.date).toLocaleString()} · ${currentEvent.status}`;
  eventHeader.append(title, meta);

  boutsContainer.replaceChildren();
  currentEvent.bouts.forEach((bout) => {
    const card = document.createElement("article");
    card.className = "bout";

    const info = document.createElement("div");
    info.className = "bout-info";
    const number = document.createElement("p");
    number.className = "bout-number";
    number.textContent = `Bout ${bout.order}`;
    const weight = document.createElement("p");
    weight.className = "bout-weight";
    weight.textContent = bout.weight_class || "MMA";
    info.append(number, weight);

    const fighters = document.createElement("div");
    fighters.className = "fighters";
    bout.fighters.forEach((fighter) => {
      const button = document.createElement("button");
      button.className = "fighter";
      button.type = "button";
      button.dataset.fighterId = fighter.id;
      const name = document.createElement("strong");
      name.className = "fighter-name";
      name.textContent = fighter.name;
      const record = document.createElement("span");
      record.className = "fighter-record";
      record.textContent = [fighter.record, fighter.country].filter(Boolean).join(" · ");
      button.append(name, record);

      if (picks[bout.id] === fighter.id) button.classList.add("selected");
      const result = gradeResults[bout.id];
      if (result?.winner_id === fighter.id) button.classList.add("correct");
      if (result?.result === "loss" && picks[bout.id] === fighter.id) {
        button.classList.add("incorrect");
      }

      button.addEventListener("click", () => {
        picks[bout.id] = fighter.id;
        gradeResults = {};
        score.hidden = true;
        renderEvent();
        updateControls();
        showPickCount();
      });
      fighters.append(button);
    });

    card.append(info, fighters);
    boutsContainer.append(card);
  });
}

async function loadEvent(eventId, sharedPickToken = null) {
  setMessage("Loading fight card...");
  score.hidden = true;
  gradeResults = {};
  try {
    currentEvent = await api(`/api/events/${encodeURIComponent(eventId)}`);
    let sharedPicks = {};
    if (sharedPickToken) {
      sharedPicks = PickCodec.decode(currentEvent, sharedPickToken);
    }
    const validPicks = Object.fromEntries(
      Object.entries(sharedPicks).filter(([boutId, fighterId]) => {
        const bout = currentEvent.bouts.find((candidate) => candidate.id === boutId);
        return bout?.fighters.some((fighter) => fighter.id === fighterId);
      }),
    );
    picks = validPicks;
    if (![...eventSelect.options].some((option) => option.value === eventId)) {
      const option = document.createElement("option");
      option.value = currentEvent.id;
      option.textContent = `${new Date(currentEvent.date).toLocaleDateString()} — ${currentEvent.name}`;
      eventSelect.prepend(option);
    }
    eventSelect.value = eventId;
    renderEvent();
    updateControls();
    showPickCount();
    if (sharedPickToken && currentEvent.completed && selectedPickCount() > 0) {
      await gradePicks();
    }
  } catch (error) {
    setMessage(error.message, true);
  }
}

async function gradePicks() {
  gradeButton.disabled = true;
  setMessage("Grading picks...");
  try {
    const report = await api(`/api/events/${encodeURIComponent(currentEvent.id)}/grade`, {
      method: "POST",
      body: JSON.stringify({ picks }),
    });
    gradeResults = Object.fromEntries(report.results.map((result) => [result.bout_id, result]));
    renderEvent();
    renderScore(report);
    setMessage("Picks graded against the latest official results.");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    updateControls();
  }
}

eventSelect.addEventListener("change", () => loadEvent(eventSelect.value));
gradeButton.addEventListener("click", gradePicks);
shareButton.addEventListener("click", async () => {
  const url = new URL(window.location.href);
  url.search = "";
  url.searchParams.set("event", currentEvent.id);
  url.searchParams.set("p", PickCodec.encode(currentEvent, picks));
  try {
    await navigator.clipboard.writeText(url.toString());
    window.history.replaceState({}, "", url);
    setMessage("Share link copied to the clipboard.");
  } catch {
    window.history.replaceState({}, "", url);
    setMessage("Share link added to the address bar; copy it from there.");
  }
});

async function initialize() {
  try {
    const events = await api("/api/events");
    if (!events.length) {
      throw new Error("No UFC events found in the current window.");
    }

    eventSelect.replaceChildren();
    events.forEach((event) => {
      const option = document.createElement("option");
      option.value = event.id;
      option.textContent = `${new Date(event.date).toLocaleDateString()} — ${event.name}`;
      eventSelect.append(option);
    });
    eventSelect.disabled = false;

    const params = new URLSearchParams(window.location.search);
    const requestedEvent = params.get("event");
    const selectedEvent =
      requestedEvent || events.find((event) => !event.completed)?.id || events.at(-1).id;
    await loadEvent(selectedEvent, params.get("p"));
  } catch (error) {
    setMessage(error.message, true);
  }
}

initialize();
