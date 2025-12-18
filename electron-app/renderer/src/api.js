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
    semanticSearchPapers: (query, limit = 20) => axios.get(`${API_BASE}/kb/semantic-search`, { params: { query, limit } }),
    getPaperDetail: (paperId) => axios.get(`${API_BASE}/kb/paper/${paperId}`),
    deletePaper: (paperId) => axios.post(`${API_BASE}/kb/delete`, null, { params: { paper_id: paperId } }),
    getKBStats: () => axios.get(`${API_BASE}/kb/stats`),
    refreshKB: () => axios.post(`${API_BASE}/kb/refresh`),
    exportKB: (onProgress) => axios.get(`${API_BASE}/kb/export`, {
        responseType: 'blob',
        onDownloadProgress: onProgress
    }),
    exportKBLocal: async (onProgress) => {
        const response = await fetch(`${API_BASE}/kb/export_local`);
        if (!response.ok) throw new Error("Export failed to start");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    onProgress(data);
                } catch (e) {
                    // Ignore partial
                }
            }
        }
    },
    openFolder: (path) => axios.post(`${API_BASE}/system/open_folder`, { path }),
    importKB: (formData, onProgress) => axios.post(`${API_BASE}/kb/import`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: onProgress
    }),

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

    // PDF Viewer
    openPdf: (pdfPath) => axios.post(`${API_BASE}/open-pdf`, { pdf_path: pdfPath }),
};
