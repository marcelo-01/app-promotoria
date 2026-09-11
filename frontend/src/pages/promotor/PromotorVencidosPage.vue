<!--
  Vencido retirado da loja.

  O promotor tira da gôndola o que passou da data e registra aqui. Parece um
  detalhe operacional, e é a informação que conserta o cálculo inteiro: sem ela,
  mercadoria que foi para o lixo é lida como venda — o estoque caiu e o sistema
  não tem como saber por quê.

  O efeito disso é perverso e trabalha contra a coleta de vencimento: a loja
  parece girar mais rápido, "dias para escoar" encolhe, e o aviso de "não vai dar
  tempo de vender" deixa de disparar justamente no produto que está vencendo.
  Quanto mais mercadoria vencia, menos o sistema avisava.

  A devolução do ERP não resolve: ela só é lançada quando a mercadoria volta
  fisicamente ao estoque, dias depois. Quem vê primeiro é quem está na loja.

  A ORDEM IMPORTA: retirar e registrar aqui ANTES de contar. Assim a contagem do
  dia já é o que sobrou, e a retirada não entra duas vezes na conta.
-->
<template>
  <q-page class="vencidos-page">
    <div class="conteudo">
      <q-banner class="aviso-card q-mb-md">
        <template #avatar><q-icon name="delete_sweep" color="red-8" size="24px" /></template>
        <div class="text-weight-bold">Retire antes de contar</div>
        <div class="text-caption text-grey-7">
          Registre aqui o que você tirou da loja por estar vencido, e só depois
          faça a contagem — assim o que você contar já é o que sobrou.
        </div>
      </q-banner>

      <div v-if="carregando" class="column items-center q-pa-xl">
        <q-spinner-dots size="36px" color="primary" />
      </div>

      <template v-else>
        <!-- ── O que já subiu hoje ──────────────────────────────────────── -->
        <q-card v-if="enviadas.length" flat bordered class="q-mb-md">
          <q-card-section class="q-pb-xs">
            <div class="text-subtitle2 text-weight-bold">Já registrado hoje</div>
          </q-card-section>
          <q-list separator dense>
            <q-item v-for="linha in enviadas" :key="linha.id">
              <q-item-section>
                <q-item-label>{{ linha.product_name }}</q-item-label>
                <q-item-label caption>vencia {{ formatDia(linha.expires_at) }}</q-item-label>
              </q-item-section>
              <q-item-section side class="text-weight-bold text-red-8">
                {{ formatQtd(linha.quantity) }} un
              </q-item-section>
            </q-item>
          </q-list>
        </q-card>

        <!-- ── O que está sendo digitado ────────────────────────────────── -->
        <q-card v-for="(linha, i) in linhas" :key="i" flat bordered class="linha-card q-mb-sm">
          <q-card-section class="q-pb-none">
            <!-- Sem busca por digitação de propósito: com `use-input` o campo
                 vira caixa de texto e a lista só aparece depois de digitar algo
                 — o promotor toca e não vê nada acontecer. Aqui o toque abre a
                 lista, que é o mix do cliente e não o catálogo inteiro. -->
            <q-select
              v-model="linha.product_id" :options="opcoes" outlined dense
              emit-value map-options options-dense
              option-value="value" option-label="label"
              label="Produto" :error="tocou && !linha.product_id" hide-bottom-space
              @update:model-value="gravar"
            >
              <template #prepend><q-icon name="inventory_2" /></template>
            </q-select>
          </q-card-section>

          <q-card-section class="row items-center no-wrap q-gutter-xs">
            <q-input
              v-model="linha.texto" outlined dense mask="##/##/####"
              placeholder="dd/mm/aaaa" label="Vencia em" class="col"
              :error="tocou && !isoDe(linha.texto)" hide-bottom-space
              @update:model-value="gravar"
            >
              <template #append>
                <q-icon name="event" class="cursor-pointer" size="20px">
                  <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                    <q-date
                      :model-value="isoDe(linha.texto)" mask="YYYY-MM-DD" minimal
                      @update:model-value="(iso) => escolherData(i, iso)"
                    />
                  </q-popup-proxy>
                </q-icon>
              </template>
            </q-input>

            <q-input
              v-if="caixaDe(linha) > 1"
              v-model="linha.boxes" outlined dense type="number" inputmode="numeric"
              min="0" step="1" label="cx" class="col-auto campo-qtd"
              input-class="text-center text-weight-bold" hide-bottom-space
              @update:model-value="gravar"
            />
            <q-input
              v-model="linha.units" outlined dense type="number" inputmode="numeric"
              min="0" step="1" label="un" class="col-auto campo-qtd"
              input-class="text-center text-weight-bold" hide-bottom-space
              @update:model-value="gravar"
            />

            <q-btn
              flat dense round icon="close" color="grey-6" class="col-auto"
              aria-label="Remover esta linha" @click="removerLinha(i)"
            />
          </q-card-section>

          <q-card-section v-if="totalDaLinha(linha)" class="q-pt-none text-caption text-grey-7">
            {{ formatQtd(totalDaLinha(linha)) }} unidades no total
          </q-card-section>
        </q-card>

        <q-banner v-if="!linhas.length && !enviadas.length" class="bg-grey-2 rounded-borders">
          <template #avatar><q-icon name="check_circle" color="positive" /></template>
          Nada retirado hoje neste cliente. Se encontrar produto vencido, toque
          em adicionar.
        </q-banner>

        <q-btn
          flat no-caps icon="add" color="primary" class="q-mt-sm"
          label="Adicionar produto retirado" @click="adicionarLinha"
        />
      </template>
    </div>

    <!-- ── Barra de envio ──────────────────────────────────────────── -->
    <div class="barra-envio row items-center q-gutter-sm">
      <div class="col text-caption text-grey-8">
        <div class="text-weight-bold text-body2">{{ formatQtd(totalGeral) }} un</div>
        a registrar
      </div>
      <q-btn
        size="lg" unelevated no-caps class="col-auto" color="negative"
        icon="delete_sweep" label="Registrar"
        :disable="!linhas.length" :loading="enviando"
        @click="enviar"
      />
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({
  customerId: { type: String, default: '' },
})

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const produtos = ref([])
const opcoes = ref([])
const enviadas = ref([])
const linhas = ref([])
const carregando = ref(false)
const enviando = ref(false)
// Só marca campo vazio em vermelho depois da primeira tentativa de envio —
// linha recém-criada nasce em branco e não é erro.
const tocou = ref(false)

