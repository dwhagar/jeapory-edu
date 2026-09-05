// Question editor controller.
//
// Renders one round's categories/questions as editable form rows and
// autosaves each field to the server (via /api/admin/*) a short debounce
// interval after the user stops typing, showing a "Saved" toast on success.

const editorState = { round: 1 }; // which round's categories are currently shown

const container = document.getElementById("categories-container");
const tabs = {
  1: document.getElementById("tab-round-1"),
  2: document.getElementById("tab-round-2"),
  3: document.getElementById("tab-round-3"),
};

/** Switch the editor to a different round: update tab styling and reload its categories. */
function setActiveTab(round) {
  editorState.round = round;
  for (const [r, btn] of Object.entries(tabs)) {
    btn.className = Number(r) === round ? "btn" : "btn secondary";
  }
  loadCategories();
}

tabs[1].addEventListener("click", () => setActiveTab(1));
tabs[2].addEventListener("click", () => setActiveTab(2));
tabs[3].addEventListener("click", () => setActiveTab(3));

document.getElementById("back-to-game").addEventListener("click", () => {
  window.location.href = "/";
});

document.getElementById("db-btn").addEventListener("click", async () => {
  await flushPendingSaves();
  showDatabaseModal(true);
});
showDatabaseModal(true);

document.getElementById("add-category-btn").addEventListener("click", async () => {
  await apiPost("/api/admin/categories", { name: "New Category", round: editorState.round });
  await loadCategories();
});

/**
 * Return a wrapped version of `fn` that only actually runs `ms` milliseconds
 * after the last call, discarding intermediate calls. Used to throttle the
 * live LaTeX preview so it doesn't re-render on every keystroke.
 */
function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// Like debounce(), but for calls that persist to the server: pending ones
// are tracked so flushPendingSaves() can force them through immediately
// (e.g. right before switching databases, so a just-typed edit isn't lost).
const pendingSaves = new Set();

/**
 * Like debounce(), but for calls that persist to the server: the pending
 * call is tracked in `pendingSaves` (with only the latest arguments kept)
 * so flushPendingSaves() can force it through immediately, e.g. right
 * before switching databases so a just-typed edit isn't lost.
 */
function debounceSave(fn, ms) {
  let timer = null;
  let latestArgs = null;
  const entry = {
    // Force this pending call through right now, if one is scheduled.
    flush: async () => {
      if (timer === null) return;
      clearTimeout(timer);
      timer = null;
      const args = latestArgs;
      latestArgs = null;
      pendingSaves.delete(entry);
      await fn(...args);
    },
  };
  return (...args) => {
    latestArgs = args;
    clearTimeout(timer);
    pendingSaves.add(entry);
    timer = setTimeout(() => {
      timer = null;
      const runArgs = latestArgs;
      latestArgs = null;
      pendingSaves.delete(entry);
      fn(...runArgs);
    }, ms);
  };
}

/** Immediately run every currently-pending debounceSave() call, in parallel. */
async function flushPendingSaves() {
  await Promise.all([...pendingSaves].map((entry) => entry.flush()));
}
// Exposed globally so common.js's database-switch/save-as flow can flush
// in-flight edits before it reloads the page onto a different database.
window.flushPendingSaves = flushPendingSaves;

/** Fetch the current round's categories/questions and re-render them. */
async function loadCategories() {
  const data = await apiGet(`/api/admin/categories?round=${editorState.round}`);
  renderCategories(data.categories);
}

/** Replace the categories container's contents with one block per category. */
function renderCategories(categories) {
  container.innerHTML = "";
  for (const cat of categories) {
    container.appendChild(buildCategoryBlock(cat));
  }
}

/**
 * Build the editable panel for one category: a renamable title, an "Add
 * Question"/"Delete Category" action row, and one buildQuestionRow() per
 * question already in the category.
 */
function buildCategoryBlock(cat) {
  const block = document.createElement("div");
  block.className = "category-block";

  const titleRow = document.createElement("div");
  titleRow.className = "category-title-row";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.className = "cat-name";
  nameInput.value = cat.name;
  nameInput.addEventListener(
    "change",
    debounceSave(async () => {
      await apiPut(`/api/admin/categories/${cat.id}`, { name: nameInput.value });
      showToast("Category saved");
    }, 300)
  );

  const addQBtn = document.createElement("button");
  addQBtn.className = "btn secondary";
  addQBtn.textContent = "+ Add Question";
  addQBtn.addEventListener("click", async () => {
    const defaultValue = editorState.round === 3 ? 0 : (editorState.round === 2 ? 200 : 100);
    await apiPost("/api/admin/questions", {
      category_id: cat.id,
      value: defaultValue,
      question_text: "",
      answer_text: "",
      is_daily_double: false,
    });
    await loadCategories();
  });

  const delCatBtn = document.createElement("button");
  delCatBtn.className = "btn danger";
  delCatBtn.textContent = "Delete Category";
  delCatBtn.addEventListener("click", async () => {
    if (!confirm(`Delete category "${cat.name}" and all its questions?`)) return;
    await apiDelete(`/api/admin/categories/${cat.id}`);
    await loadCategories();
  });

  titleRow.appendChild(nameInput);
  titleRow.appendChild(addQBtn);
  titleRow.appendChild(delCatBtn);
  block.appendChild(titleRow);

  for (const q of cat.questions) {
    block.appendChild(buildQuestionRow(q));
  }

  return block;
}

