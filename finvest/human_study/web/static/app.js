// FinVEST workbench — minimal local JS. No CDN, no external calls.
// Signing has NO keyboard shortcut (explicit typed confirmation only).

(function () {
  "use strict";

  // --- Tabs ---
  document.querySelectorAll(".tabs").forEach(function (tablist) {
    tablist.addEventListener("click", function (e) {
      var btn = e.target.closest(".tab");
      if (!btn) return;
      var name = btn.dataset.tab;
      var panel = tablist.parentElement;
      panel.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
      panel.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
      btn.classList.add("active");
      panel.querySelector('[data-panel="' + name + '"]').classList.add("active");
    });
  });

  // --- Evidence selection aggregation ---
  function collectIds(cls) {
    var ids = [];
    document.querySelectorAll(cls + ":checked").forEach(function (cb) {
      ids.push(cb.dataset.eid);
    });
    return ids.join(" ");
  }
  function syncHidden() {
    var support = document.getElementById("supporting-ids");
    var minimal = document.getElementById("minimal-ids");
    if (support) support.value = collectIds(".ev-support");
    if (minimal) minimal.value = collectIds(".ev-minimal");
  }
  document.querySelectorAll(".ev-support, .ev-minimal").forEach(function (cb) {
    cb.addEventListener("change", syncHidden);
  });

  // --- Build record from form (values only; no label invention) ---
  function collectRecord() {
    var form = document.getElementById("judgement-form");
    if (!form) return null;
    var record = {
      record_type: form.dataset.queue === "base" ? "BASE_22" : "PAIRED_12",
      case_id: form.dataset.key,
      question_valid: form.question_valid.value || null,
      answerability: form.answerability.value || null,
      sufficiency: form.sufficiency.value || null,
      route: form.route.value || null,
      reviewer_confidence: form.reviewer_confidence.value ? parseInt(form.reviewer_confidence.value, 10) : null,
      reviewer_notes: form.reviewer_notes.value || null,
      supporting_evidence_ids: (form.supporting_evidence_ids.value || "").split(/\s+/).filter(Boolean),
      minimal_evidence_ids: (form.minimal_evidence_ids.value || "").split(/\s+/).filter(Boolean),
      elapsed_seconds: 0,
    };
    return record;
  }

  // --- Autosave (Ctrl+S, plus on change) ---
  function autosave() {
    var form = document.getElementById("judgement-form");
    if (!form) return;
    var record = collectRecord();
    if (!record) return;
    fetch("/draft/" + form.dataset.queue + "/" + form.dataset.key, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        reviewer: form.dataset.reviewer,
        payload: JSON.stringify(record),
      }),
    }).then(function (r) { return r.json(); }).then(function () {
      var p = document.getElementById("global-progress");
      if (p) p.textContent = "Autosaved " + new Date().toLocaleTimeString();
    });
  }
  document.querySelectorAll("#judgement-form select, #judgement-form textarea").forEach(function (el) {
    el.addEventListener("change", autosave);
  });
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); autosave(); }
  });

  // --- Final review + explicit signing (no shortcut) ---
  function openFinalReview() {
    var record = collectRecord();
    if (!record) return;
    document.getElementById("final-record-json").textContent = JSON.stringify(record, null, 2);
    document.getElementById("final-review-modal").hidden = false;
    document.getElementById("sign-confirm").value = "";
    document.getElementById("sign-confirm").focus();
  }
  document.getElementById("open-final-review").addEventListener("click", openFinalReview);

  document.getElementById("do-sign").addEventListener("click", function () {
    var form = document.getElementById("judgement-form");
    var confirmation = document.getElementById("sign-confirm").value;
    fetch("/sign/" + form.dataset.queue + "/" + form.dataset.key, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        reviewer: form.dataset.reviewer,
        payload: JSON.stringify(collectRecord()),
        confirmation: confirmation,
      }),
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res.ok) {
        document.getElementById("final-review-modal").hidden = true;
        location.href = "/case/" + form.dataset.queue + "/" + form.dataset.key;
      } else {
        alert("Signing failed: " + (res.error || "unknown"));
      }
    });
  });

  // Ctrl+Enter opens final review (NOT signing).
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); openFinalReview(); }
  });

  // Close modal with Escape.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") document.getElementById("final-review-modal").hidden = true;
  });
})();