const formatQtd = (v) =>
  Number(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

const formatDia = (iso) => {
  const [ano, mes, dia] = String(iso).split('-')
  return dia ? `${dia}/${mes}/${ano}` : iso
}

/** 'dd/mm/aaaa' → 'aaaa-mm-dd', ou null se a data não existe no calendário. */
function isoDe(texto) {
  const partes = String(texto || '').split('/')
  if (partes.length !== 3 || partes[2].length !== 4) return null

  const [dia, mes, ano] = partes.map(Number)
  if (!dia || !mes || !ano) return null

  const data = new Date(ano, mes - 1, dia)
  if (data.getFullYear() !== ano || data.getMonth() !== mes - 1 || data.getDate() !== dia) {
    return null
  }
  return `${ano}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`
}

const caixaDe = (linha) =>
  Number(produtos.value.find((p) => p.id === linha.product_id)?.package_size) || 1

const totalDaLinha = (linha) =>
  Number(linha.boxes || 0) * caixaDe(linha) + Number(linha.units || 0)

const totalGeral = computed(() =>
  linhas.value.reduce((soma, linha) => soma + totalDaLinha(linha), 0)
)

// ── Edição ──────────────────────────────────────────────────────────────

function adicionarLinha() {
  linhas.value.push({ product_id: null, texto: '', boxes: '', units: '' })
  gravar()
}

function removerLinha(i) {
  linhas.value.splice(i, 1)
  gravar()
}

function escolherData(i, iso) {
  if (!iso) return
  linhas.value[i].texto = formatDia(iso)
  gravar()
}

/** Cada tecla vai para o localStorage: o promotor pode sair da tela para contar
 *  e voltar, e o sinal do supermercado cai a toda hora. */
const gravar = () => visita.setLinhasRetirada(props.customerId, linhas.value)

// ── Envio ───────────────────────────────────────────────────────────────

async function enviar() {
  tocou.value = true

  const incompleta = linhas.value.some(
    (linha) => !linha.product_id || !isoDe(linha.texto) || totalDaLinha(linha) <= 0
  )
  if (incompleta) {
    return $q.notify({
      type: 'warning',
      message: 'Cada linha precisa de produto, data e quantidade.',
      position: 'top',
    })
  }

  const items = linhas.value.map((linha) => ({
    product_id: linha.product_id,
    expires_at: isoDe(linha.texto),
    boxes: Number(linha.boxes || 0),
    units: Number(linha.units || 0),
  }))

  enviando.value = true
  const { sent } = await visita.submitRetirada(props.customerId, items)
  enviando.value = false

  $q.notify({
    type: sent ? 'positive' : 'warning',
    message: sent
      ? 'Retirada registrada.'
      : 'Sem conexão. A retirada foi salva e será enviada automaticamente.',
    position: 'top',
    timeout: 4000,
  })
  router.push({ name: 'PromotorClientes' })
}

// ── Carga ───────────────────────────────────────────────────────────────

onMounted(async () => {
  carregando.value = true
  // O rascunho vem primeiro: se a rede falhar, a tela ainda abre com o que já
  // estava digitado neste aparelho.
  linhas.value = (visita.retiradaPendente(props.customerId)?.linhas || []).map(
    (linha) => ({ ...linha })
  )

  try {
    // A folha da gôndola serve só como catálogo do mix deste cliente — a
    // retirada não distingue gôndola de estoque, é da loja inteira.
    const [folha, jaFeitas] = await Promise.all([
      merchandisingApi.countSheet(props.customerId, 'gondola'),
      merchandisingApi.removals(props.customerId),
    ])
    produtos.value = folha.products
    opcoes.value = folha.products.map((p) => ({ value: p.id, label: p.name }))
    enviadas.value = jaFeitas
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar os produtos',
    })
  } finally {
    carregando.value = false
  }
})
</script>

<style scoped>
.conteudo {
  padding: 12px;
  padding-bottom: 90px;
}

.aviso-card {
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-left: 4px solid #c62828;
}

.linha-card {
  border-radius: 14px;
}

.campo-qtd {
  width: 68px;
}

.campo-qtd :deep(input::-webkit-outer-spin-button),
.campo-qtd :deep(input::-webkit-inner-spin-button) {
  -webkit-appearance: none;
  margin: 0;
}

.campo-qtd :deep(input[type='number']) {
  -moz-appearance: textfield;
}

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

.body--dark .aviso-card,
.body--dark .barra-envio {
  background: #1e1e2e;
  border-color: rgba(255, 255, 255, 0.12);
}

.body--dark .aviso-card {
  border-left-color: #c62828;
}
</style>
