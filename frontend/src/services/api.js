import axios from 'axios';

const API_URL = '/api';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para adicionar token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor para tratar erros
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth
export const authService = {
  login: async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    return response.data;
  },

  me: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },
};

// Clients
export const clientsService = {
  list: async (skip = 0, limit = 100) => {
    const response = await api.get(`/clients?skip=${skip}&limit=${limit}`);
    return response.data;
  },

  get: async (id) => {
    const response = await api.get(`/clients/${id}`);
    return response.data;
  },

  create: async (data) => {
    const response = await api.post('/clients', data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/clients/${id}`, data);
    return response.data;
  },

  delete: async (id, permanent = false) => {
    const response = await api.delete(`/clients/${id}?permanent=${permanent}`);
    return response.data;
  },
};

// Licenses
export const licensesService = {
  list: async (skip = 0, limit = 100) => {
    const response = await api.get(`/licenses?skip=${skip}&limit=${limit}`);
    return response.data;
  },

  get: async (id) => {
    const response = await api.get(`/licenses/${id}`);
    return response.data;
  },

  create: async (data) => {
    const response = await api.post('/licenses', data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/licenses/${id}`, data);
    return response.data;
  },

  revoke: async (id) => {
    const response = await api.post(`/licenses/${id}/revoke`);
    return response.data;
  },

  suspend: async (id) => {
    const response = await api.post(`/licenses/${id}/suspend`);
    return response.data;
  },

  reactivate: async (id) => {
    const response = await api.post(`/licenses/${id}/reactivate`);
    return response.data;
  },

  validations: async (id, skip = 0, limit = 50) => {
    const response = await api.get(`/licenses/${id}/validations?skip=${skip}&limit=${limit}`);
    return response.data;
  },
};

// Stats
export const statsService = {
  dashboard: async () => {
    const response = await api.get('/stats/dashboard');
    return response.data;
  },
};

export default api;
