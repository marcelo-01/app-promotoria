<!--
  Casca do vendedor: o mesmo desenho do promotor (celular, uma mão), sem a
  parte que não lhe diz respeito — não há fila offline nem sincronização,
  porque o vendedor só lê o que o promotor contou e ajusta o fator de giro
  produto a produto, na própria tela do pedido. Uma tela só; sem abas.

  Quem também é promotor vai para a contagem pelo menu — item, não aba: a
  contagem é outro app, com fila offline e tudo, não outra tela deste.
-->
<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-toolbar-title class="text-subtitle1 text-weight-medium ellipsis">
          Pedido sugerido
        </q-toolbar-title>

        <q-btn flat dense round icon="more_vert" aria-label="Menu">
          <q-menu>
            <q-list style="min-width: 180px">
              <template v-if="userStore.hasRole('promoter')">
                <q-item clickable v-close-popup :to="{ name: 'PromotorClientes' }">
                  <q-item-section avatar><q-icon name="inventory_2" /></q-item-section>
                  <q-item-section>Contagem de estoque</q-item-section>
                </q-item>
                <q-separator />
              </template>
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

    <TrocarSenhaDialog v-model="dialogSenha" />
  </q-layout>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'
import TrocarSenhaDialog from '@/components/TrocarSenhaDialog.vue'

const router = useRouter()
const auth = useAuthStore()
const userStore = useUserStore()

const dialogSenha = ref(false)

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
