<template>
  <q-layout view="hHh Lpr lFf">
    <q-header elevated class="bg-primary text-white">
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" @click="drawer = !drawer" />
        <q-toolbar-title class="text-subtitle1 text-weight-medium">
          Coleta de Estoque — Administração
        </q-toolbar-title>

        <q-btn flat dense no-caps icon="account_circle" :label="user?.full_name || user?.email">
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

    <q-drawer v-model="drawer" show-if-above bordered :width="250">
      <q-list padding>
        <q-item
          v-for="item in menu" :key="item.name"
          clickable v-ripple :to="{ name: item.name }" active-class="bg-blue-1 text-primary"
        >
          <q-item-section avatar><q-icon :name="item.icon" /></q-item-section>
          <q-item-section>{{ item.label }}</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>

    <TrocarSenhaDialog v-model="dialogSenha" />
  </q-layout>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'
import TrocarSenhaDialog from '@/components/TrocarSenhaDialog.vue'

const router = useRouter()
const auth = useAuthStore()
const userStore = useUserStore()
const { user } = storeToRefs(userStore)

const drawer = ref(false)
const dialogSenha = ref(false)

const menu = [
  { name: 'AdminDashboard', label: 'Evolução do estoque', icon: 'insights' },
  { name: 'AdminVisitas', label: 'Contagens recebidas', icon: 'inventory' },
  { name: 'AdminVinculos', label: 'Clientes por promotor', icon: 'link' },
  { name: 'AdminCadastros', label: 'Cadastros', icon: 'folder_shared' },
]

function logout() {
  auth.logout()
  userStore.clearUser()
  router.push('/login')
}
</script>
