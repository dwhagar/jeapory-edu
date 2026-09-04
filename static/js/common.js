// Shared helpers used by both the game board and the editor.

async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
  return res.json();
}

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

  // Split on $$...$$ first, then $...$ within the remaining plain segments.
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
