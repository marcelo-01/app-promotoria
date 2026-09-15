<!--
  A tela do vendedor: escolhe o cliente, vê quanto pedir de cada produto e
  ajusta, na própria linha, o fator de giro daquele produto naquela loja.

  O número grande é `venda × fator − estoque`, calculado no servidor sobre a
  última coleta completa (gôndola + estoque) do promotor. Embaixo de cada um
  vai a conta aberta — venda, estoque e o ciclo de onde a venda saiu —,
  porque o vendedor conhece a loja e precisa poder discordar do número antes
  de lançar o pedido. Mudou o fator, o servidor refaz a conta e a lista se
  reordena.

  Os produtos que a loja ainda cobre (sugestão zero) ficam numa seção
  recolhida embaixo: não são pedido, mas é olhando para eles que o vendedor
  decide subir o fator — e aí sobem para a lista.

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

    <div v-if="carregando && !sugestao" class="column items-center q-pa-xl">
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

      <template v-else>
        <div class="text-caption text-grey-7 q-px-xs q-mb-sm">
          Pedido = venda do ciclo × fator − estoque atual.
          O fator é seu: 1 repõe o que vendeu, 2 dobra a cobertura (até 3).
        </div>

        <q-banner v-if="!comSugestao.length" class="bg-green-1 text-green-10 rounded-borders q-mb-md">
          <template #avatar><q-icon name="check_circle" color="positive" /></template>
          Nada a pedir: o estoque da loja cobre a venda de todos os produtos.
        </q-banner>

        <div class="column q-gutter-sm">
          <ProdutoLinha
            v-for="item in comSugestao" :key="item.product_id"
            :item="item" @fator="salvarFator"
          />
        </div>

        <!-- Recolhida de propósito: não é pedido. Fica aqui para o vendedor
             ver o que a loja ainda cobre e, se discordar, subir o fator. -->
        <q-expansion-item
          v-if="semSugestao.length"
          dense expand-separator class="q-mt-md sem-sugestao rounded-borders"
          icon="inventory" :label="`Sem sugestão (${semSugestao.length})`"
          caption="O estoque cobre a venda. Suba o fator para pedir mesmo assim."
        >
          <div class="column q-gutter-sm q-pa-sm">
            <ProdutoLinha
              v-for="item in semSugestao" :key="item.product_id"
              :item="item" @fator="salvarFator"
            />
          </div>
        </q-expansion-item>
      </template>

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
import { merchandisingApi } from '@/api/merchandising'
import ProdutoLinha from '@/pages/vendedor/PedidoProdutoLinha.vue'

const $q = useQuasar()

const clientes = ref([])
const opcoes = ref([])
const clienteId = ref(null)
const carregandoClientes = ref(false)
const carregando = ref(false)
const sugestao = ref(null)

const comSugestao = computed(() =>
  (sugestao.value?.items || []).filter((i) => i.suggested_units > 0)
)
const semSugestao = computed(() =>
  (sugestao.value?.items || []).filter((i) => i.suggested_units === 0)
)

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
    const termo = (texto || '').trim().toLowerCase()
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

/**
 * Grava o fator e pede a lista de novo: quem refaz a conta é o servidor, e a
 * ordem pode mudar — um produto que estava em "sem sugestão" pode subir.
 * A linha avisa por `done(ok)` para acender o visto ou voltar ao valor antigo.
 */
async function salvarFator({ item, fator, done }) {
  try {
    await merchandisingApi.setTurnoverFactor(clienteId.value, item.product_id, fator)
    done(true)
    await carregarSugestao(clienteId.value)
  } catch (error) {
    done(false)
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Não foi possível salvar o fator',
    })
  }
}

watch(clienteId, carregarSugestao)

onMounted(carregarClientes)
</script>

<style scoped>
.pedidos-page {
  min-height: 100%;
}

.sem-sugestao {
  border: 1px solid #e0e4ea;
  background: #fff;
}

.body--dark .sem-sugestao {
  border-color: rgba(255, 255, 255, 0.15);
  background: #1e1e2e;
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
