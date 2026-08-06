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

    <div class="text-subtitle2 text-grey-7 q-mb-sm">Enviadas</div>

    <div v-if="carregando" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner
      v-else-if="!enviadas.length"
      class="bg-grey-2 text-grey-8 rounded-borders"
    >
      <template #avatar><q-icon name="cloud_done" color="grey-6" /></template>
      Nenhuma contagem enviada ainda.
    </q-banner>

    <q-list v-else separator class="rounded-borders bg-white">
      <q-item v-for="v in enviadas" :key="v.id">
        <q-item-section>
          <q-item-label>
            {{ v.customer_name }}
            <q-chip dense square outline size="sm"
                    :color="v.visit_type === 'gondola' ? 'primary' : 'teal-8'">
              {{ v.visit_type === 'gondola' ? 'Gôndola' : 'Estoque' }}
            </q-chip>
          </q-item-label>
          <q-item-label caption>
            {{ formatData(v.visited_at) }} · {{ v.items_count }} itens
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-icon
            :name="v.status === 'exported' ? 'task_alt' : 'check_circle'"
            :color="v.status === 'exported' ? 'positive' : 'primary'"
          >
            <q-tooltip>
              {{ v.status === 'exported' ? 'Já processada pelo administrador' : 'Recebida pelo servidor' }}
            </q-tooltip>
          </q-icon>
        </q-item-section>
      </q-item>
    </q-list>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'
import { useOfflineQueue } from '@/composables/useOfflineQueue'

const visita = useVisitaStore()
const { tryFlush } = useOfflineQueue()
const enviadas = ref([])
const carregando = ref(false)

const formatData = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR') : '—')

async function carregar() {
  carregando.value = true
  try {
    const { items } = await merchandisingApi.myVisits({ limit: 50 })
    enviadas.value = items
  } catch {
    // Offline: a lista fica como está; o que importa aqui é a fila local
  } finally {
    carregando.value = false
  }
}

/** Após subir a fila, recarrega para o item aparecer em "Enviadas". */
async function enviarAgora() {
  await tryFlush()
  await carregar()
}

onMounted(carregar)
</script>
