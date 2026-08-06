<!--
  Contagem de um cliente, em um dos dois lugares (gôndola ou estoque).

  Um produto por tela: o promotor tem o celular numa mão e o produto na outra,
  então a foto precisa ser grande o bastante para reconhecer a embalagem sem ler
  nada, e o campo de quantidade precisa estar sempre no mesmo lugar. Arrastar
  para baixo passa para o próximo produto (scroll-snap), e produto sem número
  digitado simplesmente não é enviado.
-->
<template>
  <q-page class="contagem-page">
    <div v-if="loading" class="column items-center justify-center full-height">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner
      v-else-if="!products.length"
      class="bg-grey-2 text-grey-8 rounded-borders q-ma-md"
    >
      <template #avatar><q-icon name="inventory_2" color="grey-6" /></template>
      Nenhum produto cadastrado para este cliente. Fale com o administrador.
    </q-banner>

    <div v-else class="painel-scroll">
      <section v-for="(product, index) in products" :key="product.id" class="painel">
        <!-- ── Foto: ocupa toda a altura do card ─────────────────────── -->
        <div class="foto">
          <img
            v-if="imagem(product)"
            :src="imagem(product)" :alt="product.name" class="foto-img"
          />
          <div v-else class="foto-vazia column items-center justify-center">
            <q-icon name="photo_camera" size="52px" color="indigo-4" />
            <div class="text-caption text-indigo-4 q-mt-sm">sem foto</div>
          </div>

          <q-badge class="contador" color="primary" text-color="white">
            {{ index + 1 }} / {{ products.length }}
          </q-badge>

          <div class="foto-nome">{{ product.name }}</div>
        </div>

        <!-- ── Quantidade ────────────────────────────────────────────── -->
        <div class="controle column items-center justify-center">
          <q-btn-toggle
            v-model="form[product.id].unit_type"
            spread unelevated no-caps dense
            class="unidade-toggle"
            toggle-color="primary" color="grey-3" text-color="grey-8"
            :options="UNIDADES"
            @update:model-value="persistir(product.id)"
          />

          <q-btn
            round unelevated color="grey-3" text-color="dark" icon="keyboard_arrow_up"
            size="lg" class="q-mt-md" aria-label="Aumentar"
            @click="ajustar(product.id, 1)"
          />

          <q-input
            v-model="form[product.id].quantity"
            outlined type="number" inputmode="numeric" min="0" step="1"
            placeholder="—" class="quantidade q-my-sm"
            input-class="text-center text-weight-bolder"
            @update:model-value="persistir(product.id)"
          />

          <q-btn
            round unelevated color="grey-3" text-color="dark" icon="keyboard_arrow_down"
            size="lg" aria-label="Diminuir"
            @click="ajustar(product.id, -1)"
          />

          <q-btn
            flat dense no-caps size="sm" color="grey-7" label="Limpar"
            class="q-mt-sm"
            :disable="form[product.id].quantity === ''"
            @click="limpar(product.id)"
          />

          <div v-if="product.last_quantity != null" class="text-caption text-grey-6 q-mt-xs">
            anterior: {{ formatQtd(product.last_quantity) }}
            {{ product.last_unit_type === 'caixa' ? 'cx' : 'un' }}
          </div>
        </div>

        <!-- Só no primeiro: ensina o gesto e some depois de rolar -->
        <div v-if="index === 0 && products.length > 1" class="dica-scroll">
          <q-icon name="keyboard_double_arrow_down" size="20px" />
          arraste para o próximo
        </div>
      </section>
    </div>

    <!-- ── Barra de envio ──────────────────────────────────────────── -->
    <div v-if="products.length" class="barra-envio row items-center q-gutter-sm">
      <div class="col text-caption text-grey-8">
        <div class="text-weight-bold text-body2">{{ preenchidos }} de {{ products.length }}</div>
        produtos preenchidos
      </div>
      <q-btn
        color="positive" size="lg" unelevated no-caps icon="cloud_upload"
        label="Enviar" class="col-auto"
        :disable="preenchidos === 0" :loading="enviando"
        @click="confirmarEnvio"
      />
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { mediaUrl } from '@/api/client'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({
  customerId: { type: String, required: true },
  visitType: { type: String, required: true },
})

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const UNIDADES = [
  { label: 'Caixa', value: 'caixa' },
  { label: 'Unidade', value: 'unidade' },
]

const products = ref([])
const form = reactive({})
const loading = ref(false)
const enviando = ref(false)

const preenchidos = computed(
  () => Object.values(form).filter((item) => item.quantity !== '').length
)

const imagem = (product) => mediaUrl(product.image_url)

const formatQtd = (value) =>
  Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

/** Grava no rascunho local a cada digitação — sair da tela não perde nada. */
function persistir(productId) {
  const item = form[productId]
  visita.setItem(props.customerId, props.visitType, productId, {
    quantity: item.quantity,
    unit_type: item.unit_type,
  })
}

