import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { merchandisingApi } from '@/api/merchandising'

const DRAFTS_KEY = 'estoque_drafts'
const QUEUE_KEY = 'estoque_queue'

const load = (key) => JSON.parse(localStorage.getItem(key) || '{}')
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value))

/** Fallback para navegadores sem crypto.randomUUID (contexto não-seguro). */
const newUuid = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0
        const v = c === 'x' ? r : (r & 0x3) | 0x8
        return v.toString(16)
      })

export const useVisitaStore = defineStore('visita', () => {
  // { [customerId]: { client_uuid, visited_at, notes, items: { [productId]: {...} } } }
  const drafts = ref(load(DRAFTS_KEY))
  // Contagens fechadas que ainda não subiram
  const queue = ref(JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'))
  const sending = ref(false)

  const persist = () => {
    save(DRAFTS_KEY, drafts.value)
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.value))
  }

  const pendingCount = computed(() => queue.value.length)

  function getDraft(customerId) {
    if (!drafts.value[customerId]) {
      drafts.value[customerId] = {
        client_uuid: newUuid(),
        visited_at: new Date().toISOString(),
        notes: '',
        items: {},
      }
      persist()
    }
    return drafts.value[customerId]
  }

  function setItem(customerId, productId, { quantity, expires_at, notes }) {
    const draft = getDraft(customerId)
    if (quantity === null || quantity === undefined || quantity === '') {
      delete draft.items[productId]
    } else {
      draft.items[productId] = {
        product_id: productId,
        quantity: Number(quantity),
        expires_at: expires_at || null,
        notes: notes || null,
      }
    }
    persist()
  }

  function itemsCount(customerId) {
    return Object.keys(drafts.value[customerId]?.items || {}).length
  }

  function clearDraft(customerId) {
    delete drafts.value[customerId]
    persist()
  }

  /** Fecha a contagem: tenta enviar; se falhar, enfileira para reenvio. */
  async function submit(customerId) {
    const draft = getDraft(customerId)
    const payload = {
      customer_id: customerId,
      client_uuid: draft.client_uuid,
      visited_at: draft.visited_at,
      notes: draft.notes || null,
      items: Object.values(draft.items),
      submit: true,
    }

    try {
      await merchandisingApi.saveVisit(payload)
      clearDraft(customerId)
      return { sent: true }
    } catch (error) {
      queue.value.push(payload)
      clearDraft(customerId)
      persist()
      return { sent: false, error }
    }
  }

  /** Reenvia tudo que está na fila. Seguro rodar quantas vezes quiser:
   *  o backend deduplica pelo client_uuid. */
  async function flushQueue() {
    if (sending.value || queue.value.length === 0) return { sent: 0, failed: 0 }
    sending.value = true

    let sent = 0
    const remaining = []

    for (const payload of queue.value) {
      try {
        await merchandisingApi.saveVisit(payload)
        sent += 1
      } catch (error) {
        // 4xx é erro de dados (cliente removido, contagem já exportada): reenviar
        // não resolve e a fila entupiria para sempre. Só 5xx/rede voltam à fila.
        const code = error.response?.status
        if (code && code >= 400 && code < 500) {
          console.error('Contagem descartada pelo servidor:', code, payload)
          continue
        }
        remaining.push(payload)
      }
    }

    queue.value = remaining
    persist()
    sending.value = false
    return { sent, failed: remaining.length }
  }

  return {
    drafts, queue, sending, pendingCount,
    getDraft, setItem, itemsCount, clearDraft, submit, flushQueue,
  }
})
