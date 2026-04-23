const state = {
  reviewData: null,
  selectedConceptId: null,
  selectedCitationId: null,
  conceptSearch: "",
  citationFilter: "all",
  message: "",
  verificationResult: null,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function splitLines(value) {
  return String(value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function conceptRows() {
  const data = state.reviewData;
  if (!data) return [];
  const reviewById = new Map((data.concept_reviews || []).map((item) => [item.concept_id, item]));
  return (data.draft_pack?.concepts || []).map((concept) => ({
    ...concept,
    review: reviewById.get(concept.concept_id) || null,
  }));
}

function citationRows() {
  return state.reviewData?.citation_reviews || [];
}

function selectedConcept() {
  return conceptRows().find((item) => item.concept_id === state.selectedConceptId) || conceptRows()[0] || null;
}

function selectedCitation() {
  return citationRows().find((item) => item.citation_review_id === state.selectedCitationId) || citationRows()[0] || null;
}

async function loadReviewData() {
  const response = await fetch("/api/load");
  const payload = await response.json();
  state.reviewData = payload.review_data;
  if (!state.selectedConceptId && conceptRows()[0]) {
    state.selectedConceptId = conceptRows()[0].concept_id;
  }
  if (!state.selectedCitationId && citationRows()[0]) {
    state.selectedCitationId = citationRows()[0].citation_review_id;
  }
  render();
}

async function saveConcept(form) {
  const payload = {
    concept_updates: [
      {
        concept_id: form.get("concept_id"),
        status: form.get("status"),
        description: form.get("description"),
        prerequisites: splitLines(form.get("prerequisites")),
        notes: splitLines(form.get("notes")),
      },
    ],
  };
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  state.reviewData = result.review_data;
  state.message = `Saved concept ${payload.concept_updates[0].concept_id}.`;
  render();
}

async function saveCitation(form) {
  const payload = {
    citation_updates: [
      {
        citation_review_id: form.get("citation_review_id"),
        status: form.get("status"),
        notes: splitLines(form.get("notes")),
      },
    ],
  };
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  state.reviewData = result.review_data;
  state.message = `Saved citation review ${payload.citation_updates[0].citation_review_id}.`;
  render();
}

async function verifyCitation(citationReviewId) {
  const response = await fetch("/api/citations/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ citation_review_id: citationReviewId }),
  });
  state.verificationResult = await response.json();
  state.message = `Verification run for ${citationReviewId}.`;
  render();
}

function statusOptions(specs, selectedValue) {
  return (specs?.options || [])
    .map((option) => `<option value="${escapeHtml(option.value)}"${option.value === selectedValue ? " selected" : ""}>${escapeHtml(option.label)}</option>`)
    .join("");
}

function renderConceptPanel(concept) {
  if (!concept) {
    return `<section class="panel"><h2>No concept selected</h2></section>`;
  }
  const review = concept.review || {};
  const statusSpec = (state.reviewData.field_specs || []).find((item) => item.field === "status");
  const guidance = (state.reviewData.review_guidance?.priorities || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const claims = (review.top_claims || []).map((claim) => `
    <article class="claim-card">
      <div class="claim-head">
        <strong>${escapeHtml(claim.claim_kind || "claim")}</strong>
        <span class="chip">${escapeHtml(claim.grounding_status || "unknown")}</span>
      </div>
      <p>${escapeHtml(claim.claim_text || "")}</p>
      <div class="tiny">Artifacts: ${escapeHtml((claim.artifact_paths || []).join(", ") || "none")}</div>
      ${(claim.supporting_observations || []).slice(0, 2).map((obs) => `
        <div class="support-block">
          <div class="tiny">${escapeHtml(obs.origin_path || "")}${obs.line_start ? `:${obs.line_start}` : ""}</div>
          <div>${escapeHtml(obs.text || "")}</div>
        </div>
      `).join("")}
    </article>
  `).join("");

  return `
    <section class="panel detail">
      <div class="panel-head">
        <div>
          <h2>${escapeHtml(concept.title)}</h2>
          <div class="muted">${escapeHtml(concept.concept_id)} · claims ${escapeHtml(review.claim_count || 0)} · grounded ${escapeHtml(review.grounded_claim_count || 0)} · warnings ${escapeHtml(review.warning_count || 0)}</div>
        </div>
        <div class="pill ${review.has_citation_support ? "pill-good" : "pill-warn"}">${review.has_citation_support ? "citation-bearing" : "no citation support"}</div>
      </div>
      <p class="help">${escapeHtml(review.review_help || "")}</p>
      <form id="concept-form">
        <input type="hidden" name="concept_id" value="${escapeHtml(concept.concept_id)}" />
        <label>
          <span>Review status</span>
          <select name="status">${statusOptions(statusSpec, concept.status)}</select>
        </label>
        <label>
          <span>Description</span>
          <textarea name="description" rows="3">${escapeHtml(concept.description || "")}</textarea>
        </label>
        <label>
          <span>Prerequisites</span>
          <textarea name="prerequisites" rows="3">${escapeHtml((concept.prerequisites || []).join("\n"))}</textarea>
        </label>
        <label>
          <span>Reviewer notes</span>
          <textarea name="notes" rows="5">${escapeHtml((concept.notes || []).join("\n"))}</textarea>
        </label>
        <div class="actions">
          <button type="submit" class="primary">Save Concept Review</button>
        </div>
      </form>
      <section class="subpanel">
        <h3>Reviewer guidance</h3>
        <ul>${guidance}</ul>
      </section>
      <section class="subpanel">
        <h3>Representative claims</h3>
        <div class="stack">${claims || "<div class=\"muted\">No representative claims available.</div>"}</div>
      </section>
    </section>
  `;
}

function renderCitationPanel(citation) {
  const statusSpec = (state.reviewData.citation_field_specs || []).find((item) => item.field === "status");
  const nextActions = (state.reviewData.citations?.next_actions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  if (!citation) {
    return `<section class="panel"><h2>No citation selected</h2></section>`;
  }
  return `
    <section class="panel detail">
      <div class="panel-head">
        <div>
          <h2>Citation lane</h2>
          <div class="muted">${escapeHtml(citation.source_kind)} · ${escapeHtml(citation.artifact_path || citation.locator || "")}</div>
        </div>
        <div class="pill">${escapeHtml(citation.status)}</div>
      </div>
      <form id="citation-form">
        <input type="hidden" name="citation_review_id" value="${escapeHtml(citation.citation_review_id)}" />
        <label>
          <span>Status</span>
          <select name="status">${statusOptions(statusSpec, citation.status)}</select>
        </label>
        <label>
          <span>Citation key</span>
          <input value="${escapeHtml(citation.citation_key || "")}" disabled />
        </label>
        <label>
          <span>Reference title</span>
          <input value="${escapeHtml(citation.title || "")}" disabled />
        </label>
        <label>
          <span>Bibliography source</span>
          <input value="${escapeHtml(citation.source_bib_path || "")}" disabled />
        </label>
        <label>
          <span>Reviewer notes</span>
          <textarea name="notes" rows="5">${escapeHtml((citation.notes || []).join("\n"))}</textarea>
        </label>
        <div class="tiny">Related concepts: ${escapeHtml((citation.related_concept_ids || []).join(", ") || "none")}</div>
        <div class="tiny">Related claims: ${escapeHtml((citation.related_claim_ids || []).join(", ") || "none")}</div>
        <div class="actions">
          <button type="button" id="verify-citation" class="secondary">Verify With CiteGeist</button>
          <button type="submit" class="primary">Save Citation Review</button>
        </div>
      </form>
      <section class="subpanel">
        <h3>Citation guidance</h3>
        <ul>${(state.reviewData.review_guidance?.citation_guidance || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </section>
      <section class="subpanel">
        <h3>Next actions</h3>
        <ul>${nextActions}</ul>
      </section>
      <section class="subpanel">
        <h3>Verification</h3>
        ${
          state.verificationResult && state.verificationResult.citation_review_id === citation.citation_review_id
            ? `<pre class="json-block">${escapeHtml(JSON.stringify(state.verificationResult, null, 2))}</pre>`
            : `<div class="muted">Run CiteGeist verification to inspect the stored entry and candidate matches.</div>`
        }
      </section>
    </section>
  `;
}

function render() {
  const app = document.getElementById("app");
  if (!state.reviewData) {
    app.innerHTML = `<main class="shell"><section class="panel"><h1>Loading review data…</h1></section></main>`;
    return;
  }
  const summary = state.reviewData.import_context?.manifest || {};
  const conceptList = conceptRows().filter((item) => {
    const needle = state.conceptSearch.trim().toLowerCase();
    return !needle || item.title.toLowerCase().includes(needle) || item.concept_id.toLowerCase().includes(needle);
  });
  const citationList = citationRows().filter((item) => {
    if (state.citationFilter === "all") return true;
    return item.status === state.citationFilter;
  });
  const concept = selectedConcept();
  const citation = selectedCitation();

  app.innerHTML = `
    <main class="shell">
      <header class="hero">
        <div>
          <h1>GroundRecall Review Workbench</h1>
          <p>Concept-first review with a dedicated citation lane for academic imports.</p>
          <div class="muted">${escapeHtml(summary.import_id || "")} · ${escapeHtml(summary.source_root || "")}</div>
          ${state.message ? `<div class="message">${escapeHtml(state.message)}</div>` : ""}
        </div>
        <div class="hero-stats">
          <div class="stat"><strong>${escapeHtml(summary.artifact_count || 0)}</strong><span>artifacts</span></div>
          <div class="stat"><strong>${escapeHtml(summary.claim_count || 0)}</strong><span>claims</span></div>
          <div class="stat"><strong>${escapeHtml(summary.concept_count || 0)}</strong><span>concepts</span></div>
          <div class="stat"><strong>${escapeHtml(state.reviewData.citations?.summary?.citation_key_total || 0)}</strong><span>citation keys</span></div>
        </div>
      </header>

      <section class="workspace-grid">
        <aside class="panel list-panel">
          <div class="panel-head"><h2>Concepts</h2></div>
          <label class="search">
            <span>Search</span>
            <input id="concept-search" value="${escapeHtml(state.conceptSearch)}" />
          </label>
          <div class="stack">
            ${conceptList.map((item) => `
              <button class="list-item ${item.concept_id === concept?.concept_id ? "active" : ""}" data-concept-id="${escapeHtml(item.concept_id)}">
                <strong>${escapeHtml(item.title)}</strong>
                <span>${escapeHtml(item.status)}</span>
              </button>
            `).join("")}
          </div>
        </aside>
        ${renderConceptPanel(concept)}
      </section>

      <section class="workspace-grid">
        <aside class="panel list-panel">
          <div class="panel-head"><h2>Citation lane</h2></div>
          <label class="search">
            <span>Filter</span>
            <select id="citation-filter">
              ${["all", "unreviewed", "verified", "needs_source_check", "misleading", "irrelevant", "fabricated"].map((value) => `<option value="${value}"${value === state.citationFilter ? " selected" : ""}>${value}</option>`).join("")}
            </select>
          </label>
          <div class="stack">
            ${citationList.map((item) => `
              <button class="list-item ${item.citation_review_id === citation?.citation_review_id ? "active" : ""}" data-citation-id="${escapeHtml(item.citation_review_id)}">
                <strong>${escapeHtml(item.citation_key || item.title || item.citation_review_id)}</strong>
                <span>${escapeHtml(item.status)}</span>
              </button>
            `).join("")}
          </div>
        </aside>
        ${renderCitationPanel(citation)}
      </section>
    </main>
  `;

  document.querySelectorAll("[data-concept-id]").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedConceptId = node.getAttribute("data-concept-id");
      render();
    });
  });
  document.querySelectorAll("[data-citation-id]").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedCitationId = node.getAttribute("data-citation-id");
      render();
    });
  });
  document.getElementById("concept-search")?.addEventListener("input", (event) => {
    state.conceptSearch = event.target.value;
    render();
  });
  document.getElementById("citation-filter")?.addEventListener("change", (event) => {
    state.citationFilter = event.target.value;
    render();
  });
  document.getElementById("concept-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveConcept(new FormData(event.target));
  });
  document.getElementById("citation-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveCitation(new FormData(event.target));
  });
  document.getElementById("verify-citation")?.addEventListener("click", async () => {
    if (state.selectedCitationId) {
      await verifyCitation(state.selectedCitationId);
    }
  });
}

loadReviewData();
