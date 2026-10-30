const BASE = '/api'

async function request(path, { method = 'GET', body, params } = {}) {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, value)
      }
    })
  }
  const response = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  let payload = null
  try {
    payload = await response.json()
  } catch {
    throw new Error(`请求失败（HTTP ${response.status}）`)
  }
  if (!response.ok || payload.code !== 0) {
    const detail = payload?.data?.errors
      ?.map((item) => `${item.field}: ${item.message}`)
      .join('；')
    throw new Error(payload?.message || detail || `请求失败（HTTP ${response.status}）`)
  }
  return payload.data
}

export const api = {
  health: () => request('/health'),
  meta: () => request('/meta'),

  students: () => request('/students'),
  createStudent: (body) => request('/students', { method: 'POST', body }),
  dashboard: (id) => request(`/dashboard/${id}`),

  profile: (id) => request(`/profile/${id}`),
  dialogues: (id, limit = 50) => request(`/profile/${id}/dialogues`, { params: { limit } }),
  chat: (id, message) => request(`/profile/${id}/chat`, { method: 'POST', body: { message } }),

  generateResources: (body) => request('/resources/generate', { method: 'POST', body }),
  resources: (studentId, type) =>
    request('/resources', { params: { student_id: studentId, type, limit: 200 } }),
  resource: (id) => request(`/resources/${id}`),
  markView: (id, duration = 30) =>
    request(`/resources/${id}/view`, { method: 'POST', params: { duration_sec: duration } }),

  uploadStatus: (fileId, totalChunks) =>
    request(`/upload/status/${encodeURIComponent(fileId)}`, {
      params: { total_chunks: totalChunks },
    }),
  completeUpload: async (fileId, totalChunks, filename) => {
    const form = new FormData()
    form.append('file_id', fileId)
    form.append('total_chunks', String(totalChunks))
    form.append('filename', filename)
    const response = await fetch('/api/upload/complete', { method: 'POST', body: form })
    const payload = await response.json()
    if (!response.ok || payload.code !== 0) {
      throw new Error(payload.message || `合并失败（HTTP ${response.status}）`)
    }
    return payload.data
  },
  uploadDownloadUrl: (filename) => `/api/upload/download/${encodeURIComponent(filename)}`,

  generatePath: (studentId) =>
    request('/paths/generate', { method: 'POST', body: { student_id: studentId } }),
  path: (studentId) => request(`/paths/${studentId}`),
  updateStep: (pathId, stepNo, completed) =>
    request(`/paths/${pathId}/steps/${stepNo}`, {
      method: 'PATCH',
      body: { completed },
    }),

  askTutor: (body) => request('/tutor/ask', { method: 'POST', body }),
  tutorHistory: (studentId, limit = 30) =>
    request(`/tutor/history/${studentId}`, { params: { limit } }),
  addRecord: (body) => request('/assessment/records', { method: 'POST', body }),
  records: (studentId) =>
    request(`/assessment/records/${studentId}`, { params: { limit: 100 } }),
  evaluate: (studentId) =>
    request('/assessment/evaluate', { method: 'POST', body: { student_id: studentId } }),
  latestReport: (studentId) => request(`/assessment/latest/${studentId}`),
  reports: (studentId) => request(`/assessment/reports/${studentId}`),

  agentRuns: (studentId, limit = 60) =>
    request(`/agent-runs/${studentId}`, { params: { limit } }),
}
