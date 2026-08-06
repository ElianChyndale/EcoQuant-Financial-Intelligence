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

  // --- Transparent mapping: 3 natural questions -> CLI schema fields ---
  // The researcher answers Q1/Q2/Q3 (and confidence). The internal enum
  // labels are DERIVED deterministically from those answers — never
  // recommended by the system — and the full derived record is shown in the
  // final-review modal before signing.
  function deriveBaseFields(form, q1, q2, q3, confidence) {
    var answerable = { ANSWERABLE: "VALID", PARTIAL: "AMBIGUOUS", UNANSWERABLE: "INVALID", REVIEW: "REVIEW_UNRESOLVED" }[q1] || "REVIEW_UNRESOLVED";
    var answerability = { ANSWERABLE: "ANSWERABLE", PARTIAL: "ANSWERABLE", UNANSWERABLE: "UNANSWERABLE", REVIEW: "REVIEW_UNRESOLVED" }[q1] || "REVIEW_UNRESOLVED";
    var sufficiency = { ANSWERABLE: "SUPPORTED", PARTIAL: "PARTIAL", UNANSWERABLE: "INSUFFICIENT", REVIEW: "REVIEW_UNRESOLVED" }[q1] || "REVIEW_UNRESOLVED";
    if (q3 && /冲突|conflict|矛盾|不一致/.test(q3)) sufficiency = sufficiency === "SUPPORTED" ? "CONFLICTING" : sufficiency;
    var route = { ANSWERABLE: "ANSWER", PARTIAL: "REVIEW", UNANSWERABLE: "ABSTAIN", REVIEW: "REVIEW_UNRESOLVED" }[q1] || "REVIEW_UNRESOLVED";
    var notes = [];
    if (q2) notes.push("Q2 答案与计算: " + q2);
    if (q3) notes.push("Q3 冲突: " + q3);
    var calcProvided = (q2 && /\d/.test(q2)) || form.elements["your_calculation"] && form.elements["your_calculation"].value.trim() !== "";
    return {
      question_valid: answerable,
      answerability: answerability,
      sufficiency: sufficiency,
      entity: form.dataset.entity || null,
      metric: form.dataset.metric || null,
      target_period: form.dataset.targetPeriod || null,
      unit_and_scale: form.dataset.unit || null,
      reporting_scope: null,
      mandatory_requirements: [],
      source_time_valid: q3 && /日期|filing|时间|date/.test(q3) ? false : null,
      version_valid: q3 && /版本|amendment|重述|restat/.test(q3) ? false : null,
      calculation_reproducible: calcProvided ? true : null,
      final_answer_or_null: q2 && q2.trim() !== "" ? q2.trim() : null,
      reviewer_confidence: confidence || null,
      reviewer_notes: notes.join("\n") || null,
    };
  }

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
    // Base / paired / blind: derive from the 3 natural questions.
    record.case_id = form.dataset.key;
    if (queue === "paired") { record.review_token = form.dataset.key; record.condition_identity = "HIDDEN_DURING_REVIEW"; record.pass = 1; }
    if (queue === "blind") { record.temp_id = form.dataset.key; record.pass = 2; }
    var derived = deriveBaseFields(
      form,
      val("q1_answerable") || "",
      val("q2_answer_and_calc") || "",
      val("q3_conflicts") || "",
      val("reviewer_confidence") || ""
    );
    Object.keys(derived).forEach(function (k) { record[k] = derived[k]; });
    record.supporting_evidence_ids = idList("supporting_evidence_ids");
    record.minimal_evidence_set = idList("minimal_evidence_set"); // CLI-correct name
    record.elapsed_seconds = 0;
    // Raw answers are persisted for draft RESTORE only; stripped before sign.
    record._raw = {
      q1_answerable: val("q1_answerable") || "",
      q2_answer_and_calc: val("q2_answer_and_calc") || "",
      q3_conflicts: val("q3_conflicts") || "",
      reviewer_confidence: val("reviewer_confidence") || "",
      your_calculation: val("your_calculation") || "",
    };
    return record;
  }

  function stripRaw(record) {
    var copy = {};
    Object.keys(record).forEach(function (k) { if (k !== "_raw") copy[k] = record[k]; });
    return copy;
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
    return fetch("/draft/" + form.dataset.queue + "/" + form.dataset.key, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "reviewer=" + encodeURIComponent(form.dataset.reviewer || "ELIAN_PRIMARY") +
            "&payload=" + encodeURIComponent(JSON.stringify(record)),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j && j.ok) { showSaveStatus("Draft saved", false); return true; }
      showSaveStatus("Draft save failed: " + (j && j.error || "unknown"), true);
      return false;
    }).catch(function (e) { showSaveStatus("Draft save failed: " + e, true); return false; });
  }
  var saveBtn = document.getElementById("save-draft");
  if (saveBtn) {
    saveBtn.addEventListener("click", function () { autosave(); });
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        autosave();
      }
    });
  }

  // --- Draft restore (from the persisted RAW answers) ---
  if (window.__draft) {
    var raw = window.__draft._raw || window.__draft;
    var form = document.getElementById("judgement-form");
    if (form) {
      Object.keys(raw).forEach(function (name) {
        if (!form.elements[name]) return;
        var el = form.elements[name];
        if (el.type === "radio") {
          var val = raw[name];
          for (var i = 0; i < el.length; i++) {
            if (String(el[i].value) === String(val)) { el[i].checked = true; }
          }
        } else {
          el.value = raw[name] != null ? raw[name] : "";
        }
      });
    }
    syncHidden();
  }

  // --- Final review + sign (requires typed SIGN <case-key>) ---
  var openReview = document.getElementById("open-final-review");
  var modal = document.getElementById("final-review-modal");
  var recordJson = document.getElementById("final-record-json");
  function openFinalReview() {
    var record = collectRecord();
    if (!record) return;
    recordJson.textContent = JSON.stringify(stripRaw(record), null, 2);
    modal.hidden = false;
  }
  if (openReview && modal && recordJson) {
    openReview.addEventListener("click", openFinalReview);
    // Ctrl+Enter opens the final review (NEVER signs).
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        openFinalReview();
      }
    });
  }
  var doSign = document.getElementById("do-sign");
  if (doSign) {
    // Sign is bound ONLY to the button click — never a keyboard shortcut.
    document.getElementById("do-sign").addEventListener("click", function () {
      var form = document.getElementById("judgement-form");
      var confirmation = document.getElementById("sign-confirm").value.trim();
      var record = JSON.parse(recordJson.textContent);  // already stripped of _raw
      var expected = "SIGN " + form.dataset.key;
      if (confirmation !== expected) {
        alert("Confirmation must be: " + expected);
        return;
      }
      fetch("/sign/" + form.dataset.queue + "/" + form.dataset.key, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "reviewer=" + encodeURIComponent(form.dataset.reviewer || "ELIAN_PRIMARY") +
              "&payload=" + encodeURIComponent(JSON.stringify(record)) +
              "&confirmation=" + encodeURIComponent(confirmation),
      }).then(function (r) { return r.json(); }).then(function (j) {
        if (j && j.ok) { window.location.reload(); }
        else { alert("Sign failed: " + (j && j.error || "unknown")); }
      }).catch(function (e) { alert("Sign failed: " + e); });
    });
  }

  // --- Tooling issue ---
  var reportIssue = document.getElementById("report-issue");
  if (reportIssue) {
    reportIssue.addEventListener("click", function () {
      var form = document.getElementById("judgement-form");
      var category = document.getElementById("issue-category").value;
      var evidenceId = document.getElementById("issue-evidence").value.trim();
      var note = document.getElementById("issue-note").value.trim();
      fetch("/tooling-issue/" + form.dataset.queue + "/" + form.dataset.key, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "reviewer=" + encodeURIComponent(form.dataset.reviewer || "ELIAN_PRIMARY") +
              "&category=" + encodeURIComponent(category) +
              "&evidence_id=" + encodeURIComponent(evidenceId) +
              "&note=" + encodeURIComponent(note),
      }).then(function (r) { return r.json(); }).then(function (j) {
        var el = document.getElementById("issue-status");
        el.textContent = j.ok ? "Issue reported" : "Failed: " + (j.error || "unknown");
        el.className = "save-status " + (j.ok ? "ok" : "error");
      });
    });
  }

  // --- Practice mode: submit first, reveal reference AFTER submission ---
  var practiceForm = document.getElementById("practice-form");
  if (practiceForm) {
    practiceForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = new FormData(practiceForm);
      fetch("/practice/" + practiceForm.dataset.key, {
        method: "POST",
        body: data,
      }).then(function (r) { return r.json(); }).then(function (j) {
        var status = document.getElementById("practice-status");
        if (!j.ok) {
          status.textContent = "提交失败: " + (j.error || "unknown");
          status.className = "save-status error";
          return;
        }
        status.textContent = "已提交练习。参考答案如下（提交后揭示）。";
        status.className = "save-status ok";
        document.getElementById("practice-reveal").hidden = false;
        document.getElementById("reveal-reference").textContent = j.reveal.reference_answer;
        document.getElementById("reveal-explanation").textContent = j.reveal.source_explanation;
        document.getElementById("reveal-disagreement").textContent =
          j.reveal.disagreement_reason || "—";
        // Lock the form so the answer cannot be changed after the reveal.
        practiceForm.querySelectorAll("input, textarea, select, button").forEach(function (el) {
          el.disabled = true;
        });
      }).catch(function (err) {
        document.getElementById("practice-status").textContent = "提交失败: " + err;
        document.getElementById("practice-status").className = "save-status error";
      });
    });
  }
})();
