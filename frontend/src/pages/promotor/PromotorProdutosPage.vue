<template>
  <q-page class="q-pa-md" style="padding-bottom: 88px">
    <q-input
      v-model="search" outlined dense clearable
      placeholder="Buscar produto..." class="q-mb-md"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <div v-if="loading" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner v-else-if="!products.length" class="bg-grey-2 text-grey-8 rounded-borders">
      <template #avatar><q-icon name="inventory_2" color="grey-6" /></template>
      Nenhum produto cadastrado para este cliente. Fale com o administrador.
    </q-banner>

    <q-list v-else separator class="rounded-borders bg-white">
      <q-item
        v-for="product in filtrados" :key="product.id"
        clickable v-ripple class="q-py-md"
        @click="contar(product)"
      >
        <q-item-section>
          <q-item-label class="text-weight-medium">{{ product.name }}</q-item-label>
          <q-item-label caption>
            {{ product.sku }} · {{ product.unit }}
            <span v-if="product.last_quantity !== null && product.last_quantity !== undefined">
              · anterior: {{ formatQtd(product.last_quantity) }}
            </span>
          </q-item-label>
        </q-item-section>

        <q-item-section side>
          <q-chip
            v-if="digitado(product.id) !== null"
            square color="primary" text-color="white" class="text-weight-bold"
          >
            {{ formatQtd(digitado(product.id)) }}
          </q-chip>
          <q-icon v-else name="edit" color="grey-5" />
        </q-item-section>
      </q-item>
    </q-list>

    <!-- Barra fixa de envio -->
    <q-footer class="bg-transparent q-pa-md" style="bottom: 50px">
      <q-btn
        :label="`Enviar contagem (${totalDigitado})`"
        color="positive" size="lg" class="full-width"
        icon="cloud_upload" unelevated no-caps
        :disable="totalDigitado === 0" :loading="enviando"
        @click="enviar"
      />
    </q-footer>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({ customerId: { type: String, required: true } })

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const products = ref([])
const loading = ref(false)
const enviando = ref(false)
const search = ref('')

const filtrados = computed(() => {
  const term = (search.value || '').trim().toLowerCase()
  if (!term) return products.value
  return products.value.filter(
    (p) =>
      p.name.toLowerCase().includes(term) ||
      (p.sku || '').toLowerCase().includes(term) ||
      (p.barcode || '').includes(term)
  )
})

const draft = computed(() => visita.getDraft(props.customerId))
const totalDigitado = computed(() => Object.keys(draft.value.items).length)

const digitado = (productId) => {
  const item = draft.value.items[productId]
  return item ? item.quantity : null
}

const formatQtd = (value) =>
  Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

function contar(product) {
  router.push({
    name: 'PromotorContagem',
    params: { customerId: props.customerId, productId: product.id },
  })
}

async function enviar() {
  enviando.value = true
  const { sent } = await visita.submit(props.customerId)
  enviando.value = false

  $q.notify({
    type: sent ? 'positive' : 'warning',
    message: sent
      ? 'Contagem enviada com sucesso.'
      : 'Sem conexão. A contagem foi salva e será enviada automaticamente.',
    position: 'top',
    timeout: 4000,
  })
  router.push({ name: 'PromotorClientes' })
}

onMounted(async () => {
  loading.value = true
  try {
    products.value = await merchandisingApi.productsForCustomer(props.customerId)
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar produtos',
    })
  } finally {
    loading.value = false
  }
})
</script>
