/*
 * MediGuess — logique du jeu (style visual novel).
 * Ne parle au serveur qu'à travers api.js. Le score et les vies sont tenus
 * par le serveur : ce fichier ne fait que les afficher.
 */
const $ = (id) => document.getElementById(id);
const MAX_LIVES = 3;
const TYPE_SPEED_MS = 22;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const game = {
  lives: MAX_LIVES, score: 0, caseCount: 0, caseId: null, gameId: null, mode: "title",
  adminMode: false,
};
// Joueur connecté : admin ou non (renvoyé par /me), et case « mode admin »
const player = { isAdmin: false, wantsAdminMode: false };

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
  const user = api.user();
  $("player").textContent = user ? `Dr ${user}` : "Invité";
  $("player").classList.toggle("guest", !user);
  $("admin-badge").hidden = !game.adminMode;
  $("quit").hidden = !game.gameId;
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
    data = await api.getCase(game.gameId);
    if (game.mode !== "loading") return; // le joueur a quitté pendant le chargement
  } catch (err) {
    if (game.mode !== "loading") return;
    if (err.status === 409) return gameOver(); // partie déjà terminée côté serveur
    if (err.status === 401) return sessionExpired();
    showCard({
      title: "Connexion impossible",
      text: `Le cas n'a pas pu être chargé. ${err.message}`,
      buttons: [{ label: "Réessayer", onClick: startCase }, { label: "Menu", onClick: showMenu, secondary: true }],
    });
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
  say(name, lines, () => showChoices(data.choices, data.answer));
}

function addSymptom(symptom) {
  const li = document.createElement("li");
  li.dataset.symptom = symptom;
  const span = document.createElement("span");
  span.textContent = capitalize(symptom);
  li.append(span);
  $("symptoms").append(li);
}

/** answer : fourni par le serveur uniquement pour une partie en mode admin. */
function showChoices(choices, answer) {
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
    if (answer && disease === answer) {
      button.classList.add("is-answer");
      button.title = "Bonne réponse (mode admin)";
    }
    button.addEventListener("click", () => submitAnswer(disease));
    grid.append(button);
  });
  body.querySelector(".question").focus();
}

