// Game board controller.

const state = {
  round: 1,
  teams: [],
  currentQuestion: null,
  selectedScoreTeamId: null,
  wagerTeamId: null,
  marking: false,
};

const ROUND_NAMES = { 1: "Jeopardy!", 2: "Double Jeopardy!", 3: "Final Jeopardy!" };

const boardGrid = document.getElementById("board-grid");
const scoreboardEl = document.getElementById("scoreboard");
const roundTitle = document.getElementById("round-title");

const modalBackdrop = document.getElementById("modal-backdrop");
const modalCategory = document.getElementById("modal-category");
const modalValue = document.getElementById("modal-value");
const ddBanner = document.getElementById("daily-double-banner");
const wagerStep = document.getElementById("wager-step");
const wagerTeamRow = document.getElementById("wager-team-row");
const wagerInput = document.getElementById("wager-input");
const qaStep = document.getElementById("qa-step");
const modalQuestion = document.getElementById("modal-question");
const modalAnswer = document.getElementById("modal-answer");
const revealBtn = document.getElementById("reveal-btn");
const scoringStep = document.getElementById("scoring-step");
const scoreTeamRow = document.getElementById("score-team-row");
const markCorrectBtn = document.getElementById("mark-correct-btn");
const markWrongBtn = document.getElementById("mark-wrong-btn");

async function loadTeams() {
  const data = await apiGet("/api/teams");
  state.teams = data.teams;
  renderScoreboard();
}

function renderScoreboard() {
  scoreboardEl.innerHTML = "";
  for (const team of state.teams) {
    const card = document.createElement("div");
    card.className = "team-card";

    const nameInput = document.createElement("input");
    nameInput.className = "team-name";
    nameInput.value = team.name;
    nameInput.addEventListener("change", async () => {
      await apiPut(`/api/teams/${team.id}`, { name: nameInput.value });
      showToast("Team renamed");
    });

    const scoreEl = document.createElement("div");
    scoreEl.className = "team-score";
    scoreEl.textContent = team.score;

    const actions = document.createElement("div");
    actions.className = "team-actions";

    const minus = document.createElement("button");
    minus.className = "btn secondary";
    minus.textContent = "-100";
    minus.addEventListener("click", async () => {
      const res = await apiPost(`/api/teams/${team.id}/score`, { delta: -100 });
      updateTeamLocal(res.team);
    });

    const plus = document.createElement("button");
    plus.className = "btn secondary";
    plus.textContent = "+100";
    plus.addEventListener("click", async () => {
      const res = await apiPost(`/api/teams/${team.id}/score`, { delta: 100 });
      updateTeamLocal(res.team);
    });

    const remove = document.createElement("button");
    remove.className = "btn danger";
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      if (!confirm(`Remove ${team.name}?`)) return;
      await apiDelete(`/api/teams/${team.id}`);
      await loadTeams();
    });

    actions.appendChild(minus);
    actions.appendChild(plus);
    actions.appendChild(remove);

    card.appendChild(nameInput);
    card.appendChild(scoreEl);
    card.appendChild(actions);
    scoreboardEl.appendChild(card);
  }

  const addCard = document.createElement("div");
  addCard.className = "team-card";
  const addBtn = document.createElement("button");
  addBtn.className = "btn";
  addBtn.textContent = "+ Add Team";
  addBtn.addEventListener("click", async () => {
    await apiPost("/api/teams", { name: `Team ${state.teams.length + 1}` });
    await loadTeams();
  });
  addCard.appendChild(addBtn);
  scoreboardEl.appendChild(addCard);
}

function updateTeamLocal(team) {
  const idx = state.teams.findIndex((t) => t.id === team.id);
  if (idx >= 0) state.teams[idx] = team;
  renderScoreboard();
}

async function loadBoard() {
  const data = await apiGet(`/api/board?round=${state.round}`);
  state.round = data.round;
  roundTitle.textContent = ROUND_NAMES[state.round] || "Jeopardy!";
  renderBoard(data.categories);
}

function renderBoard(categories) {
  boardGrid.innerHTML = "";
  const numCats = categories.length || 1;
  boardGrid.style.gridTemplateColumns = `repeat(${numCats}, 1fr)`;

  const maxRows = Math.max(0, ...categories.map((c) => c.questions.length));

  // header row
  for (const cat of categories) {
    const header = document.createElement("div");
    header.className = "category-header";
    header.textContent = cat.name;
    boardGrid.appendChild(header);
  }

  for (let r = 0; r < maxRows; r++) {
    for (const cat of categories) {
      const q = cat.questions[r];
      const cell = document.createElement("div");
      if (!q) {
        cell.className = "cell used";
        boardGrid.appendChild(cell);
        continue;
      }
      cell.className = "cell " + (q.used ? "used" : "available");
      cell.textContent = q.used ? "" : `$${q.value}`;
      if (!q.used) {
        cell.addEventListener("click", () => openQuestion(q.id));
      }
      boardGrid.appendChild(cell);
    }
  }
}

