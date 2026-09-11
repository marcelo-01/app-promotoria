import apiClient from '@/api/client'

const normalizeParams = (params = {}) => {
  const clean = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') clean[key] = value
  })
  return clean
}

export const merchandisingApi = {
  // ── Promotor ──────────────────────────────────────────────────────────
  async myCustomers(params = {}) {
    const { data } = await apiClient.get('/merchandising/my-customers', {
      params: normalizeParams(params),
    })
    return data
  },

  /** Folha de contagem: cliente + produtos + contagem anterior, numa chamada só. */
  async countSheet(customerId, visitType) {
    const { data } = await apiClient.get(
      `/merchandising/customers/${customerId}/count-sheet/${visitType}`
    )
    return data
  },

  /** Folha de correção de um envio: só os produtos contados, já preenchidos. */
  async visitSheet(visitId) {
    const { data } = await apiClient.get(`/merchandising/visits/${visitId}/count-sheet`)
    return data
  },

  async saveVisit(payload) {
    // Timeout maior: o promotor pode ter 40 itens e sinal ruim de supermercado.
    // O default do apiClient (10s) é curto demais para este envio.
    const { data } = await apiClient.post('/merchandising/visits', payload, {
      timeout: 30000,
    })
    return data
  },

  /** Corrige as quantidades de um envio. Mesmo timeout largo do envio. */
  async updateVisit(visitId, payload) {
    const { data } = await apiClient.put(`/merchandising/visits/${visitId}`, payload, {
      timeout: 30000,
    })
    return data
  },

  async submitVisit(visitId) {
    const { data } = await apiClient.post(`/merchandising/visits/${visitId}/submit`)
    return data
  },

  async myVisits(params = {}) {
    const { data } = await apiClient.get('/merchandising/visits/mine', {
      params: normalizeParams(params),
    })
    return data
  },

  /** Registra o vencido que o promotor retirou da loja. Idempotente pelo
   *  client_uuid, como as contagens. */
  async saveRemoval(payload) {
    const { data } = await apiClient.post('/merchandising/removals', payload, {
      timeout: 30000,
    })
    return data
  },

  /** O que já foi retirado neste cliente hoje. */
  async removals(customerId, day) {
    const { data } = await apiClient.get(
      `/merchandising/customers/${customerId}/removals`,
      { params: normalizeParams({ day }) }
    )
    return data
  },

  // ── Administrador ─────────────────────────────────────────────────────

  /**
   * Planilha de faturamento do ERP.
   *
   * `preview` lê e relata sem gravar nada — é o que acontece ao anexar, para o
   * administrador conferir antes de confirmar. `import` grava.
   *
   * Timeout largo: são milhares de linhas por arquivo, e o servidor ainda casa
   * cada uma com o cadastro antes de responder.
   */
  async previewInvoices(file) {
    return enviarPlanilha('/merchandising/invoices/preview', file)
  },

  async importInvoices(file) {
    return enviarPlanilha('/merchandising/invoices/import', file)
  },


  /** Os indicadores de evolução do estoque: parados, sumidos, voltados e
   *  gôndola vazia com saldo no depósito. Tudo é variação entre contagens —
   *  o app não conhece entregas, então nada disso é venda. */
  async stockInsights(params = {}) {
    const { data } = await apiClient.get('/merchandising/stock-insights', {
      params: normalizeParams(params),
    })
    return data
  },

  /** A linha do tempo de um cliente — da loja inteira, ou de um produto. */
  async stockHistory(params = {}) {
    const { data } = await apiClient.get('/merchandising/stock-history', {
      params: normalizeParams(params),
    })
    return data
  },

  /** A lista do administrador: uma linha por ida à loja, com gôndola e estoque
   *  juntos — a mesma unidade que a planilha usa. `visit_type` não entra: a
   *  linha é sempre dos dois lugares. */
  async visitPairs(params = {}) {
    const { data } = await apiClient.get('/merchandising/visit-pairs', {
      params: normalizeParams(params),
    })
    return data
  },

  async visit(visitId) {
    const { data } = await apiClient.get(`/merchandising/visits/${visitId}`)
    return data
  },

  /** Planilha de uma contagem — na prática, a do par dela: gôndola + estoque
   *  do mesmo cliente no mesmo dia. Sem o par, o servidor recusa com o motivo. */
  async exportVisit(visitId) {
    const response = await baixar(`/merchandising/visits/${visitId}/export.xlsx`)
    downloadBlob(response)
  },

  /** Planilha do período. `visit_type` não entra: ela é sempre dos dois lugares. */
  async exportConsolidated({ visit_type: _ignorado, ...params } = {}) {
    const response = await baixar('/merchandising/exports.xlsx', {
      params: normalizeParams(params),
      timeout: 60000,
    })
    downloadBlob(response)
  },

  async getAssignments(promoterId) {
    const { data } = await apiClient.get(`/merchandising/assignments/${promoterId}`)
    return data
  },

  async setAssignments(promoterId, customerIds) {
    await apiClient.put(`/merchandising/assignments/${promoterId}`, {
      customer_ids: customerIds,
    })
  },

  async getCustomerMix(customerId) {
    const { data } = await apiClient.get(`/merchandising/customers/${customerId}/mix`)
    return data
  },

  async setCustomerMix(customerId, productIds) {
    await apiClient.put(`/merchandising/customers/${customerId}/mix`, {
      product_ids: productIds,
    })
  },
}

/** POST multipart da planilha, com o `detail` do servidor já legível. */
async function enviarPlanilha(url, file) {
  const form = new FormData()
  form.append('file', file)
  try {
    const { data } = await apiClient.post(url, form, { timeout: 120000 })
    return data
  } catch (error) {
    throw new Error(
      error.response?.data?.detail || 'Não foi possível ler a planilha.'
    )
  }
}

/**
 * GET de planilha, com o erro já legível.
 *
 * Com `responseType: 'blob'` o corpo do erro também volta como Blob — o
 * `detail` que o servidor mandou ("a contagem de estoque ainda não chegou")
 * fica ilegível dentro dele, e a tela acabaria mostrando um erro genérico bem
 * onde o motivo importa.
 */
async function baixar(url, config = {}) {
  try {
    return await apiClient.get(url, { responseType: 'blob', ...config })
  } catch (error) {
    throw new Error((await detalheDoErro(error)) || 'Erro ao gerar a planilha')
  }
}

/** O `detail` que o servidor mandou, de dentro do Blob de erro. */
async function detalheDoErro(error) {
  const corpo = error.response?.data
  if (!(corpo instanceof Blob)) return corpo?.detail || null
  try {
    return JSON.parse(await corpo.text()).detail || null
  } catch {
    return null
  }
}

/** Extrai o nome do arquivo do Content-Disposition e dispara o download. */
function downloadBlob(response) {
  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match ? match[1] : 'planilha.xlsx'

  const url = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
