import axios from 'axios'

// Em dev com HTTPS (acesso local ou de outros dispositivos na rede Wi-Fi),
// roteia chamadas via proxy do Vite para evitar mixed content.
// Em dev com HTTP (raro), chama a API diretamente.
// Em produção, usa a variável de ambiente VITE_API_URL.
const devHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
const apiBaseURL = import.meta.env.PROD
  ? (import.meta.env.VITE_API_URL || 'http://localhost:8002')
  : isHttps
    ? '/api-proxy'
    : `http://${devHost}:8002`

export { apiBaseURL }

/**
 * Caminho de arquivo servido pela API (`/uploads/...`) → URL absoluta.
 * A foto do produto é gravada no backend, que em dev roda em outra porta e sob
 * HTTPS passa pelo proxy do Vite — por isso nunca se usa o caminho cru no `src`.
 */
export function mediaUrl(path) {
  if (!path) return null
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  return `${apiBaseURL}${path}`
}

const apiClient = axios.create({
  baseURL: apiBaseURL,
  timeout: 10000,
})

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Controle para evitar loop infinito de refresh
let _refreshing = false
let _refreshQueue = []

function _processQueue(error, token = null) {
  _refreshQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)))
  _refreshQueue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error)
    }

    // Não tentar refresh na rota de login/refresh
    if (
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/refresh')
    ) {
      _doLogout()
      return Promise.reject(error)
    }

    if (_refreshing) {
      return new Promise((resolve, reject) => {
        _refreshQueue.push({ resolve, reject })
      })
        .then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return apiClient(originalRequest)
        })
        .catch((err) => Promise.reject(err))
    }

    originalRequest._retry = true
    _refreshing = true

    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      _refreshing = false
      _doLogout()
      return Promise.reject(error)
    }

    try {
      const { data } = await axios.post(`${apiBaseURL}/auth/refresh`, {
        refresh_token: refreshToken,
      })
      const newToken = data.access_token
      localStorage.setItem('access_token', newToken)
      apiClient.defaults.headers.common.Authorization = `Bearer ${newToken}`
      _processQueue(null, newToken)
      originalRequest.headers.Authorization = `Bearer ${newToken}`
      return apiClient(originalRequest)
    } catch (refreshError) {
      _processQueue(refreshError, null)
      _doLogout()
      return Promise.reject(refreshError)
    } finally {
      _refreshing = false
    }
  }
)

function _doLogout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  window.location.href = import.meta.env.BASE_URL + 'login'
}

export default apiClient
