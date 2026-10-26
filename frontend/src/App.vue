<template>
  <div id="app">
    <RouterView />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useQuasar } from 'quasar'

const $q = useQuasar()

onMounted(() => {
  const saved = localStorage.getItem('darkMode')
  if (saved !== null) {
    $q.dark.set(saved === 'true')
  }
})
</script>

<style scoped>
#app {
  min-height: 100vh;
}
</style>

<style>
/* Fundo padrão das páginas — adapta automaticamente ao tema */
.q-page {
  background: #f5f7fa;
}
.body--dark .q-page {
  background: #121212;
}

/* Textos em escala de cinza escuro ficam ilegíveis no dark mode.
   Redefine para valores adequados ao fundo escuro. */
.body--dark .text-grey-9,
.body--dark .text-grey-8 {
  color: rgba(255, 255, 255, 0.87) !important;
}
.body--dark .text-grey-7 {
  color: rgba(255, 255, 255, 0.60) !important;
}

/* Garante que dialogs herdam o background correto em dark mode */
.body--dark .q-dialog .q-card {
  background: #1e1e2e;
}

/* Remove scroll horizontal indesejado em dialogs em mobile */
.q-dialog__inner {
  padding: 8px;
}
.q-dialog__inner > .q-card {
  margin: 0 auto;
}

/* O QSelect mostra o item escolhido numa linha só, cortado com reticências.
   Nome de cliente e de produto não se corta: quebra em quantas linhas precisar,
   e o campo cresce junto. */
.q-select .q-field__native > .ellipsis {
  white-space: normal;
  overflow: visible;
}
</style>

