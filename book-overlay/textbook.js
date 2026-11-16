/* A presentation layer for the published React course. Practice stays in the original app. */
(() => {
  "use strict";
  const assets = new URL("../", document.currentScript.src);
  const root = document.getElementById("root");
  if (!root) return;
  const take = (parent, selector) => parent.querySelector(selector);
  const make = (tag, name, text) => {
    const item = document.createElement(tag);
    if (name) item.className = name;
    if (text) item.textContent = text;
    return item;
  };

  function addMembership(container) {
    if (!container || take(container, "[data-esl-membership-link]")) return;
    const link = make("a", "esl-book-membership", "Free membership");
    link.href = new URL("membership/", assets).href;
    link.setAttribute("data-esl-membership-link", "");
    link.hidden = document.documentElement.dataset.eslMembershipConfigured !== "true";
    container.prepend(link);
  }

  function addCover(cover) {
    if (take(cover, ".esl-book-imprint")) return;
    const imprint = make("div", "esl-book-imprint");
    imprint.append(make("span", "", "English Study Lab"), make("span", "", "Independent Learning Series"));
    cover.prepend(imprint);
    const actions = take(cover, ".ac-hero-buttons");
    if (actions) {
      const det = make("a", "esl-book-det", "Open the practice workbook");
      det.href = new URL("practice/", assets).href;
      actions.after(det);
    }
  }

  function addContents(site) {
    const level = take(site, ".ac-level-band");
    const existing = take(site, ".esl-book-contents");
    if (!level) {
      existing?.remove();
      return;
    }
    if (existing) return;
    const list = make("nav", "esl-book-contents");
    list.setAttribute("aria-label", "Textbook contents");
    list.append(make("span", "esl-book-contents-title", "Table of contents"));
    list.append(make("span", "esl-book-part", "Part 1 · Coursebook"));
    const sections = [
      [".ac-level-band", "esl-volumes", "01", "Choose your level"],
      [".ac-skills-section", "esl-skills", "02", "Study by skill"],
      [".ac-catalogue", "esl-lessons", "03", "Lesson index"],
      [".ac-media", "esl-listen-watch", "04", "Listen & watch"],
      [".ac-exam-section", "esl-exams", "05", "Exam practice"],
    ];
    for (const [selector, id, number, label] of sections) {
      const section = take(site, selector);
      if (!section) continue;
      if (!section.id) section.id = id;
      const link = make("a", "", label);
      link.href = "#" + section.id;
      link.prepend(make("small", "", number));
      list.append(link);
    }
    list.append(make("span", "esl-book-part", "Part 2 · Practice workbook"));
    const workbook = make("a", "esl-book-workbook", "Ten C1 practice exams");
    workbook.prepend(make("small", "", "06"));
    workbook.href = new URL("practice/", assets).href;
    list.append(workbook);
    level.before(list);
  }

  function decorate() {
    const site = take(root, ".ac-site");
    if (site) {
      addMembership(take(site, ".ac-header-actions"));
      const cover = take(site, ".ac-hero-copy");
      if (cover) addCover(cover);
      addContents(site);
    }
    const exam = take(root, ".lab-sidebar-bottom");
    if (exam) addMembership(exam);
  }

  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      decorate();
    });
  });
  observer.observe(root, { childList: true, subtree: true });
  decorate();
})();
