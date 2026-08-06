import apiClient from '@/api/client'

const normalizeParams = (params = {}) => {
  const clean = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') clean[key] = value
  })
  return clean
}

export const productsApi = {
  /** Retorna apenas o array de produtos (o backend devolve { items, total }). */
  async list(params = {}) {
    const { data } = await apiClient.get('/products', {
      params: normalizeParams(params),
    })
    return data.items
  },

  async listPaged(params = {}) {
    const { data } = await apiClient.get('/products', {
      params: normalizeParams(params),
    })
    return data
  },

  async get(productId) {
    const { data } = await apiClient.get(`/products/${productId}`)
    return data
  },

  async create(payload) {
    const { data } = await apiClient.post('/products', payload)
    return data
  },

  async update(productId, payload) {
    const { data } = await apiClient.put(`/products/${productId}`, payload)
    return data
  },
}
