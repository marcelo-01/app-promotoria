<template>
  <q-page class="q-pa-md">
    <q-card flat bordered class="q-mb-md">
      <q-card-section>
        <div class="text-h6">{{ product?.name || '...' }}</div>
        <div class="text-caption text-grey-7">
          {{ product?.sku }} · unidade: {{ product?.unit }}
          <span v-if="product?.package_size > 1">
            · caixa com {{ product.package_size }}
          </span>
        </div>
        <div
          v-if="product?.last_quantity !== null && product?.last_quantity !== undefined"
          class="text-caption text-grey-7 q-mt-xs"
        >
          Contagem anterior: <b>{{ product.last_quantity }}</b>
        </div>
      </q-card-section>
    </q-card>

    <div class="row items-center q-col-gutter-sm q-mb-md">
      <div class="col-auto">
        <q-btn
          round color="grey-4" text-color="dark" icon="remove" size="lg"
          aria-label="Diminuir" @click="ajustar(-1)"
        />
      </div>
      <div class="col">
        <q-input
          ref="inputRef" v-model="quantidade" outlined
          type="number" inputmode="decimal" min="0"
          input-class="text-center text-h4 text-weight-bold"
          placeholder="0"
        />
      </div>
      <div class="col-auto">
        <q-btn
          round color="primary" icon="add" size="lg"
          aria-label="Aumentar" @click="ajustar(1)"
        />
      </div>
    </div>

    <q-input
      v-model="validade" outlined label="Validade (opcional)"
      mask="##/##/####" class="q-mb-md"
    >
      <template #append>
        <q-icon name="event" class="cursor-pointer">
          <q-popup-proxy cover transition-show="scale">
            <q-date v-model="validade" mask="DD/MM/YYYY" minimal />
          </q-popup-proxy>
        </q-icon>
      </template>
    </q-input>

    <q-input
      v-model="observacao" outlined label="Observação (opcional)"
      type="textarea" autogrow class="q-mb-lg"
    />

    <q-btn
      label="Salvar e voltar" color="primary" size="lg"
      class="full-width" unelevated no-caps icon="check"
      @click="salvar"
    />
  </q-page>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({
  customerId: { type: String, required: true },
  productId: { type: String, required: true },
})

const router = useRouter()
const visita = useVisitaStore()

const product = ref(null)
const quantidade = ref('')
const validade = ref('')
const observacao = ref('')
const inputRef = ref(null)

function ajustar(delta) {
  const atual = Number(quantidade.value || 0)
  quantidade.value = String(Math.max(0, atual + delta))
}

/** dd/mm/aaaa → aaaa-mm-dd (formato aceito pela API) */
function toISODate(value) {
  if (!value || value.length !== 10) return null
  const [dia, mes, ano] = value.split('/')
  return `${ano}-${mes}-${dia}`
}

function salvar() {
  visita.setItem(props.customerId, props.productId, {
    quantity: quantidade.value === '' ? null : quantidade.value,
    expires_at: toISODate(validade.value),
    notes: observacao.value || null,
  })
  router.back()
}

onMounted(async () => {
  // Recupera o que já foi digitado antes, se houver
  const existente = visita.getDraft(props.customerId).items[props.productId]
  if (existente) {
    quantidade.value = String(existente.quantity)
    observacao.value = existente.notes || ''
    if (existente.expires_at) {
      const [ano, mes, dia] = existente.expires_at.split('-')
      validade.value = `${dia}/${mes}/${ano}`
    }
  }

  const lista = await merchandisingApi.productsForCustomer(props.customerId)
  product.value = lista.find((p) => p.id === props.productId) || null

  await nextTick()
  inputRef.value?.focus()
})
</script>
