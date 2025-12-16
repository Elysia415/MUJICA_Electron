import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export const api = {
    health: () => axios.get(`${API_BASE}/`),
    listJobs: () => axios.get(`${API_BASE}/jobs`),
    getJob: (jobId) => axios.get(`${API_BASE}/jobs/${jobId}`),
    cancelJob: (jobId) => axios.delete(`${API_BASE}/jobs/${jobId}`),

    startPlan: (query, options = {}) => axios.post(`${API_BASE}/plan`, { query, ...options }),
    startResearch: (plan, options = {}) => axios.post(`${API_BASE}/research`, { plan, ...options }),
    startIngest: (venueId, options = {}) => axios.post(`${API_BASE}/ingest`, { venue_id: venueId, ...options }),
};
