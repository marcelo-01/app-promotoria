<!--
  O fator de giro de cada cliente, de 1 a 3, com uma casa decimal.

  É o único número que o vendedor grava neste app. Multiplica a venda do ciclo
  na sugestão de pedido: 1 repõe o que vendeu, 2 dobra a cobertura. Salva ao
  sair do campo (ou no Enter), um cliente por vez — não há botão "salvar tudo"
  porque cada linha é uma decisão à parte, e o visto ao lado diz qual já subiu.
-->
<template>
  <q-page class="q-pa-md">
    <q-banner class="bg-blue-1 text-blue-10 rounded-borders q-mb-md">
      <template #avatar><q-icon name="info" color="primary" /></template>
      O pedido sugerido é a <b>venda × fator</b>, menos o estoque da loja.
      Com <b>1</b> o pedido repõe o que vendeu; com <b>2</b>, dobra a cobertura. Vai de 1 a 3.
    </q-banner>

    <div v-if="loading" class="column items-center q-pa-xl">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner v-else-if="!linhas.length" class="bg-grey-2 text-grey-8 rounded-borders">
      <template #avatar><q-icon name="store" color="grey-6" /></template>
      Nenhum cliente vinculado a você. Fale com o administrador.
    </q-banner>

    <q-list v-else bordered separator class="rounded-borders bg-white lista">
      <q-item v-for="linha in linhas" :key="linha.customer_id" class="q-py-sm">
        <q-item-section>
          <q-item-label class="text-subtitle1 text-weight-medium ellipsis-2-lines">
            {{ linha.customer_name }}
          </q-item-label>
        </q-item-section>

        <q-item-section side>
          <q-input
            v-model.number="linha.fator" type="number" inputmode="decimal"
            outlined dense min="1" max="3" step="0.1" class="campo-fator"
            :loading="linha.salvando"
            :error="linha.erro" :error-message="linha.erro ? 'Entre 1 e 3' : ''"
            hide-bottom-space
            @blur="salvar(linha)" @keyup.enter="$event.target.blur()"
          >
            <template #append>
              <q-icon v-if="linha.salvo" name="check" color="positive" size="20px" />
            </template>
          </q-input>
        </q-item-section>
      </q-item>
    </q-list>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const linhas = ref([])
const loading = ref(false)

async function carregar() {
  loading.value = true
  try {
    linhas.value = (await merchandisingApi.turnoverFactors()).map((f) => ({
      ...f,
      fator: Number(f.turnover_factor),
      gravado: Number(f.turnover_factor),
      salvando: false,
      salvo: false,
      erro: false,
    }))
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar os fatores',
    })
  } finally {
    loading.value = false
  }
}

/** Uma casa decimal, entre 1 e 3 — o que o servidor aceita. */
function normalizar(valor) {
  const n = Math.round(Number(valor) * 10) / 10
  if (!Number.isFinite(n) || n < 1 || n > 3) return null
  return n
}

async function salvar(linha) {
  const fator = normalizar(linha.fator)
  linha.erro = fator === null
  if (linha.erro) return

  linha.fator = fator
  if (fator === linha.gravado) return

  linha.salvando = true
  linha.salvo = false
  try {
    await merchandisingApi.setTurnoverFactor(linha.customer_id, fator)
    linha.gravado = fator
    linha.salvo = true
  } catch (error) {
    // Volta ao que está no servidor: a tela não pode ficar mostrando um número
    // que não subiu como se tivesse subido.
    linha.fator = linha.gravado
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Não foi possível salvar o fator',
    })
  } finally {
    linha.salvando = false
  }
}

onMounted(carregar)
</script>

<style scoped>
.lista {
  border-radius: 12px;
}

.campo-fator {
  width: 104px;
}

.campo-fator :deep(input) {
  text-align: center;
  font-size: 1.1rem;
  font-weight: 600;
}
</style>
