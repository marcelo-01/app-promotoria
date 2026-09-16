import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'

export const useUserStore = defineStore('user', () => {
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
  const loading = ref(false)

  // Os papéis como conjunto: quem acumula promotor e vendedor tem os dois. O
  // fallback em `role` cobre a sessão aberta antes de `roles` existir — o
  // `user` do localStorage só ganha o campo no próximo /auth/me.
  const roles = computed(() =>
    user.value?.roles?.length ? user.value.roles : [user.value?.role].filter(Boolean)
  )
  const hasRole = (role) => roles.value.includes(role)

  const isAdmin = computed(() => user.value?.role === 'admin')
  const isSupervisor = computed(() => user.value?.role === 'supervisor')
  const isSeller = computed(() => hasRole('seller'))
  const isManagerOrAbove = computed(() => isAdmin.value || isSupervisor.value)

  const setUser = (userData) => {
    user.value = userData
    localStorage.setItem('user', JSON.stringify(userData))
  }

  const clearUser = () => {
    user.value = null
    localStorage.removeItem('user')
  }

  const fetchCurrentUser = async () => {
    loading.value = true
    try {
      const response = await apiClient.get('/auth/me')
      setUser(response.data)
      return response.data
    } finally {
      loading.value = false
    }
  }

  const updateProfile = async (data) => {
    loading.value = true
    try {
      const response = await apiClient.put('/auth/me', data)
      setUser(response.data)
      return response.data
    } finally {
      loading.value = false
    }
  }

  const uploadAvatar = async (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = async (e) => {
        const img = new Image()
        img.onload = async () => {
          const canvas = document.createElement('canvas')
          const MAX = 200
          const ratio = Math.min(MAX / img.width, MAX / img.height)
          canvas.width = img.width * ratio
          canvas.height = img.height * ratio
          canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
          const dataUrl = canvas.toDataURL('image/jpeg', 0.8)
          try {
            const response = await apiClient.put('/auth/avatar', { avatar_url: dataUrl })
            setUser(response.data)
            resolve(response.data)
          } catch (err) {
            reject(err)
          }
        }
        img.onerror = reject
        img.src = e.target.result
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  const changePassword = async (currentPassword, newPassword) => {
    const response = await apiClient.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    return response.data
  }

  const fetchPreferences = async () => {
    const response = await apiClient.get('/auth/preferences')
    return response.data
  }

  const savePreferences = async (prefs) => {
    await apiClient.put('/auth/preferences', {
      email_notifications: prefs.emailNotifications,
      dark_mode: prefs.darkMode,
      expiration_alerts: prefs.expirationAlerts,
    })
  }

  return {
    user,
    loading,
    roles,
    hasRole,
    isAdmin,
    isSupervisor,
    isSeller,
    isManagerOrAbove,
    setUser,
    clearUser,
    fetchCurrentUser,
    updateProfile,
    uploadAvatar,
    changePassword,
    fetchPreferences,
    savePreferences,
  }
})
