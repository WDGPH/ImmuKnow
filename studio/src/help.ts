const byId = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const required = <T extends HTMLElement = HTMLElement>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing walkthrough target: ${selector}`);
  return element;
};
const steps = [
  {
    target: "#template",
    theme: true,
    title: "Choose a template starter",
    text: "Open Theme → Template starters to choose a template and language. Your edits are kept when you switch.",
  },
  {
    target: ".client-controls",
    title: "Try different clients",
    text: "Try different examples to check long addresses and short or long records.",
  },
  {
    target: ".editor-pane .pane-heading",
    title: "Write your notice",
    text: "Edit the template here. The preview updates as you type.",
  },
  {
    target: ".preview-pane .pane-heading",
    title: "Review every page",
    text: "Scroll through the pages. Double-click text to highlight its code. Use − and + to zoom; drag the divider to resize.",
  },
  {
    target: "#settings-tab",
    settings: true,
    title: "Set paper and envelope",
    text: "Edit paper size and window dimensions in the settings file. Commented examples show the alternatives.",
  },
  {
    target: ".asset-card",
    theme: true,
    title: "Add your branding",
    text: "Use Theme to choose fonts and colours, or change your logo and signature.",
  },
  {
    target: ".preview-options",
    settings: true,
    title: "Check the envelope window",
    text: "Show the envelope window to check the address position. The outline does not appear in notices.",
  },
  {
    target: ".project-actions summary",
    title: "Save your work",
    text: "Open Project to download your complete project or import a saved ZIP.",
  },
  {
    target: ".project-actions summary",
    title: "Manage your project",
    text: "Export a project to save all your work, including images. Import it to pick up where you left off.",
  },
  {
    target: "#help-open",
    title: "Replay the walkthrough",
    text: "Use the question mark whenever you want to revisit this walkthrough.",
  },
];

export function initializeHelp(showSettings: (tab?: "settings" | "theme") => () => void) {
  const tour = byId<HTMLDialogElement>("tour-dialog");
  const trigger = byId("help-open");
  const card = byId("tour-card");
  const highlight = byId("tour-highlight");
  const back = byId<HTMLButtonElement>("tour-back");
  const next = byId<HTMLButtonElement>("tour-next");
  let index = 0;
  let restorePanel: (() => void) | undefined;
  let originalScroll = 0;
  let frame = 0;
  const restoreDetails = () => {
    restorePanel?.();
    restorePanel = undefined;
  };
  const position = () => {
    if (!tour.open) return;
    const target = required(steps[index].target);
    let rect = target.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    const height = window.innerHeight;
    const cardHeight = card.offsetHeight,
      cardWidth = card.offsetWidth;
    // On short screens, move the target toward the top so the explanation fits below it.
    if (
      rect.bottom + cardHeight + 51 > height &&
      rect.top < cardHeight + 51 &&
      rect.height + cardHeight + 62 < height
    ) {
      window.scrollBy({ top: rect.top - 16, behavior: "instant" });
      rect = target.getBoundingClientRect();
    }
    const left = Math.max(4, rect.left - 5),
      top = Math.max(4, rect.top - 5);
    const right = Math.min(width - 4, rect.right + 5),
      bottom = Math.min(height - 4, rect.bottom + 5);
    Object.assign(highlight.style, {
      left: `${left}px`,
      top: `${top}px`,
      width: `${Math.max(0, right - left)}px`,
      height: `${Math.max(0, bottom - top)}px`,
    });
    const below = bottom + 30 + cardHeight <= height - 16;
    const y = below ? bottom + 30 : Math.max(16, top - cardHeight - 30);
    const x = Math.max(16, Math.min(width - cardWidth - 16, left));
    Object.assign(card.style, { left: `${x}px`, top: `${y}px` });
    const startX = Math.max(x + 24, Math.min(x + cardWidth - 24, (left + right) / 2));
    const endX = Math.max(left + 8, Math.min(right - 8, startX));
    const startY = below ? y : y + cardHeight;
    const endY = below ? bottom + 4 : top - 4;
    byId("tour-line").setAttribute("d", `M ${startX} ${startY} L ${endX} ${endY}`);
  };
  const schedulePosition = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(position);
  };
  const showStep = () => {
    restoreDetails();
    const step = steps[index];
    if (step.settings) restorePanel = showSettings();
    if (step.theme) restorePanel = showSettings("theme");
    byId("tour-progress").textContent = `Step ${index + 1} of ${steps.length}`;
    byId("tour-title").textContent = step.title;
    byId("tour-text").textContent = step.text;
    back.disabled = index === 0;
    next.textContent = index === steps.length - 1 ? "Finish" : "Next";
    document
      .querySelector(steps[index].target)
      ?.scrollIntoView({ block: "center", behavior: "instant" });
    position();
    next.focus({ preventScroll: true });
  };
  const project = required<HTMLDetailsElement>(".project-actions");
  document.addEventListener("click", (event) => {
    if (tour.open) return;
    if (!project.contains(event.target as Node) || (event.target as Element).closest("button"))
      project.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && project.open && !tour.open) {
      project.open = false;
      project.querySelector<HTMLElement>("summary")?.focus();
    }
  });
  tour.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      next.click();
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      back.click();
    }
  });
  trigger.onclick = () => {
    originalScroll = window.scrollY;
    index = 0;
    tour.showModal();
    showStep();
  };
  back.onclick = () => {
    if (index > 0) {
      index--;
      showStep();
    }
  };
  next.onclick = () => {
    if (index === steps.length - 1) tour.close();
    else {
      index++;
      showStep();
    }
  };
  byId("tour-close").onclick = () => tour.close();
  tour.addEventListener("close", () => {
    cancelAnimationFrame(frame);
    restoreDetails();
    window.scrollTo({ top: originalScroll, behavior: "instant" });
    trigger.focus({ preventScroll: true });
  });
  window.addEventListener("resize", schedulePosition);
  window.addEventListener("scroll", schedulePosition, true);
  new ResizeObserver(schedulePosition).observe(card);
}
