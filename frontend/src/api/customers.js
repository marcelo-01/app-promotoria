import apiClient from '@/api/client'

const normalizeParams = (params = {}) => {
  const clean = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') clean[key] = value
  })
  return clean
}

export const customersApi = {
  /** Retorna apenas o array de clientes (o backend devolve { items, total }). */
  async list(params = {}) {
    const { data } = await apiClient.get('/customers', {
      params: normalizeParams(params),
    })
    return data.items
  },

  async listPaged(params = {}) {
    const { data } = await apiClient.get('/customers', {
      params: normalizeParams(params),
    })
    return data
  },

  async get(customerId) {
    const { data } = await apiClient.get(`/customers/${customerId}`)
    return data
  },

  async create(payload) {
    const { data } = await apiClient.post('/customers', payload)
    return data
  },

  async update(customerId, payload) {
    const { data } = await apiClient.put(`/customers/${customerId}`, payload)
    return data
  },
}
