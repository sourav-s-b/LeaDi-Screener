import axios from 'axios';

export const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  timeout: 60000,
});

// Request interceptor — attach auth token if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor — normalise errors
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      'Unknown error';
    return Promise.reject(new Error(message));
  }
);

// ── Typed endpoint helpers ────────────────────────────────────────────────────

export const apiEndpoints = {
  // Health
  health: () => api.get('/health'),

  // Dysarthria
  dysarthria: {
    predict:      (formData: FormData) => api.post('/dysarthria/predict', formData),
    predict_file: (formData: FormData) => api.post('/dysarthria/predict_file', formData),
    evaluate: (formData: FormData) => api.post('/dysarthria/evaluate', formData),
  },

  // Dyslexia
  dyslexia: {
    predict:  (formData: FormData) => api.post('/dyslexia/predict', formData),
    evaluate: (formData: FormData) => api.post('/dyslexia/evaluate', formData),
  },

  // Handwriting
  handwriting: {
    score:    (formData: FormData) => api.post('/handwriting/score', formData),
    evaluate: (formData: FormData) => api.post('/handwriting/evaluate', formData),
    history:  ()                   => api.get('/handwriting/history'),
  },

  // Sessions (recent results)
  sessions: {
    list:   () => api.get('/sessions'),
    get:    (id: string) => api.get(`/sessions/${id}`),
    delete: (id: string) => api.delete(`/sessions/${id}`),
  },
};
