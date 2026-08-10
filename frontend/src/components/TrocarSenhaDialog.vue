<!--
  Trocar a própria senha. Vive nos dois layouts porque vale para os dois papéis:
  o administrador nasce com a senha do `seed` e não tinha por onde trocá-la (a
  tela de cadastros só lista promotores), e o promotor recebe do administrador
  uma senha que mais alguém digitou.
-->
<template>
  <q-dialog :model-value="modelValue" @update:model-value="fechar" @hide="limpar">
    <q-card style="min-width: 320px; max-width: 90vw">
      <q-card-section class="text-subtitle1">Trocar minha senha</q-card-section>
      <q-separator />

      <q-card-section class="q-gutter-md">
        <q-input
          v-model="senhaAtual" outlined dense type="password"
          label="Senha atual *" autocomplete="current-password"
          @keyup.enter="salvar"
        />
        <q-input
          v-model="novaSenha" outlined dense type="password"
          label="Nova senha *" autocomplete="new-password"
          hint="Mínimo 8 caracteres"
          @keyup.enter="salvar"
        />
        <q-input
          v-model="confirmacao" outlined dense type="password"
          label="Repita a nova senha *" autocomplete="new-password"
          @keyup.enter="salvar"
        />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat no-caps label="Cancelar" v-close-popup />
        <q-btn
          color="primary" unelevated no-caps label="Salvar"
          :loading="salvando" @click="salvar"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { useQuasar } from 'quasar'
import { useUserStore } from '@/stores/user'

// `props`/`emit` em vez de `defineModel`: o projeto não fixa a minor do Vue
// (`^3.3.0`) e `defineModel` só estabilizou na 3.4.
defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])

const fechar = (valor) => emit('update:modelValue', valor)

const $q = useQuasar()
const userStore = useUserStore()

const senhaAtual = ref('')
const novaSenha = ref('')
const confirmacao = ref('')
const salvando = ref(false)

function limpar() {
  senhaAtual.value = ''
  novaSenha.value = ''
  confirmacao.value = ''
}

function avisar(message) {
  $q.notify({ type: 'warning', message, position: 'top' })
}

async function salvar() {
  if (!senhaAtual.value || !novaSenha.value) {
    return avisar('Preencha a senha atual e a nova.')
  }
  // Mesmo mínimo que o backend exige, checado aqui para o erro chegar antes da
  // viagem até o servidor.
  if (novaSenha.value.length < 8) {
    return avisar('A nova senha precisa ter pelo menos 8 caracteres.')
  }
  if (novaSenha.value !== confirmacao.value) {
    return avisar('A confirmação não confere com a nova senha.')
  }

  salvando.value = true
  try {
    await userStore.changePassword(senhaAtual.value, novaSenha.value)
    fechar(false)
    $q.notify({ type: 'positive', message: 'Senha alterada.', position: 'top' })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao trocar a senha',
      position: 'top',
    })
  } finally {
    salvando.value = false
  }
}
</script>
