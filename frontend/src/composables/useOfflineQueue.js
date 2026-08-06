import { onMounted, onUnmounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useVisitaStore } from '@/stores/visita'

export function useOfflineQueue() {
  const $q = useQuasar()
  const visita = useVisitaStore()
  const online = ref(navigator.onLine)

  async function tryFlush() {
    if (!navigator.onLine) return
    const { sent } = await visita.flushQueue()
    if (sent > 0) {
      $q.notify({
        type: 'positive',
        message: `${sent} contagem(ns) enviada(s) com sucesso.`,
        position: 'top',
      })
    }
  }

  const handleOnline = () => {
    online.value = true
    tryFlush()
  }
  const handleOffline = () => {
    online.value = false
  }
  const handleVisibility = () => {
    if (document.visibilityState === 'visible') tryFlush()
  }

  onMounted(() => {
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    document.addEventListener('visibilitychange', handleVisibility)
    tryFlush()
  })

  onUnmounted(() => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    document.removeEventListener('visibilitychange', handleVisibility)
  })

  return { online, tryFlush }
}
