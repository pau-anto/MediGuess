/*
 * Couche d'accès à l'API MediGuess (contrat : docs/api-contract.md).
 * USE_MOCK = true : le jeu tourne sans serveur, avec des cas fictifs.
 * Sur Azure, Terraform remplace API_BASE_URL et force USE_MOCK = false.
 */
const USE_MOCK = false;
const API_BASE_URL = "http://127.0.0.1:8080"; // Azure : injectée par Terraform

// ---------------------------------------------------------------------------
// Session du joueur (jeton JWT gardé dans le navigateur)
// ---------------------------------------------------------------------------
const SESSION_KEY = "mediguess.session";

const session = {
  get() {
    try {
      return JSON.parse(localStorage.getItem(SESSION_KEY));
    } catch {
      return null;
    }
  },
  set(value) {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(value));
    } catch {
      // stockage indisponible (navigation privée) : la session dure le temps de la page
    }
    session.memory = value;
  },
  clear() {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      // rien à faire
    }
    session.memory = null;
  },
  current() {
    return session.get() || session.memory || null;
  },
  memory: null,
};

const GAME_KEY = "mediguess.game";
const store = {
  get: (key) => { try { return localStorage.getItem(key); } catch { return null; } },
  set: (key, value) => { try { localStorage.setItem(key, value); } catch { /* indisponible */ } },
  remove: (key) => { try { localStorage.removeItem(key); } catch { /* indisponible */ } },
};

/** Erreur HTTP avec le code et le message renvoyés par l'API. */
class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Vraie API
// ---------------------------------------------------------------------------
async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const current = session.current();
  if (current) headers.Authorization = `Bearer ${current.token}`;

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "Serveur injoignable. Vérifiez votre connexion.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI : detail = texte, ou liste d'erreurs de validation (422)
    const detail = Array.isArray(data.detail) ? null : data.detail;
    throw new ApiError(response.status, detail || `Erreur ${response.status}.`);
  }
  return data;
}

const post = (path, body) =>
  request(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const del = (path) => request(path, { method: "DELETE" });

async function authenticate(path, username, password) {
  const data = await post(path, { username, password });
  session.set({ token: data.token, username: data.username });
  return data;
}

// ---------------------------------------------------------------------------
// Données fictives (même format que l'API), pour jouer sans serveur
// ---------------------------------------------------------------------------
const MOCK_CASES = [
  {
    case_id: "mock-1",
    symptoms: ["anxiety and nervousness", "depression", "insomnia",
      "hostile behavior", "drug abuse", "disturbance of memory"],
    choices: ["acute stress reaction", "depression", "drug reaction", "anxiety"],
    answer: "depression",
    factors: [
      { symptom: "disturbance of memory", present: true, contribution: 0.015, direction: "pour" },
      { symptom: "insomnia", present: true, contribution: 0.009, direction: "pour" },
      { symptom: "drug abuse", present: true, contribution: 0.005, direction: "pour" },
    ],
  },
  {
    case_id: "mock-2",
    symptoms: ["cough", "fever", "shortness of breath", "sharp chest pain", "chills"],
    choices: ["pneumonia", "acute bronchitis", "asthma", "common cold"],
    answer: "pneumonia",
    factors: [
      { symptom: "shortness of breath", present: true, contribution: 0.021, direction: "pour" },
      { symptom: "sharp chest pain", present: true, contribution: 0.012, direction: "pour" },
      { symptom: "nasal congestion", present: false, contribution: 0.006, direction: "pour" },
    ],
  },
  {
    case_id: "mock-3",
    symptoms: ["headache", "nausea", "vomiting", "dizziness", "diminished vision"],
    choices: ["concussion", "migraine", "vestibular disorder", "gastritis"],
    answer: "migraine",
    factors: [
      { symptom: "headache", present: true, contribution: 0.024, direction: "pour" },
      { symptom: "diminished vision", present: true, contribution: 0.011, direction: "pour" },
      { symptom: "head injury", present: false, contribution: 0.008, direction: "pour" },
    ],
  },
];

const mock = {
  index: 0,
  game: null,
  startGame() {
    mock.game = { game_id: "mock-game", username: null, score: 0, lives: 3, cases: 0, correct: 0, game_over: false };
    return Promise.resolve({ ...mock.game });
  },
  getCase() {
    const { case_id, symptoms, choices } = MOCK_CASES[mock.index % MOCK_CASES.length];
    mock.index += 1;
    return Promise.resolve({ case_id, symptoms, choices });
  },
  postAnswer(caseId, answer) {
    const item = MOCK_CASES.find((c) => c.case_id === caseId);
    const correct = answer === item.answer;
    const game = mock.game;
    game.cases += 1;
    if (correct) { game.score += 10; game.correct += 1; } else { game.lives -= 1; }
    game.game_over = game.lives <= 0;
    return Promise.resolve({
      correct,
      correct_answer: item.answer,
      points: correct ? 10 : 0,
      feedback: correct
        ? `Bien vu : ${item.factors[0].symptom} était l'indice le plus parlant.`
        : `L'indice le plus parlant était : ${item.factors[0].symptom}.`,
      explanation: { disease: item.answer, factors: item.factors },
      game: { ...game },
    });
  },
  unavailable: () => Promise.reject(new ApiError(0, "Comptes indisponibles en mode démo (USE_MOCK).")),
};

// ---------------------------------------------------------------------------
// Fonctions utilisées par app.js
// ---------------------------------------------------------------------------
const api = {
  user: () => session.current()?.username || null,
  logout: () => { session.clear(); store.remove(GAME_KEY); },

  register: (username, password) =>
    USE_MOCK ? mock.unavailable() : authenticate("/auth/register", username, password),
  login: (username, password) =>
    USE_MOCK ? mock.unavailable() : authenticate("/auth/login", username, password),
  me: () => (USE_MOCK ? mock.unavailable() : request("/me")),
  myGames: () => (USE_MOCK ? Promise.resolve([]) : request("/me/games")),
  leaderboard: (limit = 10) =>
    USE_MOCK ? Promise.resolve([]) : request(`/leaderboard?limit=${limit}`),

  // Partie sauvegardée (le serveur garde tout ; on retient juste son id
  // pour qu'un invité puisse la reprendre dans ce navigateur)
  rememberGame: (gameId) => store.set(GAME_KEY, gameId),
  savedGameId: () => store.get(GAME_KEY),
  forgetGame: () => store.remove(GAME_KEY),
  currentGame: () => (USE_MOCK ? Promise.resolve(null) : request("/games/current")),
  getGame: (gameId) => request(`/games/${encodeURIComponent(gameId)}`),

  startGame: (adminMode = false) =>
    USE_MOCK ? mock.startGame() : post("/games", adminMode ? { admin_mode: true } : undefined),
  getCase: (gameId) =>
    USE_MOCK ? mock.getCase() : request(`/case?game_id=${encodeURIComponent(gameId)}`),
  postAnswer: (caseId, answer) =>
    USE_MOCK ? mock.postAnswer(caseId, answer) : post("/answer", { case_id: caseId, answer }),

  // Administration (compte avec is_admin = true)
  admin: {
    players: () => request("/admin/players"),
    deletePlayer: (username) => del(`/admin/players/${encodeURIComponent(username)}`),
    scores: () => request("/admin/scores"),
    deleteScore: (gameId) => del(`/admin/scores/${encodeURIComponent(gameId)}`),
    resetScores: () => post("/admin/scores/reset"),
    stats: (minShown = 1) => request(`/admin/stats?min_shown=${minShown}`),
    resetStats: () => post("/admin/stats/reset"),
  },
};
