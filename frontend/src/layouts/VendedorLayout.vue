<!--
  Casca do vendedor: o mesmo desenho do promotor (celular, uma mão), sem a
  parte que não lhe diz respeito — não há fila offline nem sincronização,
  porque o vendedor só lê o que o promotor contou e grava um número por
  cliente. Duas abas: o pedido sugerido e o fator de giro.
-->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-toolbar-title class="text-subtitle1 text-weight-medium ellipsis">
          {{ title }}
        </q-toolbar-title>

        <q-btn flat dense round icon="more_vert" aria-label="Menu">
          <q-menu>
            <q-list style="min-width: 180px">
              <q-item clickable v-close-popup @click="dialogSenha = true">
                <q-item-section avatar><q-icon name="lock_reset" /></q-item-section>
                <q-item-section>Trocar minha senha</q-item-section>
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

    <!-- QRouteTab, não QTab: é ele quem navega (ver PromotorLayout). `exact` na
         aba de pedidos porque /vendedor é prefixo de /vendedor/giro. -->
    <q-footer elevated class="bg-white text-primary">
      <q-tabs dense no-caps active-color="primary" indicator-color="primary" class="text-grey-7">
        <q-route-tab
          name="pedidos" icon="shopping_cart" label="Pedidos" exact
          :to="{ name: 'VendedorPedidos' }"
        />
        <q-route-tab
          name="giro" icon="tune" label="Fator de giro"
          :to="{ name: 'VendedorGiro' }"
        />
      </q-tabs>
    </q-footer>

    <TrocarSenhaDialog v-model="dialogSenha" />
  </q-layout>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import TrocarSenhaDialog from '@/components/TrocarSenhaDialog.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const dialogSenha = ref(false)

const title = computed(() =>
  route.name === 'VendedorGiro' ? 'Fator de giro' : 'Pedido sugerido'
)

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
