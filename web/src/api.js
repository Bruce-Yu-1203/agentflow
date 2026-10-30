export class ApiError extends Error {
  constructor(message, status = 0, code = null, retryable = false) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.retryable = retryable
  }
}

function messageFromDetail(detail) {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || item?.message).filter(Boolean).join('; ') || 'The request is invalid.'
  }
  return 'The request could not be completed.'
}

export function createApiClient({ baseUrl, token = '', fetchImpl = fetch }) {
  const root = baseUrl.trim().replace(/\/+$/, '')

  async function request(path, { method = 'GET', body, signal, upload = false } = {}) {
    const headers = { Accept: 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    if (body !== undefined && !upload) headers['Content-Type'] = 'application/json'
    let response
    try {
      response = await fetchImpl(`${root}${path}`, {
        method,
        headers,
        body: upload ? body : body === undefined ? undefined : JSON.stringify(body),
        signal,
      })
    } catch (error) {
      if (error?.name === 'AbortError') throw error
      throw new ApiError('Cannot reach the API. Check the connection and retry.', 0, 'network_error', true)
    }
    const raw = await response.text()
    let data = null
    try { data = raw ? JSON.parse(raw) : null } catch { data = null }
    if (!response.ok) {
      const message = data?.response || messageFromDetail(data?.detail) || `HTTP ${response.status}`
      throw new ApiError(message, response.status, data?.error_code || null, Boolean(data?.retryable) || [0, 503, 504].includes(response.status))
    }
    return data ?? raw
  }

  return {
    baseUrl: root,
    request,
    health: (signal) => request('/health', { signal }),
    chat: (body, signal) => request('/chat', { method: 'POST', body, signal }),
    search: (query, topK = 5, signal) => request(`/search?query=${encodeURIComponent(query)}&top_k=${topK}`, { method: 'POST', signal }),
    knowledgeStats: (signal) => request('/knowledge/stats', { signal }),
    addKnowledge: (documents, signal) => request('/knowledge/add', { method: 'POST', body: { documents }, signal }),
    uploadKnowledge: (file, signal) => {
      const form = new FormData()
      form.append('file', file)
      return request('/knowledge/upload', { method: 'POST', body: form, upload: true, signal })
    },
    skills: (signal) => request('/skills', { signal }),
    reloadSkills: (signal) => request('/skills/reload', { method: 'POST', signal }),
    trace: (requestId, signal) => request(`/trace/tool/${encodeURIComponent(requestId)}`, { signal }),
    recentTraces: (limit = 20, signal) => request(`/trace/tools?limit=${limit}`, { signal }),
    monitor: (signal) => request('/monitor', { signal }),
    embedding: (signal) => request('/integrations/embedding', { signal }),
    mcp: (signal) => request('/integrations/mcp', { signal }),
    runEvaluation: (body, signal) => request('/eval/run', { method: 'POST', body, signal }),
    evaluationJob: (jobId, signal) => request(`/eval/jobs/${encodeURIComponent(jobId)}`, { signal }),
  }
}
