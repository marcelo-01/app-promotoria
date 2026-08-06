import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'

/**
 * Store de autenticação
 * Gerencia token JWT e estado de autenticação do usuário
 */
export const useAuthStore = defineStore('auth', () => {
  // Estado reativo
  const token = ref(localStorage.getItem('access_token') || null)
  const isAuthenticated = computed(() => !!token.value)

  /**
   * Define o token JWT e persiste no localStorage
   * @param {string} newToken - Token JWT recebido da API
   */
  const setToken = (newToken) => {
    token.value = newToken
    localStorage.setItem('access_token', newToken)
  }

  /**
   * Remove o token e limpa dados persistidos
   */
  const clearToken = () => {
    token.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  /**
   * Realiza login via API
   * @param {Object} credentials - Credenciais do usuário
   * @param {string} credentials.username - Nome de usuário ou email
   * @param {string} credentials.password - Senha do usuário
   * @returns {Promise<Object>} Dados do usuário e token
   * @throws {Error} Erro de autenticação
   */
  const login = async (credentials) => {
    try {
      // A API FastAPI espera JSON com email/password
      const response = await apiClient.post('/auth/login', {
        email: credentials.username, // API usa 'email' como campo
        password: credentials.password
      })

      // Salvar tokens
      setToken(response.data.access_token)
      if (response.data.refresh_token) {
        localStorage.setItem('refresh_token', response.data.refresh_token)
      }

      return response.data
    } catch (error) {
      // Limpar token em caso de erro
      clearToken()
      throw error
    }
  }

  /**
   * Realiza logout do sistema
   */
  const logout = () => {
    clearToken()
  }

  return {
    token,
    isAuthenticated,
    setToken,
    clearToken,
    login,
    logout,
  }
})
