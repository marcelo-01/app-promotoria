import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { merchandisingApi } from '@/api/merchandising'

const DRAFTS_KEY = 'estoque_drafts'
const QUEUE_KEY = 'estoque_queue'
const DONE_KEY = 'estoque_concluidas'

const load = (key) => JSON.parse(localStorage.getItem(key) || '{}')
const save = (key, value) => localStorage.setItem(key, JSON.stringify(value))

/** Gôndola e estoque do mesmo cliente são contagens independentes. */
export const draftKey = (customerId, visitType) => `${customerId}|${visitType}`

/**
 * Dia local em YYYY-MM-DD.
 *
 * É o que zera o "concluído" à meia-noite sem relógio nem tarefa agendada: a
 * marca guarda o dia em que a contagem foi enviada e a tela só a considera se
 * for o dia de hoje. Passou das 00:00, a marca de ontem deixa de valer sozinha.
 */
export function diaLocal(value = new Date()) {
  const d = new Date(value)
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0'),
  ].join('-')
}

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

/**
 * Itens gravados quando a contagem era um número só + a unidade escolhida.
 * Viram caixas ou unidades avulsas conforme aquela escolha.
 */
function migrateItems(all) {
  Object.values(all).forEach((draft) => {
    Object.values(draft.items || {}).forEach((item) => {
      if (item.boxes !== undefined || item.units !== undefined) return
      const quantidade = Number(item.quantity) || 0
      const eraCaixa = item.unit_type === 'caixa'
      item.boxes = eraCaixa ? quantidade : null
      item.units = eraCaixa ? null : quantidade
      delete item.quantity
      delete item.unit_type
    })
  })
  return all
}

/** Marcas de outros dias não interessam a ninguém — não ficam no aparelho. */
function dropOldMarks(all) {
  const hoje = diaLocal()
  Object.keys(all).forEach((key) => {
    if (all[key]?.dia !== hoje) delete all[key]
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

/** '' / null viram null (não contado); qualquer número vira número. */
const numero = (value) =>
  value === null || value === undefined || value === '' ? null : Number(value)

export const useVisitaStore = defineStore('visita', () => {
  // { [customerId|visitType]: { client_uuid, visited_at, items: { [productId]: {...} } } }
  const drafts = ref(migrateItems(dropLegacyDrafts(load(DRAFTS_KEY))))
  // Contagens fechadas que ainda não subiram
  const queue = ref(JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'))
  // { [customerId|visitType]: { dia, pendente } } — o "já contei aqui hoje"
  const concluidas = ref(dropOldMarks(load(DONE_KEY)))
  const sending = ref(false)

  const persist = () => {
    save(DRAFTS_KEY, drafts.value)
    save(DONE_KEY, concluidas.value)
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

  /** Os dois campos vazios apagam o item: produto em branco é produto não contado.
   *  Campo em branco fica `null` (e não 0) para a tela reabrir exatamente como
   *  o promotor deixou — 0 digitado é uma afirmação, branco não é. */
  function setItem(customerId, visitType, productId, { boxes, units }) {
    const draft = getDraft(customerId, visitType)
    const caixas = numero(boxes)
    const unidades = numero(units)

    if (caixas === null && unidades === null) {
      delete draft.items[productId]
    } else {
      draft.items[productId] = { product_id: productId, boxes: caixas, units: unidades }
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

  // ── "Já contei aqui hoje" ───────────────────────────────────────────────

  /** Marca a contagem como feita hoje. `pendente` = fechada mas ainda na fila. */
  function marcarConcluida(customerId, visitType, pendente = false) {
    concluidas.value[draftKey(customerId, visitType)] = { dia: diaLocal(), pendente }
    persist()
  }

  const marcaDeHoje = (customerId, visitType) => {
    const marca = concluidas.value[draftKey(customerId, visitType)]
    return marca?.dia === diaLocal() ? marca : null
  }

  const concluidaHoje = (customerId, visitType) => Boolean(marcaDeHoje(customerId, visitType))

  const aguardandoEnvio = (customerId, visitType) =>
    marcaDeHoje(customerId, visitType)?.pendente === true

  /** Fecha a contagem: tenta enviar; se falhar, enfileira para reenvio. */
  async function submit(customerId, visitType) {
    const draft = getDraft(customerId, visitType)
    const payload = {
      customer_id: customerId,
      visit_type: visitType,
      client_uuid: draft.client_uuid,
      visited_at: draft.visited_at,
      // Campo deixado em branco vira 0 só aqui, na hora de fechar a contagem
      items: Object.values(draft.items).map((item) => ({
        product_id: item.product_id,
        boxes: item.boxes || 0,
        units: item.units || 0,
      })),
      submit: true,
    }

    try {
      await merchandisingApi.saveVisit(payload)
      clearDraft(customerId, visitType)
      marcarConcluida(customerId, visitType)
      return { sent: true }
    } catch (error) {
      queue.value.push(payload)
      clearDraft(customerId, visitType)
      // Sem sinal, o promotor contou do mesmo jeito: o cliente aparece como
      // concluído, só que avisando que o envio ainda não subiu.
      marcarConcluida(customerId, visitType, true)
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
        // Só tira o "aguardando envio" se a marca for de hoje: contagem de
        // ontem que subiu agora não acende o concluído de hoje.
        const marca = marcaDeHoje(payload.customer_id, payload.visit_type)
        if (marca) marca.pendente = false
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
    drafts, queue, concluidas, sending, pendingCount,
    getDraft, setItem, itemsCount, clearDraft, submit, flushQueue,
    marcarConcluida, concluidaHoje, aguardandoEnvio,
  }
})
