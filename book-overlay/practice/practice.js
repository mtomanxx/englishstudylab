"use strict";
(() => {
  const app = document.getElementById("app");
  const steps = ["Word check", "Complete the words", "Reading", "Listening", "Writing", "Speaking", "Results"];
  const rubricCriteria = ["Task fulfilment", "Organisation", "Language control"];
  const rubricLabels = ["0 · Not demonstrated", "1 · Limited", "2 · Developing", "3 · Effective", "4 · Consistent"];
  const objectiveKeys = ["vocab", "blanks", "reading", "listening"];
  const snapshots = new Map();
  let exams = [], exam = null, step = 0, synth = null, timer = null;
  try {
    if ("speechSynthesis" in window && typeof window.SpeechSynthesisUtterance === "function") synth = window.speechSynthesis;
  } catch (_) {}

  function node(tag, properties = {}, ...children) {
    const item = document.createElement(tag);
    for (const [key, value] of Object.entries(properties)) {
      if (key === "class") item.className = value;
      else if (key === "text") item.textContent = value;
      else if (key.startsWith("on")) item.addEventListener(key.slice(2), value);
      else if (key === "disabled" || key === "hidden" || key === "checked") item[key] = value;
      else item.setAttribute(key, String(value));
    }
    item.append(...children);
    return item;
  }
  const p = (text, className) => node("p", { text, class: className || "" });
  const btn = (text, action, style = "btn") => node("button", { text, class: style, type: "button", onclick: action });
  const text = (tag, message, cls = "") => node(tag, { text: message, class: cls });
  const examLabel = (id) => "Exam " + String(id).padStart(2, "0");
  const state = () => snapshots.get(exam.id);
  const validSections = (section, key) => typeof section?.[key] === "string" && section.questions?.length === 4 &&
    section.questions.every(q => typeof q.prompt === "string" && q.options?.length === 4 && Number.isInteger(q.answer) && q.answer >= 0 && q.answer < 4 && typeof q.explanation === "string");
  function validate(data) {
    if (!Array.isArray(data) || data.length !== 10 || new Set(data.map(item => item?.id)).size !== 10 ||
      !data.every(e => Number.isInteger(e.id) && e.id >= 1 && e.id <= 10 &&
        typeof e.title === "string" && typeof e.theme === "string" &&
        e.vocab?.length === 6 && e.vocab.every(x => typeof x.word === "string" && typeof x.real === "boolean" && typeof x.explanation === "string") &&
        e.blanks?.length === 3 && e.blanks.every(x => typeof x.prompt === "string" && typeof x.answer === "string" && typeof x.explanation === "string") &&
        validSections(e.reading, "passage") && validSections(e.listening, "transcript") &&
        ["writing", "speaking"].every(k => ["prompt", "followup", "model"].every(f => typeof e[k]?.[f] === "string")))) {
      throw new Error("Practice content is incomplete.");
    }
    return [...data].sort((a, b) => a.id - b.id);
  }
  function focusHeading() {
    const heading = app.querySelector(step && exam ? ".sheet h2" : "h1");
    if (!heading) return;
    heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
    if (exam && step) {
      const sheet = app.querySelector(".sheet");
      if (sheet && window.innerWidth <= 832) sheet.scrollIntoView({ block: "start" });
      else window.scrollTo(0, 0);
    } else window.scrollTo(0, 0);
  }
  function stopMedia() {
    if (synth) synth.cancel();
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }
  function openFromHash(shouldFocus = true) {
    const match = /^#exam-(10|[1-9])$/.exec(window.location.hash);
    stopMedia();
    exam = match ? exams.find(e => e.id === Number(match[1])) : null;
    if (exam && !snapshots.has(exam.id)) {
      snapshots.set(exam.id, { vocab: [], blanks: [], reading: [], listening: [], drafts: {}, writing: [], speaking: [], transcript: false, step: 0 });
    }
    step = exam ? state().step : 0;
    render(shouldFocus);
  }
  function setStep(next) {
    if (!exam || next < 0 || next >= steps.length || next === step) return;
    stopMedia();
    step = next;
    state().step = next;
    render(true);
  }

  function directory() {
    const lead = node("section", { class: "hero" },
      node("div", {}, text("span", "Independent study workbook · Level C1", "eyebrow"),
        text("h1", "Ten C1 practice exams"),
        p("Practise reading, listening, writing and speaking with original Duolingo-style tasks. See explained answers and sample responses at the end."),
        node("div", { class: "actions" },
          node("a", { class: "btn", href: "#exam-1", text: "Start Exam 01 →" })),
        p("Start with Exam 01 or pick any exam below. No account is needed. Your answers stay in this open page and are not sent anywhere.", "notice")),
      node("div", { class: "cover", "aria-hidden": "true" }, text("span", "Study Lab Workbook"), text("strong", "C1"), text("em", "Ten practice exams")));
    const listing = node("section", { "aria-labelledby": "directory-title" },
      node("h2", { id: "directory-title", class: "directory-title", text: "Table of contents" }));
    const grid = node("ol", { class: "directory", "aria-label": "Practice workbook chapters" });
    for (const item of exams) {
      const resume = snapshots.has(item.id);
      grid.append(node("li", {}, node("a", { class: "exam-card", href: "#exam-" + item.id },
        text("span", examLabel(item.id), "eyebrow"), node("span", {class: "chapter-title"}, text("strong", item.title), text("small", item.theme)),
        text("span", resume ? "Resume" : "Open", "card-open"))));
    }
    listing.append(grid);
    return [lead, listing];
  }
  function choices(group, i, prompt, options, layout = "") {
    const field = node("fieldset", { class: "question " + layout },
      text("legend", (i + 1 + ({ vocab: 0, reading: 9, listening: 13 }[group] || 0)) + ". " + prompt, layout === "vocab" ? "word" : ""));
    const grid = node("div", { class: "options" });
    options.forEach((option, index) => {
      const value = option.value === undefined ? index : option.value;
      grid.append(node("label", { class: "option" },
        node("input", { type: "radio", name: group + "-" + i, checked: state()[group][i] === value, onchange: () => {
          state()[group][i] = value;
          updateCount();
        } }), text("span", option.label ?? option)));
    });
    field.append(grid);
    return field;
  }
  function blanks() {
    return exam.blanks.map((q, i) => {
      const id = "blank-" + i;
      const input = node("input", { class: "input", id, type: "text", autocomplete: "off", autocapitalize: "none", spellcheck: "false", maxlength: 80,
        placeholder: "Type the complete word", oninput: (event) => {
          state().blanks[i] = event.target.value;
          updateCount();
        } });
      input.value = state().blanks[i] || "";
      return node("div", { class: "question" }, node("label", { for: id, class: "result-prompt", text: (i + 7) + ". " + q.prompt }), input);
    });
  }
  function paragraphs(str, className) {
    return node("div", { class: className }, ...str.trim().split(/\n\s*\n/).map(chunk => p(chunk)));
  }
  function listening(panel) {
    const transcript = paragraphs(exam.listening.transcript, "transcript");
    transcript.id = "listening-transcript";
    transcript.hidden = !state().transcript;
    const status = node("p", { role: "status", class: "status", text: synth ? "" : "Audio playback is unavailable in this browser. Use the transcript instead." });
    const reveal = node("button", { type: "button", class: "btn secondary", "aria-expanded": String(state().transcript), "aria-controls": transcript.id,
      text: state().transcript ? "Hide transcript" : "Show transcript", onclick: () => {
        state().transcript = !state().transcript;
        transcript.hidden = !state().transcript;
        reveal.textContent = state().transcript ? "Hide transcript" : "Show transcript";
        reveal.setAttribute("aria-expanded", String(state().transcript));
      } });
    const play = btn("Play audio", () => {
      try {
        synth.cancel();
        const audio = new window.SpeechSynthesisUtterance(exam.listening.transcript);
        audio.lang = "en"; audio.rate = .92;
        audio.onstart = () => { status.textContent = "Playing audio."; };
        audio.onend = () => { status.textContent = "Playback finished."; };
        audio.onerror = (event) => {
          if (event.error !== "canceled" && event.error !== "interrupted") status.textContent = "Audio could not play. Use the transcript instead.";
        };
        synth.speak(audio);
      } catch (_) { status.textContent = "Audio could not play. Use the transcript instead."; }
    });
    const stop = btn("Stop audio", () => { synth.cancel(); status.textContent = "Playback stopped."; }, "btn secondary");
    play.disabled = stop.disabled = !synth;
    panel.append(node("div", { class: "actions" }, play, stop, reveal), status, transcript);
  }
  function timerPanel() {
    const duration = 90;
    const display = node("span", { class: "timer", role: "timer", "aria-label": "Time remaining", text: "01:30" });
    const notice = node("p", { class: "notice", role: "status", text: "Optional speaking timer. No microphone or recording." });
    let remaining = duration;
    function tick(seconds) {
      display.textContent = String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
    }
    const start = btn("Start 90-second timer", () => {
      if (timer !== null) window.clearInterval(timer);
      remaining = duration;
      const end = Date.now() + duration * 1000;
      tick(remaining);
      notice.textContent = "Timer started. Speak aloud.";
      timer = window.setInterval(() => {
        remaining = Math.max(0, Math.ceil((end - Date.now()) / 1000));
        tick(remaining);
        if (!remaining) {
          window.clearInterval(timer);
          timer = null;
          notice.textContent = "Time is up.";
        }
      }, 200);
    });
    const reset = btn("Reset timer", () => {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
      remaining = duration;
      tick(remaining);
      notice.textContent = "Timer reset.";
    }, "btn secondary");
    return [node("div", { class: "actions" }, start, reset, display), notice];
  }
  function rubric(kind) {
    const form = node("div", { class: "rubric" });
    const line = node("p", { class: "count", "aria-live": "polite" });
    const update = () => {
      const values = state()[kind];
      line.textContent = rubricCriteria.every((_, i) => Number.isInteger(values[i]))
        ? "Self-assessment: " + values.reduce((a, b) => a + b, 0) + " / 12"
        : "Select all three criteria to calculate your self-assessment.";
    };
    rubricCriteria.forEach((criterion, i) => {
      const id = kind + "-criterion-" + i;
      const select = node("select", { id, onchange: (event) => {
        state()[kind][i] = event.target.value === "" ? undefined : Number(event.target.value);
        update();
      } }, node("option", { value: "", text: "Choose a score" }));
      rubricLabels.forEach((label, score) => select.append(node("option", { value: score, text: label })));
      select.value = state()[kind][i] ?? "";
      form.append(node("div", { class: "rubric-row" }, node("label", { for: id, text: criterion }), select));
    });
    update();
    return [text("h3", "Self-assess your response"), p("Choose 0 to 4 for each criterion. For task fulfilment, ask whether you answered both prompts. For organisation, check whether your ideas connect. For language control, look at accuracy and choice of words.", "notice"), form, line];
  }
  function productive(panel, kind) {
    const task = exam[kind];
    panel.append(p(task.prompt, "result-prompt"), p("Follow-up: " + task.followup));
    if (kind === "writing") {
      const notes = node("textarea", { class: "draft", id: "writing-response", maxlength: 10000, placeholder: "Write your response here…" });
      notes.value = state().drafts.writing || "";
      notes.addEventListener("input", () => { state().drafts.writing = notes.value; });
      panel.append(node("label", { for: notes.id, class: "writing-label", text: "Your response (optional)" }), notes);
    } else panel.append(...timerPanel());
    const path = node("ol", { class: "model-path", "aria-label": "Suggested response structure" },
      ...[
        ["Answer", "State your position or main idea."],
        ["Develop", "Give a reason and a concrete example."],
        ["Connect", "Address the follow-up and link it to your main idea."]
      ].map(([label, detail]) => node("li", {}, text("strong", label), text("span", detail))));
    panel.append(node("details", { class: "model" }, text("summary", "Show a model response"),
      text("h3", "A three-part response"), path, paragraphs(task.model, "model-content")), ...rubric(kind));
  }

  const norm = (answer) => (answer ?? "").trim().toLowerCase().normalize("NFKC");
  function graded() {
    const answers = state();
    return [
      { name: steps[0], rows: exam.vocab.map((q, i) => {
        const picked = answers.vocab[i];
        return { prompt: q.word, picked: typeof picked === "boolean" ? picked ? "Real word" : "Not a real word" : null,
          correct: q.real ? "Real word" : "Not a real word", ok: picked === q.real, explanation: q.explanation };
      }) },
      { name: steps[1], rows: exam.blanks.map((q, i) => {
        const picked = (answers.blanks[i] || "").trim();
        return { prompt: q.prompt, picked: picked || null, correct: q.answer, ok: norm(picked) === norm(q.answer), explanation: q.explanation };
      }) },
      ...["reading", "listening"].map((key, n) => ({ name: steps[2+n], rows: exam[key].questions.map((q, i) => {
        const picked = answers[key][i];
        return { prompt: q.prompt, picked: q.options[picked] ?? null, correct: q.options[q.answer], ok: picked === q.answer, explanation: q.explanation };
      }) })),
    ];
  }
  function scoreCard(value, maximum, label) {
    const card = node("div", { class: "score" }, text("strong", value === null ? "Not rated" : value + " / " + maximum), text("span", label));
    if (value !== null) card.append(node("progress", { value, max: maximum, "aria-label": label }));
    return card;
  }
  function rubricScore(kind) {
    const values = state()[kind];
    return rubricCriteria.every((_, i) => Number.isInteger(values[i])) ? values.reduce((a, b) => a + b, 0) : null;
  }
  function results(panel) {
    const groups = graded();
    const items = groups.flatMap(g => g.rows);
    const correct = items.filter(row => row.ok).length;
    const missing = items.filter(row => row.picked === null).length;
    panel.append(
      node("div", { class: "scores" }, scoreCard(correct, 17, "Objective score"), scoreCard(rubricScore("writing"), 12, "Writing self-assessment"), scoreCard(rubricScore("speaking"), 12, "Speaking self-assessment")),
      p(missing ? missing + " unanswered " + (missing === 1 ? "question counts" : "questions count") + " as incorrect. Go back to answer or change any question." : "All 17 objective questions were answered. You can go back and revise.", "count"),
      p("These are study scores only. They do not convert to an official Duolingo English Test score. Writing and speaking self-assessments are separate from the objective score.", "notice"),
      node("div", { class: "actions" }, btn("Review writing model", () => setStep(4), "btn secondary"), btn("Review speaking model", () => setStep(5), "btn secondary")));
    for (const [index, group] of groups.entries()) {
      const list = node("ol", { start: [1, 7, 10, 14][index] });
      for (const row of group.rows) {
        const outcome = row.ok ? "Correct" : row.picked === null ? "Unanswered" : "Not correct";
        const evidence = node("dl", { class: "answer-flow" },
          node("div", {}, text("dt", "Your answer"), text("dd", row.picked ?? "Not answered")),
          node("div", { class: "correct-answer" }, text("dt", "Correct answer"), text("dd", row.correct)),
          node("div", { class: "reason" }, text("dt", "Why this works"), text("dd", row.explanation)));
        list.append(node("li", {}, p(row.prompt, "result-prompt"), text("span", outcome, "result-state " + (row.ok ? "right" : "wrong")), evidence));
      }
      panel.append(node("section", { class: "review-group" }, text("h3", group.name), list));
    }
  }
  function answeredCount() {
    const a = state();
    return objectiveKeys.reduce((sum, key) => sum + a[key].filter(value => typeof value === "string" ? value.trim() : value !== undefined).length, 0);
  }
  function updateCount() {
    const live = app.querySelector("#answered-count");
    if (live) live.textContent = answeredCount() + " of 17 objective questions answered";
  }

  function examView() {
    const sidebar = node("nav", { class: "steps", "aria-label": "Exam sections" });
    steps.forEach((label, i) => {
      const button = btn("", () => setStep(i), "");
      button.append(text("span", String(i + 1).padStart(2, "0"), "step-no"), text("span", label));
      if (i === step) button.setAttribute("aria-current", "step");
      sidebar.append(button);
    });
    const heading = node("header", { class: "exam-head" },
      node("a", { href: "#", class: "toplink", text: "← All practice exams" }),
      text("span", examLabel(exam.id) + " · C1 workbook", "eyebrow"),
      text("h1", exam.title), p(exam.theme, "theme"));
    const panel = node("section", { class: "sheet", "data-step": step+1, "aria-labelledby": "section-title" }, node("h2", { id: "section-title", text: steps[step] }));
    const directions = [
      "Decide whether each item is a real English word.", "Use the context and the letters supplied. Type the full word, not just the missing letters.",
      "Read the passage and choose the best answer to each question.", "Listen, then choose the best answer. Use the transcript if you need it.",
      "Respond to the main prompt and the follow-up. Compare your response with the model, then rate it.",
      "Speak aloud for the main prompt and the follow-up. Compare your response with the model, then rate it."
    ];
    if (step < directions.length) panel.append(p(directions[step], "instructions"));
    if (step === 0) panel.append(...exam.vocab.map((q, i) => choices("vocab", i, q.word, [{ label: "Real word", value: true }, { label: "Not a real word", value: false }], "vocab")));
    if (step === 1) panel.append(...blanks());
    if (step === 2) panel.append(paragraphs(exam.reading.passage, "passage"), ...exam.reading.questions.map((q, i) => choices("reading", i, q.prompt, q.options)));
    if (step === 3) {
      listening(panel);
      panel.append(...exam.listening.questions.map((q, i) => choices("listening", i, q.prompt, q.options)));
    }
    if (step === 4 || step === 5) productive(panel, step === 4 ? "writing" : "speaking");
    if (step === 6) results(panel);
    const previous = step ? btn("← Back: " + steps[step - 1], () => setStep(step - 1), "btn secondary") :
      node("a", { href: "#", class: "btn secondary", text: "← All exams" });
    const next = step === 6 ? node("a", { href: exam.id < 10 ? "#exam-" + (exam.id + 1) : "#", class: "btn", text: exam.id < 10 ? "Next exam →" : "Back to contents →" }) :
      btn(step === 5 ? "See scores and explanations →" : "Next: " + steps[step + 1] + " →", () => setStep(step + 1));
    panel.append(node("div", { class: "next-row" }, previous, next));
    const progress = node("div", { class: "progress-line" },
      text("span", "Section " + (step + 1) + " of " + steps.length),
      node("progress", { max: steps.length, value: step + 1, "aria-label": "Your position in this exam" }));
    return [heading, node("div", { class: "workspace" }, sidebar, node("div", {}, progress, panel, node("p", { class: "notice", id: "answered-count", "aria-live": "polite" })))];
  }
  function render(focus = false) {
    app.replaceChildren(...(exam ? examView() : directory()));
    if (exam) updateCount();
    if (focus) focusHeading();
  }
  async function load() {
    try {
      const response = await fetch("./exams.json", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Could not load practice.");
      exams = validate(await response.json());
      openFromHash(false);
      window.addEventListener("hashchange", () => openFromHash(true));
      window.addEventListener("pagehide", stopMedia);
    } catch (_) {
      app.replaceChildren(node("section", { class: "alert", role: "alert" }, text("h1", "Practice exams are unavailable"),
        p("The questions could not be loaded. Try reloading this page, or head back to the course."),
        node("div", { class: "actions" }, btn("Reload this page", () => window.location.reload()),
          node("a", { class: "btn secondary", href: "../", text: "Back to the course" }))));
    }
  }
  load();
})();
