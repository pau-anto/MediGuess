/*
 * MediGuess — logique du jeu (style visual novel).
 * Ne parle au serveur qu'à travers api.js : le contrat d'API ne change pas.
 */
const $ = (id) => document.getElementById(id);
const MAX_LIVES = 3;
const TYPE_SPEED_MS = 22;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const game = { lives: MAX_LIVES, score: 0, caseCount: 0, caseId: null, mode: "title" };

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const pick = (list) => list[Math.floor(Math.random() * list.length)];

// ---------------------------------------------------------------------------
// Patient dessiné en SVG (apparence tirée au hasard à chaque cas)
// ---------------------------------------------------------------------------
const LOOKS = {
  skin: ["#fbe0c8", "#f5d0b0", "#e0ac80", "#c68a5e", "#8d5a3b"],
  hair: ["#2b1d14", "#6b3e1f", "#d9a441", "#1a1a1a", "#b0463c", "#9aa0a6"],
  shirt: ["#f2a541", "#5b8def", "#e26d5a", "#7cc68d", "#b084cc"],
  style: ["short", "bun", "long"],
};

const MOODS = {
  worried: { brows: "M-65 372 L-20 360 M20 360 L65 372", mouth: "M-24 462 Q0 450 24 462" },
  happy: { brows: "M-65 360 Q-42 350 -20 360 M20 360 Q42 350 65 360", mouth: "M-32 450 Q0 482 32 450" },
  sad: { brows: "M-65 368 L-20 356 M20 356 L65 368", mouth: "M-28 468 Q0 446 28 468" },
};

function randomLook() {
  return {
    skin: pick(LOOKS.skin), hair: pick(LOOKS.hair),
    shirt: pick(LOOKS.shirt), style: pick(LOOKS.style),
  };
}

function drawPatient(look, mood = "worried") {
  const { brows, mouth } = MOODS[mood];
  const hairBack = look.style === "long"
    ? `<path d="M-125 400 Q-135 560 -80 580 L80 580 Q135 560 125 400 Z" fill="${look.hair}"/>` : "";
  const bun = look.style === "bun" ? `<circle cx="0" cy="282" r="46" fill="${look.hair}"/>` : "";
  $("patient").innerHTML = `
    <rect x="-175" y="380" width="350" height="380" rx="44" fill="#3e5c76"/>
    ${hairBack}
    <rect x="-150" y="520" width="300" height="260" rx="95" fill="${look.shirt}"/>
    <rect x="-34" y="470" width="68" height="70" rx="20" fill="${look.skin}"/>
    <circle cx="-108" cy="410" r="22" fill="${look.skin}"/>
    <circle cx="108" cy="410" r="22" fill="${look.skin}"/>
    <circle cx="0" cy="400" r="110" fill="${look.skin}"/>
    ${bun}
    <path d="M-114 400 Q-122 282 0 282 Q122 282 114 400 Q92 332 0 336 Q-92 332 -114 400 Z" fill="${look.hair}"/>
    <circle cx="-40" cy="405" r="11" fill="#1e2a33"/>
    <circle cx="40" cy="405" r="11" fill="#1e2a33"/>
    <circle cx="-70" cy="440" r="16" fill="#f28b82" opacity="0.35"/>
    <circle cx="70" cy="440" r="16" fill="#f28b82" opacity="0.35"/>
    <path d="${brows}" stroke="#1e2a33" stroke-width="8" stroke-linecap="round" fill="none"/>
    <path d="${mouth}" stroke="#1e2a33" stroke-width="7" stroke-linecap="round" fill="none"/>`;
}

// ---------------------------------------------------------------------------
// Boîte de dialogue avec effet machine à écrire
// ---------------------------------------------------------------------------
const talk = { queue: [], typing: null, onDone: null };

function say(speaker, lines, onDone) {
  game.mode = "talk";
  $("speaker").textContent = speaker;
  $("dialogue").classList.add("clickable");
  talk.queue = [...lines];
  talk.onDone = onDone;
  nextLine();
}

function nextLine() {
  const item = talk.queue.shift();
  if (!item) {
    $("dialogue").classList.remove("clickable");
    talk.onDone();
    return;
  }
  if (item.onShow) item.onShow();

  const body = $("dialogue-body");
  body.innerHTML = '<p class="line"></p><span class="next-hint" aria-hidden="true">▼</span>';
  const line = body.querySelector(".line");
  if (reducedMotion) {
    line.textContent = item.text;
    return;
  }
  let i = 0;
  talk.typing = setInterval(() => {
    i += 1;
    line.textContent = item.text.slice(0, i);
    if (i >= item.text.length) finishTyping();
  }, TYPE_SPEED_MS);
  talk.full = item.text;
}

