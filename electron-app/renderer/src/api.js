import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8000/api';

export const api = {
    health: () => axios.get('http://127.0.0.1:8000/'),
    listJobs: () => axios.get(`${API_BASE}/jobs`),
    getJob: (jobId) => axios.get(`${API_BASE}/jobs/${jobId}`),
    cancelJob: (jobId) => axios.delete(`${API_BASE}/jobs/${jobId}`),

    startPlan: (query, options = {}) => axios.post(`${API_BASE}/plan`, { query, ...options }),
    startResearch: (plan, options = {}) => axios.post(`${API_BASE}/research`, { plan, ...options }),
    startIngest: (venueId, options = {}) => axios.post(`${API_BASE}/ingest`, { venue_id: venueId, ...options }),

    // Knowledge Base
    listPapers: (limit = 100, search = null) => axios.get(`${API_BASE}/kb/papers`, { params: { limit, search } }),
    getPaperDetail: (paperId) => axios.get(`${API_BASE}/kb/paper/${paperId}`),
    deletePaper: (paperId) => axios.post(`${API_BASE}/kb/delete`, null, { params: { paper_id: paperId } }),
    getKBStats: () => axios.get(`${API_BASE}/kb/stats`),
    refreshKB: () => axios.post(`${API_BASE}/kb/refresh`),

    // Job Control
    cancelJob: (jobId) => axios.post(`${API_BASE}/job/${jobId}/cancel`),

    // Config
    getConfig: () => axios.get(`${API_BASE}/config`),
    updateConfig: (config) => axios.post(`${API_BASE}/config`, config),

    // History
    listHistory: () => axios.get(`${API_BASE}/history`),
    getHistory: (cid) => axios.get(`${API_BASE}/history/${cid}`),
    deleteHistory: (cid) => axios.delete(`${API_BASE}/history/${cid}`),
    renameHistory: (cid, title) => axios.post(`${API_BASE}/history/${cid}/rename`, { title }),
};
