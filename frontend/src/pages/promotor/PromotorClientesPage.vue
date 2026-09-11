<!--
  Tela inicial do promotor: um card grande por cliente, com os dois destinos de
  contagem lado a lado. Card grande e botão grande porque isso é usado em pé,
  no corredor do mercado, com uma mão só.

  O visto verde em cima do botão responde à única pergunta que o promotor faz
  ao chegar na loja: "já contei aqui hoje?". Ele aparece quando a contagem
  daquele tipo foi enviada hoje e some sozinho na virada do dia — não há nada
  agendado às 00:00, a marca é comparada com a data de hoje toda vez.
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

        <!-- Contagem retida: o promotor fechou os dois lados, mas há produto
             esperando data de vencimento. Enquanto isto estiver aqui, nada
             daquele cliente subiu — e é por este botão que ele volta. -->
        <q-card-section v-if="vencimentoPendente(customer.id)" class="q-pt-none q-pb-sm">
          <q-btn
            unelevated no-caps class="full-width faixa-vencimento"
            color="orange-9" icon="schedule" align="left"
            @click="abrirVencimento(customer)"
          >
            <div class="column items-start q-ml-sm">
              <div class="text-weight-bold">Falta o vencimento</div>
              <div class="text-caption">
                A contagem deste cliente não foi enviada. Toque para terminar.
              </div>
            </div>
          </q-btn>
        </q-card-section>

        <q-card-section class="row q-col-gutter-sm q-pt-none">
          <div v-for="tipo in TIPOS" :key="tipo.value" class="col-6">
            <q-btn
              stack unelevated no-caps
              class="full-width acao-btn"
              :class="{ 'acao-btn--feita': concluido(customer, tipo.value) }"
              :color="tipo.color" :icon="tipo.icon"
              @click="abrir(customer, tipo.value)"
            >
              <div class="text-subtitle2 text-weight-bold q-mt-xs">{{ tipo.label }}</div>

              <!-- Contagem enviada hoje: o visto. Ainda na fila: a nuvem. -->
              <q-badge
                v-if="concluido(customer, tipo.value)"
                floating rounded class="marca-feita"
                :color="visita.aguardandoEnvio(customer.id, tipo.value) ? 'warning' : 'positive'"
                :text-color="visita.aguardandoEnvio(customer.id, tipo.value) ? 'dark' : 'white'"
              >
                <q-icon
                  size="18px"
                  :name="visita.aguardandoEnvio(customer.id, tipo.value)
                    ? 'cloud_upload' : 'check'"
                />
              </q-badge>

              <q-badge
                v-else-if="pendente(customer.id, tipo.value)"
                color="warning" text-color="dark" floating
              >
                {{ pendente(customer.id, tipo.value) }}
              </q-badge>
            </q-btn>
            <div class="text-caption text-center q-mt-xs" :class="legenda(customer, tipo.value).cor">
              {{ legenda(customer, tipo.value).texto }}
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
import { diaLocal, useVisitaStore } from '@/stores/visita'

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

/** Coleta de vencimento em aberto hoje neste cliente. */
const vencimentoPendente = (customerId) => Boolean(visita.vencimentoPendente(customerId))

function abrirVencimento(customer) {
  router.push({
    name: 'PromotorVencimento',
    params: { customerId: customer.id },
    query: { c: customer.name },
  })
}

const ultimaContagem = (customer, tipo) =>
  tipo === 'gondola' ? customer.last_gondola_at : customer.last_estoque_at

/**
 * Contado hoje? Vale a marca deste aparelho (funciona offline, aparece na hora)
 * ou a data que o servidor devolveu — que cobre a contagem feita em outro
 * aparelho ou antes de reinstalar o app.
 */
function concluido(customer, tipo) {
  if (visita.concluidaHoje(customer.id, tipo)) return true
  const iso = ultimaContagem(customer, tipo)
  return Boolean(iso) && diaLocal(iso) === diaLocal()
}

function legenda(customer, tipo) {
  if (visita.aguardandoEnvio(customer.id, tipo)) {
    return { texto: 'contado — aguardando envio', cor: 'text-orange-9' }
  }
  if (concluido(customer, tipo)) {
    return { texto: 'contado hoje', cor: 'text-positive text-weight-bold' }
  }
  const iso = ultimaContagem(customer, tipo)
  return {
    texto: iso ? new Date(iso).toLocaleDateString('pt-BR') : 'nunca contado',
    cor: 'text-grey-7',
  }
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

/* Já contado hoje: o botão continua clicável (dá para recontar), mas recua
   visualmente para o que falta contar saltar aos olhos. */
.acao-btn--feita {
  opacity: 0.62;
}

/* Alvo largo e de texto à esquerda: é um aviso que se lê, não um ícone que se
   reconhece. */
.faixa-vencimento {
  border-radius: 12px;
  padding: 8px 12px;
  text-align: left;
}

.marca-feita {
  padding: 4px;
  border: 2px solid #fff;
}

.marca-feita :deep(.q-icon) {
  font-size: 18px;
}
</style>
