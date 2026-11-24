// Shared contract. Do not define another fetch wrapper in individual features.
const ROOT = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(ROOT + path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers }
    });
  } catch (error) {
    // Feature cleanup/timeout is different from a failed connection.
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot connect to backend. Start FastAPI on port 8000.');
  }
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return response.json();
}

export const api = {
  health: () => request('/api/health'),
  ask: (question, { signal } = {}) => request('/api/questions', { method: 'POST', body: JSON.stringify({ question }), signal }),
  questions: (status, { signal } = {}) => request('/api/questions' + (status ? `?status=${encodeURIComponent(status)}` : ''), { signal }),
  question: (id) => request(`/api/questions/${id}`),
  review: (id, answer, reviewer, { signal } = {}) => request(`/api/questions/${id}/review`, {
    method: 'POST', body: JSON.stringify({ answer, reviewer }), signal
  }),
  knowledge: ({ signal } = {}) => request('/api/knowledge', { signal })
};
