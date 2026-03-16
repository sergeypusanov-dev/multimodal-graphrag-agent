const API = '/api';

function getToken() {
    return localStorage.getItem('api_token') || '';
}

function setToken(token) {
    localStorage.setItem('api_token', token);
}

function headers(extra = {}) {
    const h = { ...extra };
    const t = getToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
}

async function request(path, opts = {}) {
    const res = await fetch(`${API}${path}`, {
        ...opts,
        headers: { ...headers(), ...(opts.headers || {}) }
    });
    if (res.status === 401 || res.status === 403) {
        throw new Error('AUTH_FAILED');
    }
    return res;
}

export async function chat(message, sessionId) {
    const res = await request('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId })
    });
    return res.json();
}

export async function chatMultimodal(message, files, sessionId) {
    const fd = new FormData();
    fd.append('message', message);
    if (sessionId) fd.append('session_id', sessionId);
    for (const f of files) fd.append('files', f);
    const res = await fetch(`${API}/chat/multimodal`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
        body: fd
    });
    if (res.status === 401 || res.status === 403) throw new Error('AUTH_FAILED');
    return res.json();
}

export async function getHealth() {
    return (await request('/health')).json();
}

export async function getKbStats() {
    return (await request('/kb/stats')).json();
}

export async function getKbFiles(status, limit = 100) {
    const params = new URLSearchParams({ limit });
    if (status) params.set('status', status);
    return (await request(`/kb/files?${params}`)).json();
}

export async function uploadFiles(files) {
    const fd = new FormData();
    for (const f of files) fd.append('files', f);
    const res = await fetch(`${API}/kb/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
        body: fd
    });
    return res.json();
}

export async function triggerSync() {
    return (await request('/kb/sync', { method: 'POST' })).json();
}

export async function getEntities(search, limit = 50) {
    const params = new URLSearchParams({ limit });
    if (search) params.set('search', search);
    return (await request(`/kb/entities?${params}`)).json();
}

export async function getAgentCard() {
    return (await request('/.well-known/agent.json')).json();
}

export async function getMetrics() {
    const res = await request('/metrics');
    return res.text();
}

export { getToken, setToken };
