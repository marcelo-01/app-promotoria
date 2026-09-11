<template>
  <q-page class="q-pa-md">
    <div class="row items-center justify-between q-mb-md">
      <div>
        <div class="text-h6">Contagens recebidas</div>
        <div class="text-caption text-grey-7">
          Uma linha por ida do promotor à loja, com gôndola e estoque juntos —
          igual à planilha, que só inclui o cliente cujas duas contagens do dia
          chegaram.
        </div>
      </div>
      <q-btn
        color="positive" icon="download" no-caps unelevated
        label="Baixar planilha do período" :loading="baixando"
        @click="exportarConsolidado"
      />
    </div>

    <!-- Filtros. Não há filtro por tipo de contagem: a linha é sempre dos dois
         lugares, e filtrar um lado só traria de volta as meias visitas. -->
    <q-card flat bordered class="q-mb-md">
      <q-card-section class="row q-col-gutter-md">
        <div class="col-12 col-md-3">
          <q-input v-model="filtros.date_from" outlined dense type="date" label="De"
                   stack-label @update:model-value="recarregar" />
        </div>
        <div class="col-12 col-md-3">
          <q-input v-model="filtros.date_to" outlined dense type="date" label="Até"
                   stack-label @update:model-value="recarregar" />
        </div>
        <div class="col-12 col-md-3">
          <q-select
            v-model="filtros.promoter_id" outlined dense clearable
            label="Promotor" :options="promotores"
            option-value="id" option-label="full_name" emit-value map-options
            @update:model-value="recarregar"
          />
        </div>
        <div class="col-12 col-md-3">
          <q-select
            v-model="filtros.status" outlined dense clearable
            label="Status" :options="statusOpcoes"
            option-value="value" option-label="label" emit-value map-options
            @update:model-value="recarregar"
          />
        </div>
      </q-card-section>
    </q-card>

    <q-table
      :rows="visitas" :columns="colunas" row-key="id"
      :loading="carregando" flat bordered
      v-model:pagination="paginacao" @request="carregar"
    >
      <!-- Os dois lados da mesma visita, um em cada coluna. Célula vazia é
           contagem que ainda não chegou; "sem produtos" é o promotor dizendo
           que passou lá e não havia nada — não é a mesma coisa. -->
      <template #body-cell-gondola="props">
        <q-td :props="props" class="text-right">
          <span v-if="!props.row.gondola" class="text-orange-9">não chegou</span>
          <span v-else-if="props.row.gondola.no_products" class="text-grey-7">sem produtos</span>
          <span v-else>{{ props.row.gondola.items_count }}</span>
        </q-td>
      </template>

      <template #body-cell-estoque="props">
        <q-td :props="props" class="text-right">
          <span v-if="!props.row.estoque" class="text-orange-9">não chegou</span>
          <span v-else-if="props.row.estoque.no_products" class="text-grey-7">sem produtos</span>
          <span v-else>{{ props.row.estoque.items_count }}</span>
        </q-td>
      </template>

      <!-- É isto que decide se esta visita já pode virar planilha -->
      <template #body-cell-missing_side="props">
        <q-td :props="props">
          <q-chip
            v-if="props.value" dense square outline
            color="orange-9" icon="hourglass_top"
          >
            Aguardando {{ rotuloTipo(props.value).toLowerCase() }}
          </q-chip>
          <q-chip v-else dense square outline color="positive" icon="done_all">
            Completa
          </q-chip>
        </q-td>
      </template>

      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense square
            :color="props.value === 'exported' ? 'positive' : 'primary'"
            text-color="white"
          >
            {{ props.value === 'exported' ? 'Processada' : 'Nova' }}
          </q-chip>
        </q-td>
      </template>

      <template #body-cell-acoes="props">
        <q-td :props="props" class="text-right">
          <q-btn
            flat dense round icon="visibility" color="grey-7"
            title="Ver os itens desta visita"
            @click="abrirDetalhe(props.row)"
          />
          <q-btn
            flat dense round icon="download" color="primary"
            :disable="Boolean(props.row.missing_side)"
            @click="exportarUma(props.row)"
          >
            <q-tooltip>
              {{ props.row.missing_side
                ? `Falta a contagem de ${rotuloTipo(props.row.missing_side).toLowerCase()} deste cliente`
                : 'Baixar a planilha deste cliente neste dia (gôndola + estoque)' }}
            </q-tooltip>
          </q-btn>
        </q-td>
      </template>

      <template #no-data>
        <div class="full-width text-center text-grey-7 q-pa-lg">
          Nenhuma contagem recebida com esses filtros.
        </div>
      </template>
    </q-table>

    <!-- Detalhe da visita: os dois lados, um embaixo do outro -->
    <q-dialog v-model="detalheAberto">
      <q-card style="min-width: 340px; max-width: 720px; width: 90vw">
        <q-card-section class="row items-center justify-between">
          <div>
            <div class="text-subtitle1">{{ detalhe?.linha?.customer_name }}</div>
            <div class="text-caption text-grey-7">
              {{ detalhe?.linha?.promoter_name }} ·
              {{ formatData(detalhe?.linha?.visited_at) }}
            </div>
          </div>
          <q-btn flat dense round icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section v-if="detalhe?.linha?.missing_side" class="q-pb-none">
          <q-banner dense class="bg-orange-1 rounded-borders">
            <template #avatar><q-icon name="hourglass_top" color="orange-9" /></template>
            Aguardando a contagem de
            {{ rotuloTipo(detalhe.linha.missing_side).toLowerCase() }} deste cliente —
            a planilha só sai com as duas.
          </q-banner>
        </q-card-section>

        <div v-if="detalhe?.carregando" class="text-center q-pa-lg">
          <q-spinner color="primary" size="2em" />
        </div>

        <div v-else style="max-height: 60vh; overflow-y: auto">
          <!-- As datas coletadas vêm ANTES dos dois lados: são do par inteiro,
               não de um lugar só, e são o motivo pelo qual esta visita rendeu uma
               ação de escoamento. -->
          <q-card-section v-if="vencimentos.length" class="q-pb-xs">
            <q-chip dense square outline color="orange-9" icon="schedule">
              Vencimentos coletados
            </q-chip>
            <q-list separator dense>
              <q-item v-for="linha in vencimentos" :key="linha.id">
                <q-item-section>
                  <q-item-label>{{ linha.product_name || 'Produto removido' }}</q-item-label>
                  <q-item-label caption :class="corDoVencimento(linha.expires_at)">
                    vence {{ formatDia(linha.expires_at) }} · {{ prazo(linha.expires_at) }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side class="text-weight-bold text-orange-9">
                  {{ formatQtd(linha.quantity) }} un
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>

          <template v-for="lado in ['gondola', 'estoque']" :key="lado">
            <q-card-section v-if="detalhe?.[lado]" class="q-pb-xs">
              <q-chip dense square outline
                      :color="lado === 'gondola' ? 'primary' : 'teal-8'"
                      :icon="lado === 'gondola' ? 'shelves' : 'inventory_2'">
                {{ rotuloTipo(lado) }}
              </q-chip>
              <span class="text-caption text-grey-7">
                {{ formatData(detalhe[lado].visited_at) }}
              </span>

              <q-banner v-if="detalhe[lado].no_products" dense
                        class="bg-grey-2 rounded-borders q-mt-sm">
                <template #avatar><q-icon name="do_not_disturb_on" color="grey-7" /></template>
                O promotor informou que não havia nenhum produto
                {{ lado === 'gondola' ? 'na gôndola' : 'no estoque' }}.
              </q-banner>

              <q-banner v-if="detalhe[lado].notes" dense
                        class="bg-grey-2 rounded-borders q-mt-sm">
                {{ detalhe[lado].notes }}
              </q-banner>
            </q-card-section>

            <q-list v-if="detalhe?.[lado]?.items?.length" separator>
              <q-item v-for="item in detalhe[lado].items" :key="item.id">
                <q-item-section>
                  <q-item-label>{{ item.product_name }}</q-item-label>
                  <!-- O que o promotor digitou, antes da conversão em unidades -->
                  <q-item-label caption>
                    {{ digitado(item) }}
                    <span v-if="item.expires_at"> · validade {{ formatDia(item.expires_at) }}</span>
                    <span v-if="item.notes"> · {{ item.notes }}</span>
                  </q-item-label>
                </q-item-section>
                <q-item-section side class="text-weight-bold text-primary">
                  {{ formatQtd(item.quantity) }} un
                </q-item-section>
              </q-item>
            </q-list>
          </template>
        </div>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { usersApi } from '@/api/users'

const $q = useQuasar()

const visitas = ref([])
const promotores = ref([])
const carregando = ref(false)
const baixando = ref(false)

const detalheAberto = ref(false)
const detalhe = ref(null)

const filtros = reactive({
  date_from: '', date_to: '', promoter_id: null, status: null,
})
const paginacao = ref({ page: 1, rowsPerPage: 25, rowsNumber: 0 })

const statusOpcoes = [
  { value: 'submitted', label: 'Nova' },
  { value: 'exported', label: 'Processada' },
]

const formatData = (v) => (v ? new Date(v).toLocaleString('pt-BR') : '—')
const formatDia = (v) => (v ? new Date(`${v}T00:00:00`).toLocaleDateString('pt-BR') : '—')
const formatQtd = (v) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 3 })
const rotuloTipo = (v) => (v === 'gondola' ? 'Gôndola' : 'Estoque')

