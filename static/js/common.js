// Shared helpers used by both the game board and the editor.

/**
 * GET `url` and parse the response as JSON.
 * Throws an Error with the HTTP status if the request did not succeed.
 */
async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
  return res.json();
}

/**
 * Send a JSON request body to `url` with the given HTTP `method` and parse
 * the JSON response. On failure, throws an Error using the server's
 * `{error: "..."}` message when present, otherwise a generic status message.
 */
async function apiSend(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `${method} ${url} failed: ${res.status}`;
    try {
      const j = await res.json();
      if (j.error) msg = j.error;
    } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

// Convenience wrappers around apiSend for the three write methods the API uses.
const apiPost = (url, body) => apiSend("POST", url, body);
const apiPut = (url, body) => apiSend("PUT", url, body);
const apiDelete = (url) => apiSend("DELETE", url);

/**
 * Renders text that may contain LaTeX math delimited by $$...$$ (display)
 * or $...$ (inline) into a DOM container. Non-math text is inserted safely
 * (no HTML injection). Each math segment becomes an <img> that is rendered
 * dynamically by the server's /api/render endpoint.
 */
function renderRichText(container, text, opts = {}) {
  container.innerHTML = "";
  if (!text) return;
  const color = opts.color || "#FFFFFF";

  // Pass 1: split on $$...$$ (display math) first, since it can itself
  // contain a lone unmatched-looking $ that would otherwise confuse the
  // simpler inline-math pass below. Everything not consumed as display
  // math is left as a "text" piece to be re-scanned in pass 2.
  const blockRe = /\$\$(.+?)\$\$/gs;
  let lastIndex = 0;
  let match;
  const pieces = []; // {type: 'text'|'math', value, display}

  while ((match = blockRe.exec(text)) !== null) {
    if (match.index > lastIndex) {
      pieces.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    pieces.push({ type: "math", value: match[1], display: true });
    lastIndex = blockRe.lastIndex;
  }
  if (lastIndex < text.length) {
    pieces.push({ type: "text", value: text.slice(lastIndex) });
  }

  // Pass 2: within each remaining plain-text piece, split on $...$ (inline
  // math). Math pieces from pass 1 are carried through unchanged.
  const finalPieces = [];
  const inlineRe = /\$(.+?)\$/g;
  for (const piece of pieces) {
    if (piece.type === "math") {
      finalPieces.push(piece);
      continue;
    }
    let li = 0, m;
    inlineRe.lastIndex = 0;
    const t = piece.value;
    while ((m = inlineRe.exec(t)) !== null) {
      if (m.index > li) finalPieces.push({ type: "text", value: t.slice(li, m.index) });
      finalPieces.push({ type: "math", value: m[1], display: false });
      li = inlineRe.lastIndex;
    }
    if (li < t.length) finalPieces.push({ type: "text", value: t.slice(li) });
  }

  // Render: plain text becomes a <span> via textContent (never innerHTML,
  // so user-entered clue/answer text can't inject markup); math becomes an
  // <img> pointing at the server's on-the-fly LaTeX renderer.
  for (const piece of finalPieces) {
    if (piece.type === "text") {
      if (piece.value === "") continue;
      const span = document.createElement("span");
      span.textContent = piece.value;
      container.appendChild(span);
    } else {
      const img = document.createElement("img");
      img.className = "latex-img";
      const params = new URLSearchParams({
        tex: piece.value,
        display: piece.display ? "1" : "0",
        color,
      });
      img.src = `/api/render?${params.toString()}`;
      img.alt = piece.value;
      container.appendChild(img);
    }
  }
}

/**
 * Shared "select a database" dialog used by both the game board and the
 * editor. Lists the .db files in the server's db/ directory; picking one
 * (other than the current one) switches the active database and reloads
 * the page. `allowSave` shows a "Save As New Database" row, which copies
 * the currently active database's questions into a new file with a fresh,
 * unplayed board and default teams -- meant for cloning one built game
 * into a separate copy per class period.
 */
/**
 * If the current page (the editor) has registered a `flushPendingSaves`
 * hook for its debounced autosave, call it and wait for any in-flight
 * edits to reach the server before we switch/copy databases out from
 * under it. A no-op on pages (like the game board) that don't define it.
 */
async function _flushPendingSavesIfAny() {
  if (typeof window.flushPendingSaves === "function") {
    try {
      await window.flushPendingSaves();
    } catch (e) {
      // best-effort; a failed flush shouldn't block navigation
    }
  }
}

let _dbModal = null; // lazily built and cached so repeat opens reuse the same DOM

/** Build the (initially hidden) database-picker modal and cache it in _dbModal. */
function _buildDbModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop hidden";
  backdrop.id = "db-modal-backdrop";
  backdrop.style.zIndex = "400";

  const modal = document.createElement("div");
  modal.className = "modal";
  modal.style.maxWidth = "480px";

  const header = document.createElement("div");
  header.className = "modal-header";
  const title = document.createElement("div");
  title.className = "category-label";
  title.textContent = "Select Database";
  header.appendChild(title);

  const list = document.createElement("div");
  list.style.display = "flex";
  list.style.flexDirection = "column";
  list.style.gap = "8px";
  list.style.margin = "14px 0";

  const saveRow = document.createElement("div");
  saveRow.className = "hidden";
  saveRow.style.borderTop = "1px dashed var(--gold)";
  saveRow.style.paddingTop = "14px";
  saveRow.style.marginTop = "4px";

  const saveHint = document.createElement("div");
  saveHint.className = "hint";
  saveHint.style.marginBottom = "8px";
  saveHint.textContent =
    "Save a copy of the current questions as a new database, ready to play with fresh teams and an uncovered board.";

  const saveInputRow = document.createElement("div");
  saveInputRow.style.display = "flex";
  saveInputRow.style.gap = "8px";
  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = "New database name";
  nameInput.style.flex = "1";
  const saveBtn = document.createElement("button");
  saveBtn.className = "btn";
  saveBtn.textContent = "Save As New";
  saveInputRow.appendChild(nameInput);
  saveInputRow.appendChild(saveBtn);
  saveRow.appendChild(saveHint);
  saveRow.appendChild(saveInputRow);

  const footer = document.createElement("div");
  footer.className = "modal-footer";
  const closeBtn = document.createElement("button");
  closeBtn.className = "btn secondary";
  footer.appendChild(closeBtn);

  modal.appendChild(header);
  modal.appendChild(list);
  modal.appendChild(saveRow);
  modal.appendChild(footer);
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);

  closeBtn.addEventListener("click", () => backdrop.classList.add("hidden"));

  saveBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    if (!name) {
      showToast("Enter a name for the new database");
      return;
    }
    await _flushPendingSavesIfAny();
    try {
      await apiPost("/api/databases", { name });
      location.reload();
    } catch (e) {
      showToast(e.message || "Could not create database");
    }
  });

  _dbModal = { backdrop, list, saveRow, closeBtn };
  return _dbModal;
}

