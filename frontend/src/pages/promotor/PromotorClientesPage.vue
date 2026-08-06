<!--
  Tela inicial do promotor: um card grande por cliente, com os dois destinos de
  contagem lado a lado. Card grande e botão grande porque isso é usado em pé,
  no corredor do mercado, com uma mão só.
-->
<template>
  <q-page class="q-pa-md">
    <q-input
      v-model="search" outlined dense clearable
      placeholder="Buscar cliente..." class="q-mb-md bg-white"
      @update:model-value="onSearch"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <div v-if="loading" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner v-else-if="!customers.length" class="bg-grey-2 text-grey-8 rounded-borders">
      <template #avatar><q-icon name="store" color="grey-6" /></template>
      Nenhum cliente atribuído a você. Fale com o administrador.
    </q-banner>

    <div v-else class="column q-gutter-md">
      <q-card v-for="customer in customers" :key="customer.id" flat bordered class="cliente-card">
        <q-card-section class="q-pb-sm">
          <div class="row items-center no-wrap">
            <q-avatar color="primary" text-color="white" icon="store" size="44px" class="q-mr-md" />
            <div class="col text-h6 text-weight-bold ellipsis-2-lines">
              {{ customer.name }}
            </div>
          </div>
        </q-card-section>

        <q-card-section class="row q-col-gutter-sm q-pt-none">
          <div v-for="tipo in TIPOS" :key="tipo.value" class="col-6">
            <q-btn
              stack unelevated no-caps
              class="full-width acao-btn"
              :color="tipo.color" :icon="tipo.icon"
              @click="abrir(customer, tipo.value)"
            >
              <div class="text-subtitle2 text-weight-bold q-mt-xs">{{ tipo.label }}</div>
              <q-badge
                v-if="pendente(customer.id, tipo.value)"
                color="warning" text-color="dark" floating
              >
                {{ pendente(customer.id, tipo.value) }}
              </q-badge>
            </q-btn>
            <div class="text-caption text-grey-7 text-center q-mt-xs">
              {{ ultimaContagem(customer, tipo.value) }}
            </div>
          </div>
        </q-card-section>
      </q-card>
    </div>
  </q-page>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const TIPOS = [
  { value: 'gondola', label: 'Gôndola', icon: 'shelves', color: 'primary' },
  { value: 'estoque', label: 'Estoque', icon: 'inventory_2', color: 'teal-8' },
]

const customers = ref([])
const loading = ref(false)
const search = ref('')
let debounce = null

async function carregar() {
  loading.value = true
  try {
    customers.value = await merchandisingApi.myCustomers({ search: search.value })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar clientes',
    })
  } finally {
    loading.value = false
  }
}

function onSearch() {
  clearTimeout(debounce)
  debounce = setTimeout(carregar, 350)
}

/** Itens já digitados neste aparelho e ainda não enviados. */
const pendente = (customerId, tipo) => visita.itemsCount(customerId, tipo)

function abrir(customer, tipo) {
  router.push({
    name: 'PromotorContagem',
    params: { customerId: customer.id, visitType: tipo },
    query: { c: customer.name },
  })
}

function ultimaContagem(customer, tipo) {
  const iso = tipo === 'gondola' ? customer.last_gondola_at : customer.last_estoque_at
  return iso ? new Date(iso).toLocaleDateString('pt-BR') : 'nunca contado'
}

onMounted(carregar)
onUnmounted(() => clearTimeout(debounce))
</script>

<style scoped>
.cliente-card {
  border-radius: 14px;
}

/* Alvo de toque grande: o promotor acerta o botão sem parar para mirar. */
.acao-btn {
  height: 104px;
  border-radius: 12px;
}

.acao-btn :deep(.q-icon) {
  font-size: 34px;
}
</style>
