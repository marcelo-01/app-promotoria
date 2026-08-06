import apiClient from '@/api/client'

const normalizeParams = (params = {}) => {
  const clean = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') clean[key] = value
  })
  return clean
}

export const merchandisingApi = {
  // ── Promotor ──────────────────────────────────────────────────────────
  async myCustomers(params = {}) {
    const { data } = await apiClient.get('/merchandising/my-customers', {
      params: normalizeParams(params),
    })
    return data
  },

  async productsForCustomer(customerId, params = {}) {
    const { data } = await apiClient.get(
      `/merchandising/customers/${customerId}/products`,
      { params: normalizeParams(params) }
    )
    return data
  },

  async saveVisit(payload) {
    // Timeout maior: o promotor pode ter 40 itens e sinal ruim de supermercado.
    // O default do apiClient (10s) é curto demais para este envio.
    const { data } = await apiClient.post('/merchandising/visits', payload, {
      timeout: 30000,
    })
    return data
  },

  async submitVisit(visitId) {
    const { data } = await apiClient.post(`/merchandising/visits/${visitId}/submit`)
    return data
  },

  async myVisits(params = {}) {
    const { data } = await apiClient.get('/merchandising/visits/mine', {
      params: normalizeParams(params),
    })
    return data
  },

  // ── Administrador ─────────────────────────────────────────────────────
  async visits(params = {}) {
    const { data } = await apiClient.get('/merchandising/visits', {
      params: normalizeParams(params),
    })
    return data
  },

  async visit(visitId) {
    const { data } = await apiClient.get(`/merchandising/visits/${visitId}`)
    return data
  },

  async exportVisit(visitId) {
    const response = await apiClient.get(
      `/merchandising/visits/${visitId}/export.xlsx`,
      { responseType: 'blob' }
    )
    downloadBlob(response)
  },

  async exportConsolidated(params = {}) {
    const response = await apiClient.get('/merchandising/exports.xlsx', {
      params: normalizeParams(params),
      responseType: 'blob',
      timeout: 60000,
    })
    downloadBlob(response)
  },

  async getAssignments(promoterId) {
    const { data } = await apiClient.get(`/merchandising/assignments/${promoterId}`)
    return data
  },

  async setAssignments(promoterId, customerIds) {
    await apiClient.put(`/merchandising/assignments/${promoterId}`, {
      customer_ids: customerIds,
    })
  },

  async getCustomerMix(customerId) {
    const { data } = await apiClient.get(`/merchandising/customers/${customerId}/mix`)
    return data
  },

  async setCustomerMix(customerId, productIds) {
    await apiClient.put(`/merchandising/customers/${customerId}/mix`, {
      product_ids: productIds,
    })
  },

  async importFile(entity, file) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await apiClient.post(`/merchandising/imports/${entity}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    return data
  },

  async downloadTemplate(entity) {
    const response = await apiClient.get(
      `/merchandising/imports/${entity}/template.xlsx`,
      { responseType: 'blob' }
    )
    downloadBlob(response)
  },
}

/** Extrai o nome do arquivo do Content-Disposition e dispara o download. */
function downloadBlob(response) {
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match ? match[1] : 'planilha.xlsx'

  const url = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