/**
 * Build one editable question row: value/daily-double controls, clue and
 * answer textareas each with a live LaTeX preview underneath, and delete /
 * used-flag controls. Every field autosaves to the server via debounceSave.
 */
function buildQuestionRow(q) {
  const row = document.createElement("div");
  row.className = "question-row";

  // Value
  const valueWrap = document.createElement("div");
  const valueLabel = document.createElement("label");
  valueLabel.textContent = "Value";
  const valueInput = document.createElement("input");
  valueInput.type = "number";
  valueInput.value = q.value;
  valueInput.step = 50;
  valueWrap.appendChild(valueLabel);
  valueWrap.appendChild(valueInput);

  const ddWrap = document.createElement("div");
  ddWrap.className = "dd-toggle";
  const ddCheckbox = document.createElement("input");
  ddCheckbox.type = "checkbox";
  ddCheckbox.checked = !!q.is_daily_double;
  ddCheckbox.id = `dd-${q.id}`;
  const ddLabel = document.createElement("label");
  ddLabel.htmlFor = `dd-${q.id}`;
  ddLabel.textContent = "Daily Double";
  ddWrap.appendChild(ddCheckbox);
  ddWrap.appendChild(ddLabel);
  valueWrap.appendChild(ddWrap);

  // Question text + preview
  const qWrap = document.createElement("div");
  const qLabel = document.createElement("label");
  qLabel.textContent = "Question (clue)";
  const qTextarea = document.createElement("textarea");
  qTextarea.value = q.question_text;
  const qPreview = document.createElement("div");
  qPreview.className = "preview";
  qWrap.appendChild(qLabel);
  qWrap.appendChild(qTextarea);
  qWrap.appendChild(qPreview);

  // Answer text + preview
  const aWrap = document.createElement("div");
  const aLabel = document.createElement("label");
  aLabel.textContent = "Answer";
  const aTextarea = document.createElement("textarea");
  aTextarea.value = q.answer_text;
  const aPreview = document.createElement("div");
  aPreview.className = "preview";
  aWrap.appendChild(aLabel);
  aWrap.appendChild(aTextarea);
  aWrap.appendChild(aPreview);

  const updatePreview = debounce(() => {
    renderRichText(qPreview, qTextarea.value, { color: "#FFFFFF" });
    renderRichText(aPreview, aTextarea.value, { color: "#FFD700" });
  }, 400);
  updatePreview();

  const saveField = debounceSave(async (field, value) => {
    await apiPut(`/api/admin/questions/${q.id}`, { [field]: value });
    showToast("Saved");
  }, 500);

  valueInput.addEventListener("input", () => {
    saveField("value", parseInt(valueInput.value, 10) || 0);
  });
  ddCheckbox.addEventListener("change", () => {
    saveField("is_daily_double", ddCheckbox.checked);
  });
  qTextarea.addEventListener("input", () => {
    updatePreview();
    saveField("question_text", qTextarea.value);
  });
  aTextarea.addEventListener("input", () => {
    updatePreview();
    saveField("answer_text", aTextarea.value);
  });

  // Actions
  const actionsWrap = document.createElement("div");
  actionsWrap.className = "row-actions";
  const delBtn = document.createElement("button");
  delBtn.className = "btn danger";
  delBtn.textContent = "Delete";
  delBtn.addEventListener("click", async () => {
    if (!confirm("Delete this question?")) return;
    await apiDelete(`/api/admin/questions/${q.id}`);
    row.remove();
  });
  const usedWrap = document.createElement("div");
  usedWrap.className = "dd-toggle";
  const usedCheckbox = document.createElement("input");
  usedCheckbox.type = "checkbox";
  usedCheckbox.checked = !!q.used;
  usedCheckbox.id = `used-${q.id}`;
  const usedLabel = document.createElement("label");
  usedLabel.htmlFor = `used-${q.id}`;
  usedLabel.textContent = "Used";
  usedCheckbox.addEventListener("change", () => saveField("used", usedCheckbox.checked));
  usedWrap.appendChild(usedCheckbox);
  usedWrap.appendChild(usedLabel);

  actionsWrap.appendChild(delBtn);
  actionsWrap.appendChild(usedWrap);

  row.appendChild(valueWrap);
  row.appendChild(qWrap);
  row.appendChild(aWrap);
  row.appendChild(actionsWrap);

  return row;
}

setActiveTab(1);
