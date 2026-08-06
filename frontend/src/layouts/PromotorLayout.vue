<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-btn
          v-if="canGoBack"
          flat dense round icon="arrow_back"
          aria-label="Voltar"
          @click="$router.back()"
        />
        <q-toolbar-title class="text-subtitle1 text-weight-medium ellipsis">
          {{ title }}
        </q-toolbar-title>

        <!-- Estado da conexão: o promotor precisa saber, sem precisar perguntar -->
        <q-chip
          v-if="!online"
          dense square color="warning" text-color="dark" icon="cloud_off"
          class="q-mr-sm"
        >
          Offline
        </q-chip>

        <q-btn flat dense round icon="more_vert" aria-label="Menu">
          <q-menu>
            <q-list style="min-width: 180px">
              <q-item clickable v-close-popup @click="sync">
                <q-item-section avatar><q-icon name="sync" /></q-item-section>
                <q-item-section>Sincronizar agora</q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable v-close-popup @click="logout">
                <q-item-section avatar><q-icon name="logout" /></q-item-section>
                <q-item-section>Sair</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>

    <!-- Durante a contagem as abas somem: a tela é um produto por vez e a barra
         de envio da própria página ocupa esse espaço. -->
    <q-footer v-if="!contando" elevated class="bg-white text-primary">
      <q-tabs
        v-model="tab" dense no-caps active-color="primary"
        indicator-color="primary" class="text-grey-7"
      >
        <q-tab name="clientes" icon="store" label="Clientes" :to="{ name: 'PromotorClientes' }" />
        <q-tab name="envios" icon="cloud_upload" :to="{ name: 'PromotorEnvios' }">
          <q-badge v-if="visita.pendingCount" color="negative" floating>
            {{ visita.pendingCount }}
          </q-badge>
          <div class="q-tab__label">Envios</div>
        </q-tab>
      </q-tabs>
    </q-footer>
  </q-layout>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useAuthStore } from '@/stores/auth'
import { useVisitaStore } from '@/stores/visita'
import { useOfflineQueue } from '@/composables/useOfflineQueue'

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const auth = useAuthStore()
const visita = useVisitaStore()
const { online } = useOfflineQueue()

const tab = ref('clientes')

// Mantém a aba destacada coerente com a rota (inclusive ao voltar pelo navegador)
watch(
  () => route.name,
  (name) => {
    tab.value = name === 'PromotorEnvios' ? 'envios' : 'clientes'
  },
  { immediate: true }
)

const canGoBack = computed(() => route.name !== 'PromotorClientes')
const contando = computed(() => route.name === 'PromotorContagem')

const title = computed(() => {
  if (contando.value) {
    const lugar = route.params.visitType === 'gondola' ? 'Gôndola' : 'Estoque'
    // O nome do cliente vem na query só para o cabeçalho — abrir a URL direto
    // (sem passar pela lista) continua funcionando, só sem o nome.
    return route.query.c ? `${route.query.c} · ${lugar}` : lugar
  }
  return route.name === 'PromotorEnvios' ? 'Envios' : 'Meus Clientes'
})

async function sync() {
  const { sent, failed } = await visita.flushQueue()
  $q.notify({
    type: failed ? 'warning' : 'positive',
    message: failed
      ? `${sent} enviada(s), ${failed} pendente(s).`
      : sent ? `${sent} contagem(ns) enviada(s).` : 'Nada pendente.',
    position: 'top',
  })
}

function logout() {
  if (visita.pendingCount > 0) {
    $q.dialog({
      title: 'Há contagens não enviadas',
      message: `${visita.pendingCount} contagem(ns) ainda não subiram. Se sair agora, elas continuam salvas neste aparelho. Deseja sair?`,
      cancel: true,
      persistent: true,
    }).onOk(() => {
      auth.logout()
      router.push('/login')
    })
    return
  }
  auth.logout()
  router.push('/login')
}
</script>