function ajustar(productId, delta) {
  const atual = form[productId].quantity
  // Campo em branco + seta para baixo continua em branco: quem não contou ainda
  // não está declarando zero.
  if (atual === '' && delta < 0) return
  form[productId].quantity = String(Math.max(0, Number(atual || 0) + delta))
  persistir(productId)
}

function limpar(productId) {
  form[productId].quantity = ''
  persistir(productId)
}

function confirmarEnvio() {
  const faltando = products.value.length - preenchidos.value
  if (faltando === 0) return enviar()

  $q.dialog({
    title: 'Enviar contagem?',
    message: `${faltando} produto(s) ficaram em branco e não serão enviados.`,
    cancel: { label: 'Voltar', flat: true, noCaps: true },
    ok: { label: 'Enviar', color: 'positive', unelevated: true, noCaps: true },
  }).onOk(enviar)
}

async function enviar() {
  enviando.value = true
  const { sent } = await visita.submit(props.customerId, props.visitType)
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
    const sheet = await merchandisingApi.countSheet(props.customerId, props.visitType)

    // O formulário é preenchido ANTES da lista: o template lê `form[id]` em todo
    // painel, e uma renderização com a lista pronta e o formulário vazio quebra.
    // Recupera também o que já tinha sido digitado nesta contagem (mesmo aparelho).
    const draft = visita.getDraft(props.customerId, props.visitType)
    sheet.products.forEach((product) => {
      const gravado = draft.items[product.id]
      form[product.id] = {
        quantity: gravado ? String(gravado.quantity) : '',
        unit_type: gravado?.unit_type || 'unidade',
      }
    })

    products.value = sheet.products
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar os produtos',
    })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.contagem-page {
  overflow: hidden;
}

/* Altura fixa + snap: cada arraste para baixo encaixa o próximo produto.
   `svh` e não `dvh` para o painel não encolher quando o teclado abre. */
.painel-scroll {
  height: calc(100vh - 50px - 78px);
  height: calc(100svh - 50px - 78px);
  overflow-y: auto;
  scroll-snap-type: y mandatory;
  -webkit-overflow-scrolling: touch;
}

.painel {
  position: relative;
  display: flex;
  height: 100%;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  padding: 8px;
  gap: 8px;
}

/* ── Foto ─────────────────────────────────────────────────────────── */
/* Azul claro atrás da foto. As fotos do catálogo vêm com fundo branco chapado;
   `multiply` faz esse branco virar o próprio azul do card (multiplicar por 1 não
   muda nada), então o produto aparece recortado sobre o azul em vez de dentro de
   um quadrado branco. Azul claro e não o da marca justamente por causa do
   multiply: sobre um azul escuro o produto sairia quase preto.
   `isolation` prende a mesclagem ao card — sem ela o blend pega o fundo da
   página junto. */
.foto {
  position: relative;
  flex: 1 1 55%;
  min-width: 0;
  border-radius: 14px;
  overflow: hidden;
  isolation: isolate;
  background: #c5cae9;
}

.foto-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  mix-blend-mode: multiply;
}

.foto-vazia {
  height: 100%;
}

.contador {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0.75;
}

/* Nome sobre a foto: não rouba altura útil do card */
.foto-nome {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 24px 12px 10px;
  color: #fff;
  font-weight: 700;
  font-size: 1rem;
  line-height: 1.2;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.82), rgba(0, 0, 0, 0));
}

/* ── Quantidade ───────────────────────────────────────────────────── */
.controle {
  flex: 0 0 42%;
  max-width: 220px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 10px;
}

.unidade-toggle {
  width: 100%;
  border-radius: 10px;
  overflow: hidden;
}

.quantidade {
  width: 100%;
}

.quantidade :deep(input) {
  font-size: 2rem;
  padding: 4px 0;
}

/* Some as setinhas nativas do type=number: as do app são maiores e melhores */
.quantidade :deep(input::-webkit-outer-spin-button),
.quantidade :deep(input::-webkit-inner-spin-button) {
  -webkit-appearance: none;
  margin: 0;
}

.quantidade :deep(input[type='number']) {
  -moz-appearance: textfield;
}

.dica-scroll {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 6px;
  text-align: center;
  font-size: 0.7rem;
  color: rgba(0, 0, 0, 0.45);
  pointer-events: none;
}

/* ── Barra de envio ───────────────────────────────────────────────── */
.barra-envio {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 78px;
  padding: 0 12px calc(env(safe-area-inset-bottom, 0px)) 12px;
  background: #fff;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
  z-index: 10;
}

/* A foto mantém o azul nos dois temas — é ele que dá o contraste com a embalagem. */
.body--dark .controle,
.body--dark .barra-envio {
  background: #1e1e2e;
  border-color: rgba(255, 255, 255, 0.12);
}
</style>
