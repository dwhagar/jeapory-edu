// Game board controller.
//
// Drives the teacher-facing display: the scoreboard, the clickable board
// grid, and the question/answer modal (including the daily-double wager
// step). All game state lives server-side; this file just reflects it and
// posts the actions a click represents.

const state = {
  round: 1,              // current round number (1, 2, or 3/Final)
  teams: [],              // last-fetched team rows, kept in sync via updateTeamLocal
  currentQuestion: null,  // the question object shown in the open modal, or null
  wagerTeamId: null,      // team id selected during a daily-double wager step
  marking: false,         // true while a mark-question request is in flight (prevents double-submits)
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
const teamScoreRow = document.getElementById("team-score-row");

/** Fetch the current teams from the server and re-render the scoreboard. */
async function loadTeams() {
  const data = await apiGet("/api/teams");
  state.teams = data.teams;
  renderScoreboard();
}

/** Rebuild the scoreboard: one card per team (name, score, +/-/edit/remove) plus an "Add Team" card. */
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

    const edit = document.createElement("button");
    edit.className = "btn secondary";
    edit.textContent = "Edit";
    edit.addEventListener("click", async () => {
      const entered = prompt(`Set score for ${team.name}:`, team.score);
      if (entered === null) return;
      const newScore = parseInt(entered, 10);
      if (Number.isNaN(newScore)) {
        showToast("Enter a whole number");
        return;
      }
      const res = await apiPut(`/api/teams/${team.id}`, { score: newScore });
      updateTeamLocal(res.team);
      showToast("Score updated");
    });

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
    actions.appendChild(edit);
    actions.appendChild(remove);

    card.appendChild(nameInput);
    card.appendChild(scoreEl);
    card.appendChild(actions);
    scoreboardEl.appendChild(card);
  }

  const addCard = document.createElement("div");
  addCard.className = "team-card add-team-card";
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

/** Patch a single team's row into local state (from an API response) and re-render, avoiding a full refetch. */
function updateTeamLocal(team) {
  const idx = state.teams.findIndex((t) => t.id === team.id);
  if (idx >= 0) state.teams[idx] = team;
  renderScoreboard();
}

/** Fetch the board (categories + question cells) for the current round and render it. */
async function loadBoard() {
  const data = await apiGet(`/api/board?round=${state.round}`);
  state.round = data.round;
  roundTitle.textContent = ROUND_NAMES[state.round] || "Jeopardy!";
  renderBoard(data.categories);
}

/**
 * Render the category header row and the grid of value cells beneath it.
 * A cell shows its dollar value and is clickable while unused; once used it
 * renders blank and inert. Categories with fewer questions than the tallest
 * one get blank filler cells so the grid stays rectangular.
 */
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

/**
 * Open the question modal for a clicked cell. A regular question goes
 * straight to the question/answer step; a daily double first shows the
 * wager step (pick the finding team, enter a wager) before revealing the clue.
 */
async function openQuestion(questionId) {
  const q = await apiGet(`/api/question/${questionId}`);
  state.currentQuestion = q;
  state.wagerTeamId = null;

  modalCategory.textContent = q.category;
  modalValue.textContent = `$${q.value}`;

  modalAnswer.classList.add("hidden");
  scoringStep.classList.add("hidden");
  teamScoreRow.innerHTML = "";

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
  document.body.classList.add("modal-open");
}

/** Fill `rowEl` with one button per team; clicking a button calls `onPick(teamId)`. */
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

// Confirm the daily-double wager: stash it on the current question and
// advance from the wager step to the question/answer step.
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

// Reveal the answer text and expose the per-team scoring buttons.
revealBtn.addEventListener("click", () => {
  renderRichText(modalAnswer, state.currentQuestion.answer_text, { color: "#FFD700" });
  modalAnswer.classList.remove("hidden");
  scoringStep.classList.remove("hidden");
  renderTeamScoreButtons();
});

