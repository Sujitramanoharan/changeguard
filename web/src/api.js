const BASE = "/api";

const TOKEN_KEY = "changeguard_access_token";
const USER_KEY = "changeguard_user";

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function getHeaders(includeJson = false) {
  const headers = {};

  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }

  const token = getToken();

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return headers;
}

function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

async function handleResponse(res) {
  if (res.status === 401) {
    clearSession();
    window.location.href = "/login";
    throw new Error("Authentication required");
  }

  if (res.status === 403) {
    throw new Error("Administrator access required");
  }

  if (!res.ok) {
    let message = `Request failed: ${res.status}`;

    try {
      const data = await res.json();

      if (data?.detail) {
        message = data.detail;
      } else if (data?.message) {
        message = data.message;
      }
    } catch {
      // Keep the default error message.
    }

    throw new Error(message);
  }

  return res.json();
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: getHeaders(true),
    body: JSON.stringify(body),
  });

  return handleResponse(res);
}

async function postFile(path, file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(BASE + path, {
    method: "POST",
    headers: getHeaders(false),
    body: formData,
  });

  return handleResponse(res);
}

async function get(path) {
  const res = await fetch(BASE + path, {
    method: "GET",
    headers: getHeaders(),
  });

  return handleResponse(res);
}

async function login(username, password) {
  const res = await fetch(BASE + "/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username,
      password,
    }),
  });

  if (!res.ok) {
    let message = "Invalid username or password";

    if (res.status === 429) {
      message = "Too many login attempts. Please wait a minute and try again.";
    }

    try {
      const data = await res.json();

      if (data?.detail) {
        message = data.detail;
      } else if (data?.error && res.status === 429) {
        message = "Too many login attempts. Please wait a minute and try again.";
      }
    } catch {
      // Keep the default login error.
    }

    throw new Error(message);
  }

  const data = await res.json();

  sessionStorage.setItem(TOKEN_KEY, data.access_token);

  sessionStorage.setItem(
    USER_KEY,
    JSON.stringify(data.user)
  );

  return data;
}

function logout() {
  clearSession();
  window.location.href = "/login";
}

function getStoredUser() {
  const value = sessionStorage.getItem(USER_KEY);

  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value);
  } catch {
    clearSession();
    return null;
  }
}

function isAuthenticated() {
  return Boolean(getToken());
}

export const api = {
  login,
  logout,
  getStoredUser,
  isAuthenticated,
  me: () => get("/auth/me"),
  assess: (change) => post("/assess", change),
  assessAutonomous: (change) => post("/assess-autonomous", change),
  verifyRollbackDocument: (file) =>
    postFile("/documents/verify-rollback", file),
  analyzeRepoChange: (url) => post("/analyze-repo-change", { url }),
  history: () => get("/history"),
  getAssessment: (id) => get(`/assessments/${id}`),
  stats: () => get("/stats"),
};