/**
 * Open the database-picker modal, populated with the current list of saved
 * databases fetched from the server. Pass `allowSave` to also show the
 * "Save As New" row (used by the editor, not the game board).
 */
async function showDatabaseModal(allowSave) {
  const m = _dbModal || _buildDbModal();
  m.saveRow.classList.toggle("hidden", !allowSave);
  m.list.textContent = "Loading...";
  m.backdrop.classList.remove("hidden");
  try {
    const data = await apiGet("/api/databases");
    m.list.innerHTML = "";
    for (const name of data.databases) {
      const btn = document.createElement("button");
      const isCurrent = name === data.current;
      btn.className = "btn" + (isCurrent ? "" : " secondary");
      btn.textContent = isCurrent ? `${name} (current)` : name;
      btn.style.width = "100%";
      btn.addEventListener("click", async () => {
        if (isCurrent) {
          m.backdrop.classList.add("hidden");
          return;
        }
        await _flushPendingSavesIfAny();
        try {
          await apiPost("/api/databases/select", { name });
          location.reload();
        } catch (e) {
          showToast(e.message || "Could not load database");
        }
      });
      m.list.appendChild(btn);
    }
    m.closeBtn.textContent = `Keep using ${data.current}`;
  } catch (e) {
    m.list.textContent = "Failed to load database list.";
  }
}

/**
 * Called once on page load by the game board and editor to decide whether
 * to auto-open the database picker. If the server was started with
 * JEOPARDY_DB_NAME (see server.py), the active database was already chosen
 * for us, so skip the prompt -- the "Back to Databases" button remains
 * available to open it manually at any time via showDatabaseModal().
 */
async function maybeShowDatabaseModalOnLoad(allowSave) {
  let envSelected = false;
  try {
    const data = await apiGet("/api/databases");
    envSelected = !!data.env_selected;
  } catch (e) {
    // If the check itself fails, fall back to prompting as before.
  }
  if (!envSelected) {
    showDatabaseModal(allowSave);
  }
}

/**
 * Show a brief, self-dismissing message at the bottom of the screen.
 * Reuses a single toast element across calls; re-triggering resets its timer.
 */
function showToast(message, ms = 2200) {
  let toast = document.getElementById("global-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "global-toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove("show"), ms);
}