/** Build one +/- scoring card per team, worth the question's value (or the daily-double wager). */
function renderTeamScoreButtons() {
  teamScoreRow.innerHTML = "";
  const q = state.currentQuestion;
  const points = q.is_daily_double ? q.wager : q.value;
  for (const team of state.teams) {
    const card = document.createElement("div");
    card.className = "team-score-card";

    const name = document.createElement("div");
    name.className = "team-score-card-name";
    name.textContent = team.name;

    const buttons = document.createElement("div");
    buttons.className = "team-score-card-buttons";

    const plus = document.createElement("button");
    plus.className = "btn success";
    plus.textContent = `+ $${points}`;
    plus.addEventListener("click", () => submitMark(team.id, true));

    const minus = document.createElement("button");
    minus.className = "btn danger";
    minus.textContent = `- $${points}`;
    minus.addEventListener("click", () => submitMark(team.id, false));

    buttons.appendChild(plus);
    buttons.appendChild(minus);
    card.appendChild(name);
    card.appendChild(buttons);
    teamScoreRow.appendChild(card);
  }
}

/**
 * Record correct/incorrect for the given team on the currently open
 * question, then close the modal and refresh the board. Guards against
 * double-submission via state.marking, since scoring buttons don't disable
 * synchronously before the network round-trip completes.
 */
async function submitMark(teamId, correct) {
  if (!teamId || !state.currentQuestion || state.marking) return;
  state.marking = true;
  [...teamScoreRow.querySelectorAll("button")].forEach((b) => (b.disabled = true));
  const body = { team_id: teamId, correct };
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

document.getElementById("close-modal-btn").addEventListener("click", closeModal);

/** Hide the question modal and forget the currently-open question. */
function closeModal() {
  modalBackdrop.classList.add("hidden");
  document.body.classList.remove("modal-open");
  state.currentQuestion = null;
}

/** Switch to a different round both on the server (so it persists) and locally, then reload the board. */
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

// Undo the most recent reversible server-side action (see server.py's
// set_undo/pop_undo) and refresh both the scoreboard and the board to
// reflect the reverted state.
document.getElementById("undo-btn").addEventListener("click", async () => {
  try {
    const res = await apiPost("/api/undo", {});
    showToast(`Undid ${res.label}`);
    await loadTeams();
    await loadBoard();
  } catch (e) {
    showToast(e.message || "Nothing to undo");
  }
});

document.getElementById("db-btn").addEventListener("click", () => showDatabaseModal(false));

// Reset flow: ask which of the four reset scopes to apply (scores/teams/
// board/full), confirm, then hit the matching /api/reset/<scope> endpoint.
document.getElementById("reset-btn").addEventListener("click", async () => {
  const choice = prompt(
    "Type: 'scores' to reset scores only, 'teams' to remove custom teams and reset to Team 1 & Team 2, " +
      "'board' to re-cover all questions, or 'full' to reset everything.",
    "full"
  );
  if (!choice) return;
  const normalized = choice.trim().toLowerCase();
  if (!["scores", "teams", "board", "full"].includes(normalized)) {
    showToast("No changes made");
    return;
  }
  if (!confirm(`This will reset ${normalized}. Continue?`)) return;
  await apiPost(`/api/reset/${normalized}`, {});
  await loadTeams();
  await loadBoard();
  showToast("Reset complete");
});

// Shut down the server (see /api/exit in server.py) and replace the page
// with a static "stopped" message, since no further API calls will succeed.
document.getElementById("exit-btn").addEventListener("click", async () => {
  if (!confirm("This will stop the server for everyone. Continue?")) return;
  try {
    await apiPost("/api/exit", {});
  } catch (e) {
    // The server may close the connection as part of shutting down; ignore.
  }
  document.body.innerHTML =
    '<div style="padding:60px 20px; text-align:center; font-size:1.4rem;">' +
    "Server stopped. You can close this tab." +
    "</div>";
});

/** Page bootstrap: pick up the round the server left off on, then load teams and the board. */
async function init() {
  const roundsInfo = await apiGet("/api/rounds");
  state.round = roundsInfo.current_round || 1;
  await loadTeams();
  await loadBoard();
}

init();
showDatabaseModal(false); // let the teacher pick/confirm which class's database to use before playing