/** "2 cx + 5 un" — o que foi contado, do jeito que foi contado. */
function digitado(item) {
  const partes = []
  if (Number(item.boxes)) partes.push(`${formatQtd(item.boxes)} cx`)
  if (Number(item.units)) partes.push(`${formatQtd(item.units)} un`)
  return partes.length ? partes.join(' + ') : 'nada encontrado'
}

const colunas = [
  { name: 'visited_at', label: 'Data', field: 'visited_at', align: 'left',
    format: (v) => (v ? new Date(v).toLocaleString('pt-BR') : '—') },
  { name: 'customer_name', label: 'Cliente', field: 'customer_name', align: 'left' },
  { name: 'promoter_name', label: 'Promotor', field: 'promoter_name', align: 'left' },
  { name: 'gondola', label: 'Gôndola', field: 'gondola', align: 'right' },
  { name: 'estoque', label: 'Estoque', field: 'estoque', align: 'right' },
  { name: 'missing_side', label: 'Par', field: 'missing_side', align: 'left' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

async function carregar(props) {
  const page = props?.pagination?.page || paginacao.value.page
  const rows = props?.pagination?.rowsPerPage || paginacao.value.rowsPerPage

  carregando.value = true
  try {
    const { items, total } = await merchandisingApi.visitPairs({
      ...filtros, limit: rows, offset: (page - 1) * rows,
    })
    visitas.value = items
    paginacao.value = { page, rowsPerPage: rows, rowsNumber: total }
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar contagens',
    })
  } finally {
    carregando.value = false
  }
}

