import apiClient from '@/api/client'

const normalizeParams = (params = {}) => {
  const clean = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') clean[key] = value
  })
  return clean
}

export const usersApi = {
  async list(params = {}) {
    const { data } = await apiClient.get('/users', {
      params: normalizeParams(params),
    })
    return data
  },

  async create(payload) {
    const { data } = await apiClient.post('/users', payload)
    return data
  },

  /** O conjunto completo de papéis de campo: ['promoter'], ['seller'] ou os dois. */
  async setRoles(userId, roles) {
    await apiClient.put(`/users/${userId}/roles`, { roles })
  },

  /** Redefinição de senha pelo administrador — não há 'esqueci minha senha' no MVP. */
  async setPassword(userId, newPassword) {
    await apiClient.put(`/users/${userId}/password`, { new_password: newPassword })
  },
}