async function submitAnswer(disease) {
  if (game.mode !== "choose") return;
  game.mode = "waiting";
  let result;
  try {
    result = await api.postAnswer(game.caseId, disease);
  } catch (err) {
    if (err.status === 401) return sessionExpired();
    if (err.status === 404 || err.status === 409) return gameOver(); // cas expiré
    game.mode = "choose";
    $("speaker").textContent = "Réponse non envoyée, réessayez";
    return;
  }
  // Score et vies : valeurs du serveur, pas de calcul local
  game.score = result.game.score;
  game.lives = result.game.lives;
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
    if (game.mode !== "result") return; // le joueur a quitté entre-temps
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
// Écrans : menu, connexion, fin de partie, classement
// ---------------------------------------------------------------------------
/**
 * Carte affichée dans la boîte de dialogue.
 * buttons : [{ label, onClick, secondary }] ; content : nœud DOM optionnel.
 */
function showCard({ title, text = "", content = null, buttons = [] }) {
  game.mode = "menu";
  $("quit").hidden = true;
  $("speaker").textContent = "";
  const body = $("dialogue-body");
  body.innerHTML = '<div class="title-card"><h2></h2><p class="card-text"></p><div class="card-buttons"></div></div>';
  body.querySelector("h2").textContent = title;
  body.querySelector(".card-text").textContent = text;
  if (content) body.querySelector(".card-text").after(content);
  const row = body.querySelector(".card-buttons");
  buttons.forEach(({ label, onClick, secondary }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = secondary ? "action secondary" : "action";
    button.textContent = label;
    button.addEventListener("click", onClick);
    row.append(button);
  });
  const first = row.querySelector("button");
  if (first && !content?.querySelector?.("input")) first.focus();
  return body;
}

function resetScene() {
  $("clipboard").hidden = true;
  $("stamp").hidden = true;
  drawPatient(randomLook(), "happy");
}

/** Partie sauvegardée à reprendre (compte : côté serveur ; invité : ce navigateur). */
async function findSavedGame() {
  try {
    if (api.user()) return await api.currentGame();
    const id = api.savedGameId();
    if (!id) return null;
    const saved = await api.getGame(id);
    if (saved.game_over || saved.cases === 0) { api.forgetGame(); return null; }
    return saved;
  } catch (err) {
    if (err.status === 401) throw err;
    if (!api.user()) api.forgetGame();
    return null; // 404 : aucune partie en cours
  }
}

const savedSummary = (saved) =>
  `Partie en cours : ${saved.score} point${saved.score > 1 ? "s" : ""}, `
  + `${saved.lives} vie${saved.lives > 1 ? "s" : ""}, ${saved.cases} patient${saved.cases > 1 ? "s" : ""} vu${saved.cases > 1 ? "s" : ""}`
  + `${saved.admin_mode ? " (mode admin)" : ""}.`;

async function showMenu() {
  resetScene();
  Object.assign(game, { lives: MAX_LIVES, score: 0, caseCount: 0, gameId: null, adminMode: false });
  $("admin-panel").hidden = true;
  renderHud();
  const user = api.user();
  if (!user) player.isAdmin = false;
  const token = (showMenu.token = (showMenu.token || 0) + 1);
  showCard({ title: user ? `Bienvenue, Dr ${user}` : "Bienvenue au cabinet, docteur", text: "Chargement..." });

  let me = null;
  let saved = null;
  try {
    [me, saved] = await Promise.all([user ? api.me() : null, findSavedGame()]);
  } catch (err) {
    if (err.status === 401) return sessionExpired();
  }
  if (token !== showMenu.token) return; // un autre écran a été ouvert entre-temps
  player.isAdmin = Boolean(me?.is_admin);

  const buttons = [];
  if (saved) {
    buttons.push({ label: "Reprendre la partie", onClick: () => resumeGame(saved) });
    // Nouvelle partie : le serveur termine l'ancienne et enregistre son score
    buttons.push({ label: "Nouvelle partie", onClick: newGame, secondary: true });
  } else {
    buttons.push({ label: user ? "Ouvrir le cabinet" : "Jouer en invité", onClick: newGame, secondary: !user });
  }
  if (!user) {
    buttons.unshift(
      { label: "Se connecter", onClick: () => showAuthForm("login") },
      { label: "Créer un compte", onClick: () => showAuthForm("register") },
    );
  }
  buttons.push({ label: "Classement", onClick: () => showLeaderboard(), secondary: true });
  if (user) buttons.push({ label: "Se déconnecter", onClick: logout, secondary: true });

  let text;
  if (saved) text = savedSummary(saved);
  else if (!user) {
    text = "Écoutez chaque patient, notez ses symptômes et posez le bon diagnostic parmi "
      + "quatre propositions. Trois erreurs et la partie est terminée. "
      + "Connectez-vous pour enregistrer vos scores et entrer au classement.";
  } else if (me?.games_played) {
    text = `Record : ${me.best_score} points · ${me.games_played} partie${me.games_played > 1 ? "s" : ""} · `
      + `${Math.round(me.accuracy * 100)} % de bons diagnostics`;
  } else text = "Votre première partie vous attend. Bonne chance !";

  const body = showCard({
    title: user ? `Bienvenue, Dr ${user}` : "Bienvenue au cabinet, docteur",
    text,
    buttons,
  });
  if (player.isAdmin) addAdminControls(body);
}

function resumeGame(saved) {
  Object.assign(game, {
    lives: saved.lives, score: saved.score, caseCount: saved.cases,
    gameId: saved.game_id, adminMode: saved.admin_mode,
  });
  api.rememberGame(saved.game_id);
  renderHud();
  startCase(); // le serveur renvoie le cas laissé en suspens, s'il y en a un
}

/** Bouton « Sauvegarder et quitter » : rien à envoyer, le serveur a déjà tout. */
function quitGame() {
  if (!["talk", "choose", "result", "loading"].includes(game.mode)) return;
  finishTyping();
  talk.queue = [];
  showMenu();
}

function logout() {
  api.logout();
  showMenu();
}

function sessionExpired() {
  api.logout();
  resetScene();
  renderHud();
  showCard({
    title: "Session expirée",
    text: "Reconnectez-vous pour continuer à enregistrer vos scores.",
    buttons: [
      { label: "Se connecter", onClick: () => showAuthForm("login") },
      { label: "Menu", onClick: showMenu, secondary: true },
    ],
  });
}

function showAuthForm(mode) {
  const register = mode === "register";
  const form = document.createElement("form");
  form.className = "auth-form";
  form.noValidate = false;
  form.innerHTML = `
    <label>Pseudo
      <input name="username" required minlength="3" maxlength="20"
        pattern="[A-Za-z0-9_\\-]{3,20}" autocomplete="username" spellcheck="false">
    </label>
    <label>Mot de passe
      <input name="password" type="password" required minlength="${register ? 8 : 1}"
        maxlength="128" autocomplete="${register ? "new-password" : "current-password"}">
    </label>
    <p class="hint"></p>
    <p class="form-error" role="alert"></p>
    <div class="card-buttons">
      <button type="submit" class="action"></button>
      <button type="button" class="action secondary" data-back>Retour</button>
    </div>
    <button type="button" class="link" data-switch></button>`;
  form.querySelector(".hint").textContent = register
    ? "Pseudo : 3 à 20 caractères (lettres, chiffres, - ou _). Mot de passe : 8 caractères minimum."
    : "";
  form.querySelector("[type=submit]").textContent = register ? "Créer mon compte" : "Se connecter";
  form.querySelector("[data-switch]").textContent = register
    ? "Déjà un compte ? Se connecter"
    : "Pas encore de compte ? En créer un";
  form.querySelector("[data-back]").addEventListener("click", showMenu);
  form.querySelector("[data-switch]").addEventListener("click", () =>
    showAuthForm(register ? "login" : "register"));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    const error = form.querySelector(".form-error");
    const username = form.username.value.trim();
    const password = form.password.value;
    submit.disabled = true;
    error.textContent = "";
    try {
      await (register ? api.register(username, password) : api.login(username, password));
      showMenu();
    } catch (err) {
      error.textContent = err.status === 422
        ? "Pseudo ou mot de passe au mauvais format."
        : err.message;
      submit.disabled = false;
    }
  });

  showCard({ title: register ? "Créer un compte" : "Connexion", content: form });
  form.username.focus();
}