function finishTyping() {
  clearInterval(talk.typing);
  talk.typing = null;
  const line = document.querySelector("#dialogue-body .line");
  if (line) line.textContent = talk.full;
}

function advance() {
  if (game.mode !== "talk") return;
  if (talk.typing) finishTyping();
  else nextLine();
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------
function renderHud() {
  $("score").textContent = game.score;
  $("lives").innerHTML = Array.from({ length: MAX_LIVES }, (_, i) =>
    `<span class="${i < game.lives ? "" : "lost"}">♥</span>`).join("");
  $("lives").setAttribute("aria-label", `${game.lives} vies restantes`);
}

// ---------------------------------------------------------------------------
// Déroulé d'un cas
// ---------------------------------------------------------------------------
const INTROS = [
  "Bonjour docteur... Je ne me sens vraiment pas bien.",
  "Docteur, merci de me recevoir. Ça ne va pas du tout.",
  "Bonjour. Je viens parce que plusieurs choses m'inquiètent.",
];
const LEADS = ["J'ai remarqué : ", "Il y a aussi : ", "Et puis : ", "Ah, et aussi : ", "Sans oublier : "];

async function startCase() {
  game.mode = "loading";
  $("stamp").hidden = true;
  $("dialogue-body").innerHTML = '<p class="line">Le patient suivant arrive...</p>';
  let data;
  try {
    data = await api.getCase();
  } catch (err) {
    showMessage("Connexion impossible", `Le cas n'a pas pu être chargé. ${err.message}`, "Réessayer", startCase);
    return;
  }
  game.caseId = data.case_id;
  game.caseCount += 1;
  game.look = randomLook();
  drawPatient(game.look, "worried");

  const name = `Patient n°${String(game.caseCount).padStart(3, "0")}`;
  $("patient-name").textContent = name;
  $("symptoms").replaceChildren();
  $("clipboard").hidden = false;

  const lines = [{ text: pick(INTROS) }];
  data.symptoms.forEach((symptom, i) => {
    lines.push({
      text: `${LEADS[i % LEADS.length]}${symptom}.`,
      onShow: () => addSymptom(symptom),
    });
  });
  say(name, lines, () => showChoices(data.choices));
}

function addSymptom(symptom) {
  const li = document.createElement("li");
  li.dataset.symptom = symptom;
  const span = document.createElement("span");
  span.textContent = capitalize(symptom);
  li.append(span);
  $("symptoms").append(li);
}

function showChoices(choices) {
  game.mode = "choose";
  $("speaker").textContent = "Vous";
  const body = $("dialogue-body");
  // tabindex=-1 : le focus va sur la question et non sur un bouton, sinon un
  // appui sur Espace (pour passer le dialogue) validerait un choix par erreur.
  body.innerHTML = '<p class="question" tabindex="-1">Quel est votre diagnostic ?</p><div class="choices"></div>';
  const grid = body.querySelector(".choices");
  choices.forEach((disease, i) => {
    const button = document.createElement("button");
    button.className = "choice";
    button.dataset.disease = disease;
    button.innerHTML = `<kbd>${i + 1}</kbd>`;
    button.append(capitalize(disease));
    button.addEventListener("click", () => answer(disease));
    grid.append(button);
  });
  body.querySelector(".question").focus();
}

async function answer(disease) {
  if (game.mode !== "choose") return;
  game.mode = "waiting";
  let result;
  try {
    result = await api.postAnswer(game.caseId, disease);
  } catch (err) {
    game.mode = "choose";
    $("speaker").textContent = "Réponse non envoyée, réessayez";
    return;
  }
  game.score += result.points;
  if (!result.correct) game.lives -= 1;
  renderHud();
  showResult(disease, result);
}

function showResult(chosen, { correct, correct_answer, points, feedback, explanation }) {
  game.mode = "result";
  document.querySelectorAll(".choice").forEach((button) => {
    button.disabled = true;
    if (button.dataset.disease === correct_answer) button.classList.add("is-correct");
    else if (button.dataset.disease === chosen) button.classList.add("is-wrong");
  });

  drawPatient(game.look, correct ? "happy" : "sad");
  const stamp = $("stamp");
  stamp.textContent = correct ? "Bon diagnostic" : "Raté";
  stamp.className = `stamp ${correct ? "ok" : "ko"}`;
  stamp.hidden = false;

  // Surligne dans le dossier les symptômes décisifs (SHAP, présents et "pour")
  const keys = new Set(explanation.factors
    .filter((f) => f.present && f.direction === "pour").map((f) => f.symptom));
  document.querySelectorAll("#symptoms li").forEach((li) =>
    li.classList.toggle("is-key", keys.has(li.dataset.symptom)));

  // Panneau de correction dans la boîte de dialogue (après un court délai
  // pour laisser voir les boutons colorés)
  setTimeout(() => {
    $("speaker").textContent = "Correction";
    const maxWeight = Math.max(...explanation.factors.map((f) => Math.abs(f.contribution)));
    const body = $("dialogue-body");
    body.innerHTML = `
      <div class="result">
        <div>
          <p class="verdict ${correct ? "ok" : "ko"}"></p>
          <p class="feedback"></p>
          <ul class="factors"></ul>
        </div>
        <button class="action"></button>
      </div>`;
    body.querySelector(".verdict").textContent = correct
      ? `Exact : ${capitalize(correct_answer)}, +${points} points`
      : `C'était : ${capitalize(correct_answer)}`;
    body.querySelector(".feedback").textContent = feedback || "";
    const list = body.querySelector(".factors");
    explanation.factors.forEach((f) => {
      const li = document.createElement("li");
      li.className = f.direction === "pour" ? "for" : "against";
      li.innerHTML = '<span class="name"><small></small></span><span class="bar"><span></span></span>';
      li.querySelector(".name").prepend(capitalize(f.symptom));
      li.querySelector("small").textContent =
        `${f.present ? "Présent" : "Absent"}, ${f.direction === "pour" ? "oriente vers" : "éloigne de"} ce diagnostic`;
      li.querySelector(".bar span").style.width =
        `${Math.round((Math.abs(f.contribution) / maxWeight) * 100)}%`;
      list.append(li);
    });
    const button = body.querySelector(".action");
    if (game.lives > 0) {
      button.textContent = "Patient suivant";
      button.addEventListener("click", startCase);
    } else {
      button.textContent = "Voir le bilan";
      button.addEventListener("click", gameOver);
    }
    button.focus();
  }, reducedMotion ? 0 : 700);
}

// ---------------------------------------------------------------------------
// Écrans titre / fin
// ---------------------------------------------------------------------------
function showMessage(title, text, buttonLabel, onClick) {
  game.mode = "menu";
  $("speaker").textContent = "";
  const body = $("dialogue-body");
  body.innerHTML = '<div class="title-card"><h2></h2><p></p><button class="action"></button></div>';
  body.querySelector("h2").textContent = title;
  body.querySelector("p").textContent = text;
  const button = body.querySelector(".action");
  button.textContent = buttonLabel;
  button.addEventListener("click", onClick);
  button.focus();
}

function newGame() {
  Object.assign(game, { lives: MAX_LIVES, score: 0, caseCount: 0 });
  renderHud();
  startCase();
}

function gameOver() {
  $("clipboard").hidden = true;
  $("patient").innerHTML = "";
  const cases = game.caseCount;
  showMessage(
    "Fin de la garde",
    `Vous avez examiné ${cases} patient${cases > 1 ? "s" : ""} et marqué ${game.score} points.`,
    "Rejouer",
    newGame
  );
}

// ---------------------------------------------------------------------------
// Contrôles : clic sur la boîte de dialogue, Espace/Entrée, touches 1 à 4
// ---------------------------------------------------------------------------
$("dialogue").addEventListener("click", (event) => {
  if (!event.target.closest("button")) advance();
});

document.addEventListener("keydown", (event) => {
  if (game.mode === "talk" && (event.key === " " || event.key === "Enter")) {
    event.preventDefault();
    advance();
  } else if (game.mode === "choose" && ["1", "2", "3", "4"].includes(event.key)) {
    const button = document.querySelectorAll(".choice")[Number(event.key) - 1];
    if (button) button.click();
  }
});

renderHud();
drawPatient(randomLook(), "happy");
showMessage(
  "Bienvenue au cabinet, docteur",
  "Écoutez chaque patient, notez ses symptômes et posez le bon diagnostic parmi quatre propositions. Trois erreurs et la garde est terminée.",
  "Ouvrir le cabinet",
  newGame
);
