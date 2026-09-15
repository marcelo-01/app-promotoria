<!--
  A tela do vendedor: escolhe o cliente, vê quanto pedir de cada produto.

  O número grande é `venda × fator − estoque`, calculado no servidor sobre a
  última coleta completa (gôndola + estoque) do promotor. Embaixo de cada um
  vai a conta aberta, porque o vendedor conhece a loja e precisa poder
  discordar do número antes de lançar o pedido.

  A tela zera sozinha toda semana: coleta anterior ao domingo mais recente vem
  do servidor com `stale` e a lista vazia — o que aparece aqui é o aviso e a
  data, não um pedido velho. Não há nada agendado; é comparação de data.
-->
<template>
  <q-page class="q-pa-md column pedidos-page">
    <q-select
      v-model="clienteId" :options="opcoes" outlined dense emit-value map-options
      use-input input-debounce="0" fill-input hide-selected
      label="Cliente" class="q-mb-md bg-white"
      :loading="carregandoClientes"
      @filter="filtrar"
    >
      <template #prepend><q-icon name="store" /></template>
      <template #no-option>
        <q-item><q-item-section class="text-grey-7">Nenhum cliente</q-item-section></q-item>
      </template>
    </q-select>

    <div v-if="carregando" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner v-else-if="!clienteId && !carregandoClientes" class="bg-grey-2 text-grey-8 rounded-borders">
      <template #avatar><q-icon name="touch_app" color="grey-6" /></template>
      <span v-if="clientes.length">Escolha um cliente para ver o pedido sugerido.</span>
      <span v-else>Nenhum cliente vinculado a você. Fale com o administrador.</span>
    </q-banner>

    <template v-else-if="sugestao">
      <!-- Coleta da semana passada: o servidor já mandou a lista vazia. O aviso
           diz por quê, para o vendedor não achar que "não tem nada a pedir". -->
      <q-banner v-if="sugestao.stale" class="bg-orange-1 text-orange-10 rounded-borders q-mb-md">
        <template #avatar><q-icon name="event_busy" color="orange-9" /></template>
        <div class="text-weight-bold">Sugestões zeradas</div>
        A última coleta foi em {{ dataBr(sugestao.last_collection_day) }}, semana passada.
        O pedido volta a aparecer quando o promotor contar a loja de novo.
      </q-banner>

      <q-banner v-else-if="!sugestao.last_collection_day" class="bg-grey-2 text-grey-8 rounded-borders q-mb-md">
        <template #avatar><q-icon name="hourglass_empty" color="grey-6" /></template>
        Este cliente ainda não tem duas coletas completas (gôndola e estoque).
        Sem duas, não há venda para calcular.
      </q-banner>

      <q-banner v-else-if="!sugestao.items.length" class="bg-green-1 text-green-10 rounded-borders q-mb-md">
        <template #avatar><q-icon name="check_circle" color="positive" /></template>
        Nada a pedir: o estoque da loja cobre a venda com o fator {{ fatorBr }}.
      </q-banner>

      <div v-else class="column q-gutter-sm">
        <div class="text-caption text-grey-7 q-px-xs">
          Venda dos últimos {{ sugestao.cycle_days }} dias × fator {{ fatorBr }}, menos o
          estoque atual. {{ sugestao.items.length }} produto(s).
        </div>

        <q-card v-for="item in sugestao.items" :key="item.product_id" flat bordered class="item-card">
          <q-card-section class="row items-center no-wrap q-py-sm">
            <q-avatar square size="56px" class="q-mr-md foto">
              <img v-if="mediaUrl(item.image_url)" :src="mediaUrl(item.image_url)" :alt="item.product_name">
              <q-icon v-else name="inventory_2" color="grey-5" size="32px" />
            </q-avatar>

            <div class="col">
              <div class="text-subtitle1 text-weight-bold ellipsis-2-lines">
                {{ item.product_name || 'Produto' }}
              </div>
              <div class="text-caption text-grey-7">
                vendeu {{ qtd(item.sold) }} · estoque {{ qtd(item.current_stock) }}
              </div>
            </div>

            <div class="column items-end q-ml-sm">
              <div class="text-h5 text-weight-bold text-primary no-wrap">
                {{ item.suggested_units }} <span class="text-subtitle2">un</span>
              </div>
              <div v-if="item.suggested_boxes" class="text-caption text-grey-7 no-wrap">
                ≈ {{ qtd(item.suggested_boxes) }} cx
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <!-- Sempre visível quando há cliente: é a resposta à pergunta "esses
           números são de quando?" -->
      <div class="rodape-coleta text-center q-mt-md">
        <q-icon name="event_available" size="18px" class="q-mr-xs" />
        Última coleta de estoque:
        <span class="text-weight-bold">
          {{ sugestao.last_collection_day ? dataBr(sugestao.last_collection_day) : 'nunca' }}
        </span>
      </div>
    </template>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { mediaUrl } from '@/api/client'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const clientes = ref([])
const opcoes = ref([])
const clienteId = ref(null)
const carregandoClientes = ref(false)
const carregando = ref(false)
const sugestao = ref(null)

const fatorBr = computed(() =>
  sugestao.value ? Number(sugestao.value.turnover_factor).toLocaleString('pt-BR') : ''
)

/** Números vêm como string decimal; mostra sem casas quando são inteiros. */
const qtd = (valor) => Number(valor).toLocaleString('pt-BR', { maximumFractionDigits: 1 })

/** 'AAAA-MM-DD' → 'DD/MM/AAAA' sem passar por Date (que leria como UTC). */
const dataBr = (dia) => dia.split('-').reverse().join('/')

async function carregarClientes() {
  carregandoClientes.value = true
  try {
    clientes.value = await merchandisingApi.myCustomers()
    opcoes.value = todasOpcoes()
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar clientes',
    })
  } finally {
    carregandoClientes.value = false
  }
}

const todasOpcoes = () => clientes.value.map((c) => ({ label: c.name, value: c.id }))

function filtrar(texto, update) {
  update(() => {
    const termo = texto.trim().toLowerCase()
    opcoes.value = termo
      ? todasOpcoes().filter((o) => o.label.toLowerCase().includes(termo))
      : todasOpcoes()
  })
}

async function carregarSugestao(id) {
  if (!id) {
    sugestao.value = null
    return
  }
  carregando.value = true
  try {
    sugestao.value = await merchandisingApi.orderSuggestion(id)
  } catch (error) {
    sugestao.value = null
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao calcular o pedido sugerido',
    })
  } finally {
    carregando.value = false
  }
}

watch(clienteId, carregarSugestao)

onMounted(carregarClientes)
</script>

<style scoped>
.pedidos-page {
  min-height: 100%;
}

.item-card {
  border-radius: 12px;
}

.foto {
  border-radius: 8px;
  background: #f0f2f5;
}

.foto img {
  object-fit: cover;
}

.rodape-coleta {
  color: #5f6b7a;
  font-size: 0.9rem;
  padding: 10px;
  border-top: 1px dashed #cfd6df;
}

.body--dark .rodape-coleta {
  color: rgba(255, 255, 255, 0.7);
  border-top-color: rgba(255, 255, 255, 0.2);
}
</style>