async function newGame() {
  game.mode = "loading";
  let data;
  try {
    data = await api.startGame(player.isAdmin && player.wantsAdminMode);
  } catch (err) {
    if (err.status === 401) return sessionExpired();
    showCard({
      title: "Connexion impossible",
      text: `La partie n'a pas pu commencer. ${err.message}`,
      buttons: [{ label: "Réessayer", onClick: newGame }, { label: "Menu", onClick: showMenu, secondary: true }],
    });
    return;
  }
  Object.assign(game, {
    lives: data.lives, score: data.score, caseCount: 0, gameId: data.game_id, adminMode: data.admin_mode,
  });
  api.rememberGame(data.game_id);
  renderHud();
  startCase();
}

function gameOver() {
  api.forgetGame();
  game.mode = "menu";
  $("clipboard").hidden = true;
  $("patient").innerHTML = "";
  const cases = game.caseCount;
  const user = api.user();
  const summary = `Vous avez examiné ${cases} patient${cases > 1 ? "s" : ""} et marqué ${game.score} points.`;
  const buttons = [
    { label: "Rejouer", onClick: newGame },
    { label: "Classement", onClick: () => showLeaderboard(gameOver), secondary: true },
    { label: "Menu", onClick: showMenu, secondary: true },
  ];
  if (!user) buttons.splice(1, 0, { label: "Créer un compte", onClick: () => showAuthForm("register") });
  showCard({
    title: "Fin de la partie",
    text: game.adminMode
      ? `${summary} Partie en mode admin : non comptée.`
      : user
        ? `${summary} Score enregistré au classement.`
        : `${summary} En invité, ce score n'est pas enregistré.`,
    buttons,
  });
}

async function showLeaderboard(back = showMenu) {
  const body = showCard({
    title: "Classement",
    text: "Chargement...",
    buttons: [{ label: "Retour", onClick: back }],
  });
  let rows;
  try {
    rows = await api.leaderboard(10);
  } catch (err) {
    body.querySelector(".card-text").textContent = err.message;
    return;
  }
  const text = body.querySelector(".card-text");
  if (!text) return;
  if (!rows.length) {
    text.textContent = "Aucun score pour l'instant : soyez le premier !";
    return;
  }
  text.textContent = "Meilleur score de chaque médecin.";
  const user = api.user();
  const table = document.createElement("table");
  table.className = "board";
  table.innerHTML = "<thead><tr><th>#</th><th>Médecin</th><th>Points</th><th>Patients</th></tr></thead><tbody></tbody>";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (user && row.username.toLowerCase() === user.toLowerCase()) tr.className = "me";
    [row.rank, `Dr ${row.username}`, row.score, row.cases].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    });
    table.tBodies[0].append(tr);
  });
  text.after(table);
}

