import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { merchandisingApi } from '@/api/merchandising'

const DRAFTS_KEY = 'estoque_drafts'
const QUEUE_KEY = 'estoque_queue'

const load = (key) => JSON.parse(localStorage.getItem(key) || '{}')
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value))

/** Gôndola e estoque do mesmo cliente são contagens independentes. */
export const draftKey = (customerId, visitType) => `${customerId}|${visitType}`

/**
 * Rascunhos do formato antigo (chave = só o customerId, sem tipo de contagem)
 * não têm como ser reaproveitados: não dá para saber se aquilo era gôndola ou
 * estoque. Some com eles em vez de deixá-los presos no aparelho para sempre.
 */
function dropLegacyDrafts(all) {
  Object.keys(all).forEach((key) => {
    if (!key.includes('|')) delete all[key]
  })
  return all
}

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
  // { [customerId|visitType]: { client_uuid, visited_at, items: { [productId]: {...} } } }
  const drafts = ref(dropLegacyDrafts(load(DRAFTS_KEY)))
  // Contagens fechadas que ainda não subiram
  const queue = ref(JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'))
  const sending = ref(false)

  const persist = () => {
    save(DRAFTS_KEY, drafts.value)
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.value))
  }

  const pendingCount = computed(() => queue.value.length)

  function getDraft(customerId, visitType) {
    const key = draftKey(customerId, visitType)
    if (!drafts.value[key]) {
      drafts.value[key] = {
        customer_id: customerId,
        visit_type: visitType,
        client_uuid: newUuid(),
        visited_at: new Date().toISOString(),
        items: {},
      }
      persist()
    }
    return drafts.value[key]
  }

  /** Quantidade vazia (null/'') apaga o item: produto em branco é produto não contado. */
  function setItem(customerId, visitType, productId, { quantity, unit_type }) {
    const draft = getDraft(customerId, visitType)
    if (quantity === null || quantity === undefined || quantity === '') {
      delete draft.items[productId]
    } else {
      draft.items[productId] = {
        product_id: productId,
        quantity: Number(quantity),
        unit_type: unit_type || 'unidade',
      }
    }
    persist()
  }

  function itemsCount(customerId, visitType) {
    return Object.keys(drafts.value[draftKey(customerId, visitType)]?.items || {}).length
  }

  function clearDraft(customerId, visitType) {
    delete drafts.value[draftKey(customerId, visitType)]
    persist()
  }

  /** Fecha a contagem: tenta enviar; se falhar, enfileira para reenvio. */
  async function submit(customerId, visitType) {
    const draft = getDraft(customerId, visitType)
    const payload = {
      customer_id: customerId,
      visit_type: visitType,
      client_uuid: draft.client_uuid,
      visited_at: draft.visited_at,
      items: Object.values(draft.items),
      submit: true,
    }

    try {
      await merchandisingApi.saveVisit(payload)
      clearDraft(customerId, visitType)
      return { sent: true }
    } catch (error) {
      queue.value.push(payload)
      clearDraft(customerId, visitType)
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
