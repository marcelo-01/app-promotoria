<!--
  Histórico de envios do promotor, do mais recente para o mais antigo.

  Serve para duas perguntas: "o que eu já mandei?" e "dá para arrumar aquele
  número que digitei errado?". Por isso cada envio é clicável — abre a tela de
  contagem de novo, só com os produtos daquele envio. Envio já baixado em
  planilha pelo administrador não abre: mudar o número aqui faria o app
  discordar do que ele tem na mão.

  Os envios ficam agrupados por dia porque é assim que o promotor procura ("foi
  na terça"), e não por nome de cliente.
-->
<template>
  <q-page class="q-pa-md">
    <q-banner
      v-if="visita.pendingCount" class="bg-warning text-dark rounded-borders q-mb-md"
    >
      <template #avatar><q-icon name="cloud_off" /></template>
      {{ visita.pendingCount }} contagem(ns) aguardando envio neste aparelho.
      <template #action>
        <q-btn flat dense no-caps label="Enviar agora" :loading="visita.sending" @click="enviarAgora" />
      </template>
    </q-banner>

    <div class="row items-center q-mb-sm">
      <div class="col text-subtitle2 text-grey-7">Enviadas</div>
      <q-btn
        flat dense round icon="refresh" color="grey-7" aria-label="Atualizar"
        :loading="carregando" @click="carregar()"
      />
    </div>

    <div v-if="carregando && !enviadas.length" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner
      v-else-if="!enviadas.length"
      class="bg-grey-2 text-grey-8 rounded-borders"
    >
      <template #avatar><q-icon name="cloud_done" color="grey-6" /></template>
      Nenhuma contagem enviada ainda.
    </q-banner>

    <template v-else>
      <div v-for="grupo in grupos" :key="grupo.dia" class="q-mb-md">
        <div class="text-caption text-weight-bold text-grey-7 q-mb-xs">
          {{ grupo.titulo }}
        </div>

        <q-list separator bordered class="rounded-borders bg-white">
          <q-item v-for="v in grupo.envios" :key="v.id" clickable @click="abrir(v)">
            <q-item-section>
              <q-item-label>
                {{ v.customer_name }}
                <q-chip dense square outline size="sm"
                        :color="v.visit_type === 'gondola' ? 'primary' : 'teal-8'">
                  {{ v.visit_type === 'gondola' ? 'Gôndola' : 'Estoque' }}
                </q-chip>
              </q-item-label>
              <q-item-label caption>
                {{ formatHora(v.visited_at) }} · {{ v.items_count }} itens
                <span v-if="corrigido(v)"> · corrigida</span>
              </q-item-label>
            </q-item-section>

            <q-item-section side>
              <div class="row items-center no-wrap">
                <q-icon
                  size="22px"
                  :name="v.status === 'exported' ? 'task_alt' : 'check_circle'"
                  :color="v.status === 'exported' ? 'positive' : 'primary'"
                >
                  <q-tooltip>
                    {{ v.status === 'exported' ? 'Já processada pelo administrador' : 'Recebida pelo servidor' }}
                  </q-tooltip>
                </q-icon>
                <q-icon
                  size="20px" class="q-ml-xs" color="grey-6"
                  :name="v.status === 'exported' ? 'lock' : 'chevron_right'"
                />
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </div>

      <div v-if="temMais" class="row justify-center q-mt-md">
        <q-btn
          flat no-caps color="primary" label="Carregar mais"
          :loading="carregando" @click="carregar({ append: true })"
        />
      </div>
    </template>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { diaLocal, useVisitaStore } from '@/stores/visita'
import { useOfflineQueue } from '@/composables/useOfflineQueue'

const PAGINA = 30

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()
const { tryFlush } = useOfflineQueue()

const enviadas = ref([])
const total = ref(0)
const carregando = ref(false)

const temMais = computed(() => enviadas.value.length < total.value)

const dataDoEnvio = (v) => v.visited_at || v.submitted_at || v.created_at

const formatHora = (iso) =>
  iso ? new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '—'

/** Itens trocados depois do envio — o backend carimba `updated_at` ao corrigir.
 *  A exportação também carimba `updated_at`, por isso a marca não vale para
 *  contagem já processada — que, de todo modo, não pode mais ser corrigida. */
const corrigido = (v) =>
  v.status !== 'exported' &&
  Boolean(v.submitted_at && v.updated_at) &&
  new Date(v.updated_at) - new Date(v.submitted_at) > 1000

function tituloDia(dia) {
  if (dia === diaLocal()) return 'Hoje'
  if (dia === diaLocal(Date.now() - 86400000)) return 'Ontem'
  const [ano, mes, d] = dia.split('-')
  return `${d}/${mes}/${ano}`
}

/** A lista já vem do servidor em ordem decrescente: basta quebrar por dia. */
const grupos = computed(() => {
  const porDia = new Map()
  enviadas.value.forEach((v) => {
    const dia = diaLocal(dataDoEnvio(v))
    if (!porDia.has(dia)) porDia.set(dia, { dia, titulo: tituloDia(dia), envios: [] })
    porDia.get(dia).envios.push(v)
  })
  return [...porDia.values()]
})

async function carregar({ append = false } = {}) {
  carregando.value = true
  try {
    const { items, total: totalServidor } = await merchandisingApi.myVisits({
      limit: PAGINA,
      offset: append ? enviadas.value.length : 0,
    })
    enviadas.value = append ? [...enviadas.value, ...items] : items
    total.value = totalServidor
  } catch {
    // Offline: a lista fica como está; o que importa aqui é a fila local
  } finally {
    carregando.value = false
  }
}

function abrir(v) {
  if (v.status === 'exported') {
    $q.notify({
      type: 'info',
      message: 'Esta contagem já foi processada pelo administrador e não pode mais ser alterada.',
      position: 'top',
    })
    return
  }
  router.push({
    name: 'PromotorEdicao',
    params: { visitId: v.id },
    query: { c: v.customer_name },
  })
}

/** Após subir a fila, recarrega para o item aparecer em "Enviadas". */
async function enviarAgora() {
  await tryFlush()
  await carregar()
}

onMounted(carregar)
</script>