// ---------------------------------------------------------------------------
// Administration (visible seulement si /me renvoie is_admin = true ; chaque
// action est de toute façon revérifiée par le serveur)
// ---------------------------------------------------------------------------
function addAdminControls(body) {
  const row = body.querySelector(".card-buttons");
  if (!row || row.querySelector("[data-admin]")) return;
  const open = document.createElement("button");
  open.type = "button";
  open.className = "action secondary";
  open.dataset.admin = "";
  open.textContent = "Administration";
  open.addEventListener("click", () => openAdmin("players"));
  row.append(open);

  const label = document.createElement("label");
  label.className = "admin-toggle";
  label.innerHTML = '<input type="checkbox"> <span>Mode admin : réponses visibles, partie non comptée</span>';
  const box = label.querySelector("input");
  box.checked = player.wantsAdminMode;
  box.addEventListener("change", () => { player.wantsAdminMode = box.checked; });
  row.after(label);
}

const formatDate = (value) => new Date(typeof value === "number" ? value * 1000 : value)
  .toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
const percent = (value) => `${Math.round(value * 100)} %`;

/** Tableau HTML : columns = [{ label, value(row), className }] ; texte échappé. */
function buildTable(rows, columns) {
  const table = document.createElement("table");
  table.className = "admin-table";
  const head = document.createElement("tr");
  columns.forEach(({ label, className }) => {
    const th = document.createElement("th");
    th.textContent = label;
    if (className) th.className = className;
    head.append(th);
  });
  table.createTHead().append(head);
  const tbody = table.createTBody();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach(({ value, className }) => {
      const td = document.createElement("td");
      const content = value(row);
      if (content instanceof Node) td.append(content);
      else td.textContent = content ?? "—";
      if (className) td.className = className;
      tr.append(td);
    });
    tbody.append(tr);
  });
  return table;
}

/** Bouton à double clic de confirmation (pas de fenêtre « confirm » bloquante). */
function dangerButton(label, onConfirm) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "danger";
  button.textContent = label;
  let timer = null;
  button.addEventListener("click", async () => {
    if (!button.classList.contains("armed")) {
      button.classList.add("armed");
      button.textContent = "Confirmer ?";
      timer = setTimeout(() => {
        button.classList.remove("armed");
        button.textContent = label;
      }, 3000);
      return;
    }
    clearTimeout(timer);
    button.disabled = true;
    try {
      await onConfirm();
    } catch (err) {
      button.disabled = false;
      button.textContent = label;
      button.classList.remove("armed");
      adminMessage(err.message, true);
    }
  });
  return button;
}

function adminMessage(text, isError = false) {
  const message = document.querySelector("#admin-body .admin-message");
  if (!message) return;
  message.textContent = text;
  message.classList.toggle("error", isError);
}

