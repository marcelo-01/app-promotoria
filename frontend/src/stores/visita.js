import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { merchandisingApi } from '@/api/merchandising'
import { diasEntre, veredito } from '@/lib/vencimento'

const DRAFTS_KEY = 'estoque_drafts'
const QUEUE_KEY = 'estoque_queue'
const DONE_KEY = 'estoque_concluidas'
// Totais já contados hoje em cada cliente, separados por lado. É o que permite
// somar gôndola + estoque no aparelho, sem perguntar nada ao servidor.
const TOTAIS_KEY = 'estoque_totais'
// A coleta de vencimento retida: a contagem que não subiu porque falta digitar
// as datas.
const VENCIMENTOS_KEY = 'estoque_vencimentos'
// O vencido que o promotor retirou da loja, ainda em digitação.
const RETIRADAS_KEY = 'estoque_retiradas'

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
  // { [customerId|visitType]: { client_uuid, visited_at, no_products, items: { [productId]: {...} } } }
  const drafts = ref(migrateItems(dropLegacyDrafts(load(DRAFTS_KEY))))
  // Contagens fechadas que ainda não subiram
  const queue = ref(JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'))
  // { [customerId|visitType]: { dia, pendente } } — o "já contei aqui hoje"
  const concluidas = ref(dropOldMarks(load(DONE_KEY)))
  // { [customerId]: { dia, lados: { gondola: {produtoId: unidades}, estoque: {...} } } }
  const totais = ref(dropOldMarks(load(TOTAIS_KEY)))
  // { [customerId]: { dia, visit_type, produtos: [...], linhas: {...} } }
  const vencimentos = ref(dropOldMarks(load(VENCIMENTOS_KEY)))
  // { [customerId]: { dia, client_uuid, linhas: [{product_id, texto, boxes, units}] } }
  const retiradas = ref(dropOldMarks(load(RETIRADAS_KEY)))
  const sending = ref(false)

  const persist = () => {
    save(DRAFTS_KEY, drafts.value)
    save(DONE_KEY, concluidas.value)
    save(TOTAIS_KEY, totais.value)
    save(VENCIMENTOS_KEY, vencimentos.value)
    save(RETIRADAS_KEY, retiradas.value)
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
        // Quadrado "não tem produtos aqui", marcado no topo da tela
        no_products: false,
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

  /** O promotor declarou que não há produto nenhum neste lugar hoje.
   *  Fica no rascunho junto com o resto: sair da tela não perde a marcação, e
   *  o que já tinha sido digitado continua guardado caso ele desmarque. */
  function setSemProdutos(customerId, visitType, valor) {
    getDraft(customerId, visitType).no_products = Boolean(valor)
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

  // ── Vencimento ──────────────────────────────────────────────────────────

  const outroLado = (visitType) => (visitType === 'gondola' ? 'estoque' : 'gondola')

  /** Marca de hoje deste cliente numa das duas listas por cliente. */
  const deHoje = (mapa, customerId) =>
    mapa.value[customerId]?.dia === diaLocal() ? mapa.value[customerId] : null

  /** Guarda o que foi contado neste lado, em unidades, por produto.
   *  Por LADO e não somado: recontar a gôndola no mesmo dia tem de substituir o
   *  número da gôndola, não empilhar em cima do que já estava. */
  function registrarTotais(customerId, visitType, porProduto) {
    const atual = deHoje(totais, customerId) || { dia: diaLocal(), lados: {} }
    atual.lados[visitType] = porProduto
    totais.value[customerId] = atual
    persist()
  }

  /**
   * O total do PAR por produto: o que este lado acabou de contar mais o que o
   * outro lado já trouxe hoje.
   *
   * É este número que a coleta de vencimento reparte em datas — não o de um lado
   * só. A mercadoria que vence dia 20 pode estar metade na prateleira e metade
   * no depósito, e o promotor não contou onde cada data está.
   */
  function totalDoPar(customerId, visitType, desteLado) {
    const doOutro = deHoje(totais, customerId)?.lados?.[outroLado(visitType)] || {}
    const soma = { ...doOutro }
    Object.entries(desteLado).forEach(([productId, unidades]) => {
      soma[productId] = (soma[productId] || 0) + unidades
    })
    return soma
  }

  /**
   * Os produtos que barram este envio — ou lista vazia, se nenhum barra.
   *
   * Só decide com o par fechando: enquanto o outro lado não chegou, não existe
   * total para repartir em datas, e barrar o primeiro lado seria pedir o
   * vencimento de metade do estoque.
   *
   * `products` é a folha que o servidor mandou ao abrir a tela, e `diaAnterior`
   * é a ponta de baixo do ciclo que veio com ela. A ponta de cima é HOJE: quem
   * fecha a conta é este aparelho, com o número que acabou de ser contado, e não
   * o servidor com o retrato da visita passada. A regra está em `lib/vencimento`.
   */
  function pendenciaDeVencimento(customerId, visitType, products, desteLado, diaAnterior) {
    if (!concluidaHoje(customerId, outroLado(visitType))) return []
    if (!diaAnterior) return []

    const ciclo = diasEntre(diaAnterior, diaLocal())
    const total = totalDoPar(customerId, visitType, desteLado)

    const pendentes = []
    products.forEach((product) => {
      const conta = veredito({
        shelfLife: product.expiry_shelf_life,
        previousStock: product.expiry_previous_stock,
        invoiced: product.expiry_invoiced,
        gifted: product.expiry_gifted,
        removed: product.expiry_removed,
        currentStock: total[product.id] || 0,
        cycleDays: ciclo,
      })
      if (!conta) return

      pendentes.push({
        product_id: product.id,
        name: product.name,
        image_url: product.image_url || null,
        package_size: Number(product.package_size) || 1,
        total: total[product.id],
        // A conta aberta, para a tela de vencimento poder explicar por que este
        // produto apareceu — sem precisar de rede para perguntar de novo.
        expiry_reason: conta.reason,
        expiry_days_to_clear: conta.daysToClear,
        expiry_shelf_life: conta.shelfLife,
        expiry_cycle_days: conta.cycleDays,
        expiry_sold: conta.sold,
      })
    })
    return pendentes
  }

  /** Retém a contagem e abre a coleta. O rascunho continua intacto: é ele que
   *  será enviado quando as datas fecharem, e é ele que segura a contagem se o
   *  aparelho desligar no meio. */
  function abrirVencimento(customerId, visitType, produtos, totaisPorProduto) {
    const anterior = deHoje(vencimentos, customerId)
    vencimentos.value[customerId] = {
      dia: diaLocal(),
      visit_type: visitType,
      produtos,
      // O que ESTE lado contou. Fica aqui porque quem vai chamar o envio é a
      // tela de vencimento, que não tem a folha de produtos para reconverter
      // caixas em unidades.
      totais_lado: totaisPorProduto,
      // Reabrir a coleta não apaga o que já tinha sido digitado nela.
      linhas: anterior?.linhas || {},
    }
    persist()
  }

  const vencimentoPendente = (customerId) => deHoje(vencimentos, customerId)

  /** As datas digitadas para um produto: [{ expires_at, boxes, units }]. */
  function setLinhasVencimento(customerId, productId, linhas) {
    const pendente = deHoje(vencimentos, customerId)
    if (!pendente) return
    pendente.linhas[productId] = linhas
    persist()
  }

  function fecharVencimento(customerId) {
    delete vencimentos.value[customerId]
    persist()
  }

  // ── Vencido retirado da loja ────────────────────────────────────────────

  /**
   * O rascunho da retirada de hoje neste cliente.
   *
   * Um `client_uuid` por retirada, não por linha: o servidor substitui o
   * conjunto inteiro quando a fila offline reenvia, então corrigir uma linha e
   * mandar de novo não deixa a versão antiga para trás.
   */
  function getRetirada(customerId) {
    const atual = deHoje(retiradas, customerId)
    if (atual) return atual

    retiradas.value[customerId] = {
      dia: diaLocal(),
      client_uuid: newUuid(),
      removed_at: new Date().toISOString(),
      linhas: [],
    }
    persist()
    return retiradas.value[customerId]
  }

  function setLinhasRetirada(customerId, linhas) {
    getRetirada(customerId).linhas = linhas
    persist()
  }

  const retiradaPendente = (customerId) => deHoje(retiradas, customerId)

  function clearRetirada(customerId) {
    delete retiradas.value[customerId]
    persist()
  }

  /** Fecha a retirada: tenta enviar; se falhar, enfileira. Lista vazia é um
   *  envio legítimo — é assim que o promotor desfaz o que registrou por engano. */
  async function submitRetirada(customerId, items) {
    const rascunho = getRetirada(customerId)
    const payload = {
      tipo: 'retirada',
      customer_id: customerId,
      client_uuid: rascunho.client_uuid,
      removed_at: rascunho.removed_at,
      items,
    }

    try {
      await merchandisingApi.saveRemoval(payload)
      clearRetirada(customerId)
      return { sent: true }
    } catch (error) {
      queue.value.push(payload)
      clearRetirada(customerId)
      persist()
      return { sent: false, error }
    }
  }

  // ── Envio ───────────────────────────────────────────────────────────────

  /**
   * Fecha a contagem: tenta enviar; se falhar, enfileira para reenvio.
   *
   * `totaisPorProduto` é o que este lado contou, em unidades — fica guardado no
   * aparelho para o outro lado somar. `expiries` são as datas coletadas, quando
   * houve coleta: sobem no MESMO payload da contagem, de propósito. Separá-las
   * deixaria a contagem subir e a coleta ficar para trás numa fila offline, que
   * é exatamente o que o bloqueio existe para impedir.
   */
  async function submit(customerId, visitType, { totaisPorProduto, expiries } = {}) {
    const draft = getDraft(customerId, visitType)
    const semProdutos = Boolean(draft.no_products)
    const payload = {
      customer_id: customerId,
      visit_type: visitType,
      client_uuid: draft.client_uuid,
      visited_at: draft.visited_at,
      no_products: semProdutos,
      // "Não tem produtos aqui" manda a contagem vazia: o que estivesse
      // digitado antes de marcar o quadrado não vai junto.
      // Campo deixado em branco vira 0 só aqui, na hora de fechar a contagem
      items: semProdutos ? [] : Object.values(draft.items).map((item) => ({
        product_id: item.product_id,
        boxes: item.boxes || 0,
        units: item.units || 0,
      })),
      expiries: expiries || [],
      submit: true,
    }

    if (totaisPorProduto) registrarTotais(customerId, visitType, totaisPorProduto)

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
        // A fila carrega contagens e retiradas de vencido. O tipo só existe nas
        // segundas: payload antigo, gravado antes desta versão, é contagem.
        if (payload.tipo === 'retirada') {
          await merchandisingApi.saveRemoval(payload)
        } else {
          await merchandisingApi.saveVisit(payload)
        }
        sent += 1
        // Só tira o "aguardando envio" se a marca for de hoje: contagem de
        // ontem que subiu agora não acende o concluído de hoje.
        const marca = payload.visit_type
          ? marcaDeHoje(payload.customer_id, payload.visit_type)
          : null
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
    drafts, queue, concluidas, totais, vencimentos, retiradas, sending, pendingCount,
    getDraft, setItem, setSemProdutos, itemsCount, clearDraft, submit, flushQueue,
    marcarConcluida, concluidaHoje, aguardandoEnvio,
    pendenciaDeVencimento, abrirVencimento, vencimentoPendente,
    setLinhasVencimento, fecharVencimento,
    getRetirada, setLinhasRetirada, retiradaPendente, clearRetirada, submitRetirada,
  }
})
