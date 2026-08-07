<template>
  <q-page class="q-pa-md">
    <div class="row items-center justify-between q-mb-md">
      <div class="text-h6">Contagens recebidas</div>
      <q-btn
        color="positive" icon="download" no-caps unelevated
        label="Baixar planilha do período" :loading="baixando"
        @click="exportarConsolidado"
      />
    </div>

    <!-- Filtros -->
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
            v-model="filtros.visit_type" outlined dense clearable
            label="Contagem" :options="tiposContagem"
            option-value="value" option-label="label" emit-value map-options
            @update:model-value="recarregar"
          />
        </div>
        <div class="col-12 col-md-3">
          <q-select
            v-model="filtros.status" outlined dense clearable
            label="Status" :options="['submitted', 'exported']"
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
      <template #body-cell-visit_type="props">
        <q-td :props="props">
          <q-chip
            dense square outline
            :color="props.value === 'gondola' ? 'primary' : 'teal-8'"
            :icon="props.value === 'gondola' ? 'shelves' : 'inventory_2'"
          >
            {{ rotuloTipo(props.value) }}
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
            title="Ver itens desta contagem"
            @click="abrirDetalhe(props.row.id)"
          />
          <q-btn
            flat dense round icon="download" color="primary"
            title="Baixar planilha desta contagem"
            @click="exportarUma(props.row.id)"
          />
        </q-td>
      </template>

      <template #no-data>
        <div class="full-width text-center text-grey-7 q-pa-lg">
          Nenhuma contagem recebida com esses filtros.
        </div>
      </template>
    </q-table>

    <!-- Detalhe da contagem -->
    <q-dialog v-model="detalheAberto">
      <q-card style="min-width: 340px; max-width: 720px; width: 90vw">
        <q-card-section class="row items-center justify-between">
          <div>
            <div class="text-subtitle1">
              {{ detalhe?.customer_name }}
              <q-chip dense square outline
                      :color="detalhe?.visit_type === 'gondola' ? 'primary' : 'teal-8'">
                {{ rotuloTipo(detalhe?.visit_type) }}
              </q-chip>
            </div>
            <div class="text-caption text-grey-7">
              {{ detalhe?.promoter_name }} · {{ formatData(detalhe?.visited_at) }}
            </div>
          </div>
          <q-btn flat dense round icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section v-if="detalhe?.notes">
          <q-banner dense class="bg-grey-2 rounded-borders">{{ detalhe.notes }}</q-banner>
        </q-card-section>

        <q-list separator style="max-height: 55vh; overflow-y: auto">
          <q-item v-for="item in detalhe?.items || []" :key="item.id">
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
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
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
  date_from: '', date_to: '', promoter_id: null, visit_type: null, status: null,
})
const paginacao = ref({ page: 1, rowsPerPage: 25, rowsNumber: 0 })

const tiposContagem = [
  { value: 'gondola', label: 'Gôndola' },
  { value: 'estoque', label: 'Estoque' },
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
  { name: 'visit_type', label: 'Contagem', field: 'visit_type', align: 'left' },
  { name: 'items_count', label: 'Itens', field: 'items_count', align: 'right' },
  { name: 'status', label: 'Status', field: 'status', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

async function carregar(props) {
  const page = props?.pagination?.page || paginacao.value.page
  const rows = props?.pagination?.rowsPerPage || paginacao.value.rowsPerPage

  carregando.value = true
  try {
    const { items, total } = await merchandisingApi.visits({
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

/** Qualquer mudança de filtro volta para a primeira página. */
const recarregar = () =>
  carregar({ pagination: { page: 1, rowsPerPage: paginacao.value.rowsPerPage } })

async function abrirDetalhe(id) {
  detalhe.value = await merchandisingApi.visit(id)
  detalheAberto.value = true
}

async function exportarUma(id) {
  await merchandisingApi.exportVisit(id)
  // O download marca a contagem como processada — recarrega para refletir o status
  await carregar()
}

async function exportarConsolidado() {
  baixando.value = true
  try {
    await merchandisingApi.exportConsolidated(filtros)
    await carregar()
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao gerar a planilha',
    })
  } finally {
    baixando.value = false
  }
}

onMounted(async () => {
  promotores.value = await usersApi.list({ role: 'promoter' })
  await carregar()
})
</script>