const ADMIN_TABS = {
  async players(container) {
    const rows = await api.admin.players();
    const me = api.user()?.toLowerCase();
    container.append(buildTable(rows, [
      { label: "Joueur", value: (r) => (r.is_admin ? `${r.username} (admin)` : r.username) },
      { label: "Inscrit le", value: (r) => formatDate(r.created) },
      { label: "Parties", value: (r) => r.games_played, className: "num" },
      { label: "Record", value: (r) => r.best_score, className: "num" },
      { label: "Bons diagnostics", value: (r) => (r.total_cases ? percent(r.accuracy) : "—"), className: "num" },
      {
        label: "",
        value: (r) => (r.username.toLowerCase() === me ? "" : dangerButton("Supprimer", async () => {
          await api.admin.deletePlayer(r.username);
          renderAdminTab("players", `Compte « ${r.username} » supprimé, ses scores sont retirés du classement.`);
        })),
      },
    ]));
    if (!rows.length) adminMessage("Aucun joueur inscrit.");
  },

  async scores(container) {
    const rows = await api.admin.scores();
    const tools = document.createElement("div");
    tools.className = "admin-tools";
    tools.append(dangerButton("Remettre le classement à zéro", async () => {
      const { deleted } = await api.admin.resetScores();
      renderAdminTab("scores", `${deleted} score${deleted > 1 ? "s" : ""} supprimé${deleted > 1 ? "s" : ""}.`);
    }));
    container.append(tools);
    container.append(buildTable(rows, [
      { label: "Joueur", value: (r) => r.username },
      { label: "Points", value: (r) => r.score, className: "num" },
      { label: "Patients", value: (r) => r.cases, className: "num" },
      { label: "Bons", value: (r) => r.correct, className: "num" },
      { label: "Date", value: (r) => formatDate(r.finished_at) },
      {
        label: "",
        value: (r) => dangerButton("Supprimer", async () => {
          await api.admin.deleteScore(r.game_id);
          renderAdminTab("scores", "Score supprimé.");
        }),
      },
    ]));
    if (!rows.length) adminMessage("Le classement est vide.");
  },

  async stats(container) {
    const minShown = Number(container.dataset.minShown || 1);
    const stats = await api.admin.stats(minShown);
    const tiles = document.createElement("div");
    tiles.className = "admin-tiles";
    [
      ["Joueurs", stats.players],
      ["Parties", stats.games],
      ["Réponses", stats.answers],
      ["Bons diagnostics", stats.answers ? percent(stats.accuracy) : "—"],
    ].forEach(([label, value]) => {
      const tile = document.createElement("div");
      tile.innerHTML = "<strong></strong><span></span>";
      tile.querySelector("strong").textContent = value;
      tile.querySelector("span").textContent = label;
      tiles.append(tile);
    });

    const tools = document.createElement("div");
    tools.className = "admin-tools";
    const filter = document.createElement("label");
    filter.innerHTML = 'Maladies présentées au moins <select><option>1</option><option>3</option><option>5</option><option>10</option></select> fois';
    const select = filter.querySelector("select");
    select.value = String(minShown);
    select.addEventListener("change", () => {
      container.dataset.minShown = select.value;
      renderAdminTab("stats", "", select.value);
    });
    tools.append(filter, dangerButton("Remettre les statistiques à zéro", async () => {
      await api.admin.resetStats();
      renderAdminTab("stats", "Statistiques remises à zéro.");
    }));

    const note = document.createElement("p");
    note.className = "admin-note";
    note.textContent = "Maladies les plus ratées par les joueurs (parties en mode admin exclues).";
    container.append(tiles, tools, note, buildTable(stats.diseases, [
      { label: "Maladie", value: (r) => capitalize(r.disease) },
      { label: "Présentée", value: (r) => r.shown, className: "num" },
      { label: "Ratée", value: (r) => percent(r.error_rate), className: "num" },
      {
        label: "Souvent confondue avec",
        value: (r) => (r.top_confusion ? `${capitalize(r.top_confusion)} (${r.top_confusion_count}×)` : "—"),
      },
    ]));
    if (!stats.diseases.length) adminMessage("Pas encore de réponses enregistrées.");
  },
};

async function renderAdminTab(tab, message = "", minShown = null) {
  document.querySelectorAll("#admin-panel [data-tab]").forEach((button) =>
    button.setAttribute("aria-selected", String(button.dataset.tab === tab)));
  const body = $("admin-body");
  const previousMin = body.dataset.minShown;
  body.innerHTML = '<p class="admin-message" role="status">Chargement...</p>';
  body.dataset.minShown = minShown ?? (tab === "stats" ? previousMin || 1 : 1);
  try {
    await ADMIN_TABS[tab](body);
    const status = body.querySelector(".admin-message");
    if (message) adminMessage(message);
    else if (status.textContent === "Chargement...") adminMessage("");
  } catch (err) {
    if (err.status === 401) { closeAdmin(); return sessionExpired(); }
    adminMessage(err.status === 403 ? "Accès réservé aux administrateurs." : err.message, true);
  }
}

function openAdmin(tab) {
  game.mode = "admin";
  $("admin-panel").hidden = false;
  renderAdminTab(tab);
  $("admin-close").focus();
}

function closeAdmin() {
  $("admin-panel").hidden = true;
  showMenu();
}

document.querySelectorAll("#admin-panel [data-tab]").forEach((button) =>
  button.addEventListener("click", () => renderAdminTab(button.dataset.tab)));
$("admin-close").addEventListener("click", closeAdmin);
$("quit").addEventListener("click", quitGame);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("admin-panel").hidden) closeAdmin();
});

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

showMenu();