async function openQuestion(questionId) {
  const q = await apiGet(`/api/question/${questionId}`);
  state.currentQuestion = q;
  state.selectedScoreTeamId = null;
  state.wagerTeamId = null;

  modalCategory.textContent = q.category;
  modalValue.textContent = `$${q.value}`;

  modalAnswer.classList.add("hidden");
  scoringStep.classList.add("hidden");
  markCorrectBtn.disabled = true;
  markWrongBtn.disabled = true;

  if (q.is_daily_double) {
    ddBanner.classList.remove("hidden");
    wagerStep.classList.remove("hidden");
    qaStep.classList.add("hidden");
    buildTeamRow(wagerTeamRow, (teamId) => {
      state.wagerTeamId = teamId;
      [...wagerTeamRow.children].forEach((b) =>
        b.classList.toggle("selected", Number(b.dataset.teamId) === teamId)
      );
    });
    const team = state.teams[0];
    wagerInput.value = team ? Math.max(team.score, 100) : 100;
  } else {
    ddBanner.classList.add("hidden");
    wagerStep.classList.add("hidden");
    qaStep.classList.remove("hidden");
    renderRichText(modalQuestion, q.question_text, { color: "#FFFFFF" });
  }

  modalBackdrop.classList.remove("hidden");
}

function buildTeamRow(rowEl, onPick) {
  rowEl.innerHTML = "";
  for (const team of state.teams) {
    const btn = document.createElement("button");
    btn.className = "team-pick-btn";
    btn.textContent = team.name;
    btn.dataset.teamId = team.id;
    btn.addEventListener("click", () => onPick(team.id));
    rowEl.appendChild(btn);
  }
}

document.getElementById("wager-confirm-btn").addEventListener("click", () => {
  if (!state.wagerTeamId) {
    showToast("Pick the team that found the Daily Double first");
    return;
  }
  const wager = parseInt(wagerInput.value, 10) || 0;
  state.currentQuestion.wager = wager;
  wagerStep.classList.add("hidden");
  qaStep.classList.remove("hidden");
  renderRichText(modalQuestion, state.currentQuestion.question_text, { color: "#FFFFFF" });
});

revealBtn.addEventListener("click", () => {
  renderRichText(modalAnswer, state.currentQuestion.answer_text, { color: "#FFD700" });
  modalAnswer.classList.remove("hidden");
  scoringStep.classList.remove("hidden");
  buildTeamRow(scoreTeamRow, (teamId) => {
    state.selectedScoreTeamId = teamId;
    [...scoreTeamRow.children].forEach((b) =>
      b.classList.toggle("selected", Number(b.dataset.teamId) === teamId)
    );
    markCorrectBtn.disabled = false;
    markWrongBtn.disabled = false;
  });
});

async function submitMark(correct) {
  if (!state.selectedScoreTeamId || !state.currentQuestion || state.marking) return;
  state.marking = true;
  markCorrectBtn.disabled = true;
  markWrongBtn.disabled = true;
  const body = { team_id: state.selectedScoreTeamId, correct };
  if (state.currentQuestion.is_daily_double) {
    body.wager = state.currentQuestion.wager;
  }
  try {
    const res = await apiPost(`/api/question/${state.currentQuestion.id}/mark`, body);
    updateTeamLocal(res.team);
    closeModal();
    await loadBoard();
  } catch (e) {
    showToast(e.message || "Failed to record answer");
    await loadBoard();
  } finally {
    state.marking = false;
  }
}

markCorrectBtn.addEventListener("click", () => submitMark(true));
markWrongBtn.addEventListener("click", () => submitMark(false));

document.getElementById("close-modal-btn").addEventListener("click", closeModal);

function closeModal() {
  modalBackdrop.classList.add("hidden");
  state.currentQuestion = null;
}

async function setRound(roundNum) {
  state.round = roundNum;
  await apiPost("/api/round", { round: roundNum });
  await loadBoard();
}

document.getElementById("round1-btn").addEventListener("click", () => setRound(1));
document.getElementById("round2-btn").addEventListener("click", () => setRound(2));
document.getElementById("round3-btn").addEventListener("click", () => setRound(3));
document.getElementById("editor-link").addEventListener("click", () => {
  window.location.href = "/editor";
});

document.getElementById("reset-btn").addEventListener("click", async () => {
  const choice = prompt(
    "Type: 'scores' to reset scores only, 'board' to re-cover all questions, or 'full' to reset everything.",
    "full"
  );
  if (!choice) return;
  const normalized = choice.trim().toLowerCase();
  if (!["scores", "board", "full"].includes(normalized)) {
    showToast("No changes made");
    return;
  }
  if (!confirm(`This will reset ${normalized}. Continue?`)) return;
  await apiPost(`/api/reset/${normalized}`, {});
  await loadTeams();
  await loadBoard();
  showToast("Reset complete");
});

async function init() {
  const roundsInfo = await apiGet("/api/rounds");
  state.round = roundsInfo.current_round || 1;
  await loadTeams();
  await loadBoard();
}

init();
