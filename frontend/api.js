/*
 * Couche d'accès à l'API MediGuess.
 * Tant que le backend (#12) n'existe pas, USE_MOCK = true : le jeu tourne
 * avec des cas fictifs au format exact du contrat (docs/api-contract.md).
 * Pour brancher la vraie API : USE_MOCK = false et renseigner API_BASE_URL.
 */
const USE_MOCK = false;
const API_BASE_URL = "http://127.0.0.1:8000"; // ex : "https://xxxx.execute-api.eu-west-3.amazonaws.com/prod"

// ---------------------------------------------------------------------------
// Vraie API
// ---------------------------------------------------------------------------
async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`Le serveur a répondu ${response.status} sur ${path}.`);
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Données fictives (même format que l'API)
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

let mockIndex = 0;

function mockGetCase() {
  const { case_id, symptoms, choices } = MOCK_CASES[mockIndex % MOCK_CASES.length];
  mockIndex += 1;
  return Promise.resolve({ case_id, symptoms, choices });
}

function mockPostAnswer(caseId, answer) {
  const item = MOCK_CASES.find((c) => c.case_id === caseId);
  const correct = answer === item.answer;
  return Promise.resolve({
    correct,
    correct_answer: item.answer,
    points: correct ? 10 : 0,
    feedback: correct
      ? `Bien vu : ${item.factors[0].symptom} était l'indice le plus parlant.`
      : `L'indice le plus parlant était : ${item.factors[0].symptom}.`,
    explanation: { disease: item.answer, factors: item.factors },
  });
}

// ---------------------------------------------------------------------------
// Fonctions utilisées par app.js
// ---------------------------------------------------------------------------
const api = {
  getCase: () => (USE_MOCK ? mockGetCase() : request("/case")),
  postAnswer: (caseId, answer) =>
    USE_MOCK
      ? mockPostAnswer(caseId, answer)
      : request("/answer", {
          method: "POST",
          body: JSON.stringify({ case_id: caseId, answer }),
        }),
};