/**
 * As datas coletadas na visita — as dos dois lados juntas, da mais próxima de
 * vencer para a mais distante.
 *
 * A coleta é do par, mas fica gravada no envio que a trouxe (o segundo dos dois
 * lados, o que fechou a visita). Por isso os dois lados são lidos e o resultado
 * é somado: de qual deles a linha veio não diz nada a quem lê.
 */
const vencimentos = computed(() => {
  const linhas = [
    ...(detalhe.value?.gondola?.expiries || []),
    ...(detalhe.value?.estoque?.expiries || []),
  ]
  return linhas.sort((a, b) => a.expires_at.localeCompare(b.expires_at))
})

/** Dias entre hoje e a data, em texto curto. */
function prazo(iso) {
  const dias = Math.round(
    (new Date(`${iso}T00:00:00`) - new Date().setHours(0, 0, 0, 0)) / 86400000
  )
  if (dias < 0) return `vencido há ${Math.abs(dias)} dia(s)`
  if (dias === 0) return 'vence hoje'
  return `faltam ${dias} dia(s)`
}

/** Vermelho para o que já venceu ou vence esta semana. */
function corDoVencimento(iso) {
  const dias = Math.round(
    (new Date(`${iso}T00:00:00`) - new Date().setHours(0, 0, 0, 0)) / 86400000
  )
  if (dias < 0) return 'text-negative text-weight-bold'
  return dias <= 7 ? 'text-orange-9 text-weight-bold' : 'text-grey-7'
}

/** Qualquer mudança de filtro volta para a primeira página. */
const recarregar = () =>
  carregar({ pagination: { page: 1, rowsPerPage: paginacao.value.rowsPerPage } })

/** Os itens dos dois lados, buscados em paralelo: a linha da tela traz só as
 *  contagens, e o detalhe é a única tela que precisa dos produtos. */
async function abrirDetalhe(linha) {
  detalhe.value = { linha, gondola: null, estoque: null, carregando: true }
  detalheAberto.value = true
  try {
    const [gondola, estoque] = await Promise.all([
      linha.gondola ? merchandisingApi.visit(linha.gondola.visit_id) : null,
      linha.estoque ? merchandisingApi.visit(linha.estoque.visit_id) : null,
    ])
    detalhe.value = { linha, gondola, estoque, carregando: false }
  } catch (error) {
    detalheAberto.value = false
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao abrir a contagem',
    })
  }
}

/** A planilha é sempre a do par — qualquer um dos dois lados serve de entrada,
 *  o servidor reencontra o outro sozinho. */
async function exportarUma(linha) {
  try {
    await merchandisingApi.exportVisit(linha.gondola?.visit_id || linha.estoque?.visit_id)
  } catch (error) {
    // Par incompleto: o servidor diz qual lado falta
    $q.notify({ type: 'negative', message: error.message, timeout: 6000 })
    return
  }
  // O download marca as duas contagens como processadas — recarrega o status
  await carregar()
}

async function exportarConsolidado() {
  baixando.value = true
  try {
    await merchandisingApi.exportConsolidated(filtros)
    await carregar()
  } catch (error) {
    $q.notify({ type: 'negative', message: error.message, timeout: 6000 })
  } finally {
    baixando.value = false
  }
}

onMounted(async () => {
  promotores.value = await usersApi.list({ role: 'promoter' })
  await carregar()
})
</script>
