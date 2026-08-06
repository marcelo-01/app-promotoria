<template>
  <q-page class="q-pa-md">
    <q-input
      v-model="search" outlined dense clearable
      placeholder="Buscar cliente..." class="q-mb-md"
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

    <q-list v-else separator class="rounded-borders bg-white">
      <q-item
        v-for="customer in customers" :key="customer.id"
        clickable v-ripple class="q-py-md"
        @click="abrir(customer)"
      >
        <q-item-section avatar>
          <q-avatar color="primary" text-color="white" icon="store" />
        </q-item-section>

        <q-item-section>
          <q-item-label class="text-weight-medium">{{ customer.name }}</q-item-label>
          <q-item-label caption lines="1">
            {{ formatCidade(customer.address) }}
          </q-item-label>
          <q-item-label caption class="text-grey-6">
            {{ customer.last_visited_at
              ? `Última contagem: ${formatData(customer.last_visited_at)}`
              : 'Nunca contado' }}
          </q-item-label>
        </q-item-section>

        <q-item-section side>
          <!-- Rascunho em andamento neste aparelho -->
          <q-badge v-if="rascunho(customer.id)" color="warning" text-color="dark">
            {{ rascunho(customer.id) }} itens
          </q-badge>
          <q-icon v-else name="chevron_right" color="grey-5" />
        </q-item-section>
      </q-item>
    </q-list>
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

const rascunho = (customerId) => visita.itemsCount(customerId)

function abrir(customer) {
  router.push({ name: 'PromotorProdutos', params: { customerId: customer.id } })
}

const formatCidade = (address) =>
  address?.city ? `${address.city}${address.state ? ' - ' + address.state : ''}` : '—'

const formatData = (iso) => new Date(iso).toLocaleDateString('pt-BR')

onMounted(carregar)
onUnmounted(() => clearTimeout(debounce))
</script>
