<!--
  Uma linha do pedido sugerido: foto, nome, a conta aberta (venda, estoque e
  o ciclo), o campo do fator de giro e o número grande.

  O fator salva ao sair do campo (ou no Enter), uma linha por vez. Fora de
  1 a 3 não sobe; o que não subiu volta ao que está no servidor, para a tela
  nunca mostrar um número como se tivesse sido gravado. Quem grava é a página
  — esta linha só avisa `fator` e espera o `done`.
-->
<template>
  <q-card flat bordered class="item-card">
    <q-card-section class="row items-center no-wrap q-py-sm">
      <q-avatar square size="56px" class="q-mr-md foto">
        <img v-if="mediaUrl(item.image_url)" :src="mediaUrl(item.image_url)" :alt="item.product_name">
        <q-icon v-else name="inventory_2" color="grey-5" size="32px" />
      </q-avatar>

      <div class="col">
        <div class="text-subtitle1 text-weight-bold ellipsis-2-lines">
          {{ item.product_name || 'Produto' }}
        </div>
        <div class="text-caption text-grey-7">
          vendeu {{ qtd(item.sold) }} · estoque {{ qtd(item.current_stock) }}
        </div>
        <div class="text-caption text-grey-7">
          ciclo {{ dataCurta(item.cycle_from) }} → {{ dataCurta(item.cycle_to) }}
          ({{ item.cycle_days }} {{ item.cycle_days === 1 ? 'dia' : 'dias' }})
        </div>
      </div>

      <div class="column items-end q-ml-sm no-wrap">
        <div class="text-h5 text-weight-bold no-wrap" :class="item.suggested_units ? 'text-primary' : 'text-grey-6'">
          {{ item.suggested_units }} <span class="text-subtitle2">un</span>
        </div>
        <div v-if="item.suggested_boxes" class="text-caption text-grey-7 no-wrap">
          ≈ {{ qtd(item.suggested_boxes) }} cx
        </div>

        <!-- Rótulo fixo, e não flutuante: o vendedor precisa ler "fator de
             giro" antes de tocar, não depois. -->
        <q-input
          v-model.number="fator" type="number" inputmode="decimal"
          outlined dense min="1" max="3" step="0.1" class="campo-fator q-mt-xs"
          label="Fator de giro" stack-label prefix="×" :loading="salvando"
          :error="erro" :error-message="erro ? 'Entre 1 e 3' : ''" hide-bottom-space
          @blur="salvar" @keyup.enter="$event.target.blur()"
        >
          <template #append>
            <q-icon v-if="salvo" name="check" color="positive" size="18px" />
          </template>
        </q-input>
      </div>
    </q-card-section>
  </q-card>
</template>

<script setup>
import { ref, watch } from 'vue'
import { mediaUrl } from '@/api/client'

const props = defineProps({ item: { type: Object, required: true } })
const emit = defineEmits(['fator'])

const fator = ref(Number(props.item.turnover_factor))
const gravado = ref(Number(props.item.turnover_factor))
const salvando = ref(false)
const salvo = ref(false)
const erro = ref(false)

// A página recarrega a lista depois de cada gravação; se o servidor devolver
// outro número para este produto, é ele que vale.
watch(() => props.item.turnover_factor, (novo) => {
  fator.value = Number(novo)
  gravado.value = Number(novo)
})

/** Números vêm como string decimal; mostra sem casas quando são inteiros. */
const qtd = (valor) => Number(valor).toLocaleString('pt-BR', { maximumFractionDigits: 1 })

/** 'AAAA-MM-DD' → 'DD/MM' sem passar por Date (que leria como UTC). */
const dataCurta = (dia) => dia.slice(8, 10) + '/' + dia.slice(5, 7)

/** Uma casa decimal, entre 1 e 3 — o que o servidor aceita. */
function normalizar(valor) {
  const n = Math.round(Number(valor) * 10) / 10
  if (!Number.isFinite(n) || n < 1 || n > 3) return null
  return n
}

function salvar() {
  const novo = normalizar(fator.value)
  erro.value = novo === null
  if (erro.value) return

  fator.value = novo
  if (novo === gravado.value) return

  salvando.value = true
  salvo.value = false
  emit('fator', {
    item: props.item,
    fator: novo,
    done: (ok) => {
      salvando.value = false
      if (ok) {
        gravado.value = novo
        salvo.value = true
      } else {
        fator.value = gravado.value
      }
    },
  })
}
</script>

<style scoped>
.item-card {
  border-radius: 12px;
}

.foto {
  border-radius: 8px;
  background: #f0f2f5;
}

.foto img {
  object-fit: cover;
}

.campo-fator {
  width: 118px;
}

.campo-fator :deep(input) {
  text-align: center;
  font-weight: 600;
}
</style>
