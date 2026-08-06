<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="flex flex-center bg-primary">
        <q-card flat class="q-pa-lg" style="width: 100%; max-width: 380px">
          <q-card-section class="text-center q-pb-none">
            <q-avatar size="72px" color="primary" text-color="white" icon="inventory_2" />
            <div class="text-h6 q-mt-md">Coleta de Estoque</div>
            <div class="text-caption text-grey-7">Entre com seu usuário e senha</div>
          </q-card-section>

          <q-card-section>
            <q-form @submit.prevent="handleLogin">
              <q-input
                v-model="credentials.username" outlined
                label="Usuário ou e-mail" autocomplete="username"
                class="q-mb-md" :disable="loading"
              >
                <template #prepend><q-icon name="person" /></template>
              </q-input>

              <q-input
                v-model="credentials.password" outlined
                :type="showPassword ? 'text' : 'password'"
                label="Senha" autocomplete="current-password"
                class="q-mb-md" :disable="loading"
              >
                <template #prepend><q-icon name="lock" /></template>
                <template #append>
                  <q-icon
                    :name="showPassword ? 'visibility_off' : 'visibility'"
                    class="cursor-pointer"
                    @click="showPassword = !showPassword"
                  />
                </template>
              </q-input>

              <q-banner v-if="errorMessage" dense class="bg-red-1 text-negative q-mb-md rounded-borders">
                {{ errorMessage }}
              </q-banner>

              <q-btn
                type="submit" color="primary" size="lg" unelevated no-caps
                class="full-width" label="Entrar" :loading="loading"
              />
            </q-form>
          </q-card-section>
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const authStore = useAuthStore()
const userStore = useUserStore()

const credentials = ref({ username: '', password: '' })
const showPassword = ref(false)
const loading = ref(false)
const errorMessage = ref('')

async function handleLogin() {
  errorMessage.value = ''

  if (!credentials.value.username || !credentials.value.password) {
    errorMessage.value = 'Preencha usuário e senha'
    return
  }

  loading.value = true
  try {
    await authStore.login({
      username: credentials.value.username,
      password: credentials.value.password,
    })
    const user = await userStore.fetchCurrentUser()

    // O promotor vai direto para a lista de clientes; o admin, para as contagens
    router.push(user?.role === 'promoter' ? '/promotor' : '/admin')
  } catch (error) {
    errorMessage.value =
      error.response?.status === 401
        ? 'Usuário ou senha inválidos'
        : error.response?.data?.detail || 'Não foi possível entrar. Tente novamente.'
  } finally {
    loading.value = false
  }
}
</script>
