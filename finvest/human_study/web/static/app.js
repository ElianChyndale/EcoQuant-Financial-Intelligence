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
    if (minimal) minimal.value = collectIds(".ev-minimal");  // minimal_evidence_set
  }
  document.querySelectorAll(".ev-support, .ev-minimal").forEach(function (cb) {
    cb.addEventListener("change", syncHidden);
  });

  // --- Build record from form (values only; no label invention) ---
  // Emits the FULL CLI schema (BASE_FIELD_SPECS), including the CLI-correct
  // field name minimal_evidence_set (not minimal_evidence_ids).
  function collectRecord() {
    var form = document.getElementById("judgement-form");
    if (!form) return null;
    var queue = form.dataset.queue;
    function val(name) {
      var el = form.elements[name];
      if (!el) return null;
      if (el.type === "checkbox") return el.checked;
      if (el.type === "radio") {
        for (var i = 0; i < el.length; i++) {
          if (el[i].checked) {
            return el[i].value === "" ? null : (el[i].value === "true" ? true : (el[i].value === "false" ? false : el[i].value));
          }
        }
        return null;
      }
      return el.value !== "" ? el.value : null;
    }
    function idList(name) {
      var el = form.elements[name];
      if (!el) return [];
      return String(el.value || "").split(/\s+/).filter(Boolean);
    }
    var record = {
      record_type: queue === "base" ? "BASE_22" :
                   queue === "paired" ? "PAIRED_12" :
                   queue === "interface" ? "INTERFACE_PILOT" : "BLIND_REPEAT",
    };
    if (queue === "interface") {
      record.case_id = form.dataset.key;
      record.display_condition = form.display_condition ? form.display_condition.value : null;
      record.final_judgement = val("final_judgement");
      record.error_detected = val("error_detected") === true;
      record.missing_evidence_detected = val("missing_evidence_detected") === true;
      record.wrong_period_detected = val("wrong_period_detected") === true;
      record.review_time_seconds = val("review_time_seconds");
      record.confidence = val("confidence");
      record.interface_notes = val("interface_notes");
      record.elapsed_seconds = 0;
      return record;
    }
    // Base / paired / blind share the CLI BASE_FIELD_SPECS.
    record.case_id = form.dataset.key;
    if (queue === "paired") { record.review_token = form.dataset.key; record.condition_identity = "HIDDEN_DURING_REVIEW"; record.pass = 1; }
    if (queue === "blind") { record.temp_id = form.dataset.key; record.pass = 2; }
    record.question_valid = val("question_valid");
    record.answerability = val("answerability");
    record.sufficiency = val("sufficiency");
    record.entity = val("entity");
    record.metric = val("metric");
    record.target_period = val("target_period");
    record.unit_and_scale = val("unit_and_scale");
    record.reporting_scope = val("reporting_scope");
    record.mandatory_requirements = idList("mandatory_requirements");
    record.supporting_evidence_ids = idList("supporting_evidence_ids");
    record.minimal_evidence_set = idList("minimal_evidence_set"); // CLI-correct name
    record.source_time_valid = val("source_time_valid");
    record.version_valid = val("version_valid");
    record.calculation_reproducible = val("calculation_reproducible");
    record.final_answer_or_null = val("final_answer_or_null");
    record.reviewer_confidence = val("reviewer_confidence");
    record.reviewer_notes = val("reviewer_notes");
    record.elapsed_seconds = 0;
    return record;
  }

  // --- Save draft (button click + Ctrl+S autosave, with visible outcome) ---
  function showSaveStatus(text, isError) {
    var el = document.getElementById("save-status");
    if (!el) return;
    el.textContent = text;
    el.className = "save-status " + (isError ? "error" : "ok");
  }
  function autosave(opts) {
    opts = opts || {};
    var form = document.getElementById("judgement-form");
    if (!form) return Promise.resolve(false);
    var record = collectRecord();
    if (!record) return Promise.resolve(false);
    var btn = document.getElementById("save-draft");
    var originalLabel = btn ? btn.textContent : "";
    if (btn) btn.textContent = "Saving...";
    var requestId = "req-" + Date.now() + "-" + Math.floor(Math.random() * 1000);
    return fetch("/draft/" + form.dataset.queue + "/" + form.dataset.key, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        reviewer: form.dataset.reviewer,
        payload: JSON.stringify(record),
        _request_id: requestId,
      }),
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (res) {
      if (!res.ok) throw new Error(res.error || "draft save failed");
      if (btn) btn.textContent = originalLabel;
      var now = new Date();
      var ts = ("0" + now.getHours()).slice(-2) + ":" + ("0" + now.getMinutes()).slice(-2) + ":" + ("0" + now.getSeconds()).slice(-2);
      showSaveStatus("Draft saved locally at " + ts + " (id " + requestId + ")", false);
      return true;
    }).catch(function (err) {
      if (btn) btn.textContent = originalLabel;
      showSaveStatus("Save failed: " + (err && err.message ? err.message : "unknown") + " (id " + requestId + "). Click Save draft to retry.", true);
      return false;
    });
  }
  var saveBtn = document.getElementById("save-draft");
  if (saveBtn) saveBtn.addEventListener("click", function () { autosave(); });
  document.querySelectorAll("#judgement-form select, #judgement-form textarea, #judgement-form input").forEach(function (el) {
    el.addEventListener("change", function () { autosave(); });
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
  // --- Restore draft values on page load (refresh + restart recovery) ---
  function restoreDraft() {
    var form = document.getElementById("judgement-form");
    if (!form || !window.__draft) return;
    var draft = window.__draft;
    Object.keys(draft).forEach(function (key) {
      var value = draft[key];
      var el = form.elements[key];
      if (!el) return;
      if (el.type === "radio") {
        for (var i = 0; i < el.length; i++) {
          if (String(el[i].value) === String(value)) el[i].checked = true;
        }
      } else if (el.type === "checkbox") {
        el.checked = !!value;
      } else if (el.tagName === "SELECT" || el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
        el.value = value === null || value === undefined ? "" : value;
      }
    });
    // Restore evidence checkboxes from supporting/minimal arrays.
    if (draft.supporting_evidence_ids) {
      document.querySelectorAll(".ev-support").forEach(function (cb) {
        if (draft.supporting_evidence_ids.indexOf(cb.dataset.eid) !== -1) cb.checked = true;
      });
    }
    if (draft.minimal_evidence_set) {
      document.querySelectorAll(".ev-minimal").forEach(function (cb) {
        if (draft.minimal_evidence_set.indexOf(cb.dataset.eid) !== -1) cb.checked = true;
      });
    }
    syncHidden();
    showSaveStatus("Draft restored from local save", false);
  }

  // --- Report tooling issue (never a label) ---
  var issueBtn = document.getElementById("report-issue");
  if (issueBtn) {
    issueBtn.addEventListener("click", function () {
      var form = document.getElementById("judgement-form");
      var body = new URLSearchParams({
        reviewer: form.dataset.reviewer,
        category: document.getElementById("issue-category").value,
        evidence_id: document.getElementById("issue-evidence").value,
        note: document.getElementById("issue-note").value,
      });
      fetch("/tooling-issue/" + form.dataset.queue + "/" + form.dataset.key, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body,
      }).then(function (r) { return r.json(); }).then(function (res) {
        var s = document.getElementById("issue-status");
        if (s) { s.textContent = res.ok ? "Issue reported (not a label)." : "Failed: " + res.error; }
      });
    });
  }

  var openReviewBtn = document.getElementById("open-final-review");
  if (!openReviewBtn) return; // dashboard page: no case controls
  openReviewBtn.addEventListener("click", openFinalReview);
  restoreDraft();

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
