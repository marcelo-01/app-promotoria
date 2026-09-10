<!--
  Painel do dia — a primeira tela do administrador.

  Dois painéis, e nada além disso de propósito:

  · COBERTURA responde "o dia está indo bem?" antes de qualquer filtro. O
    denominador é a carteira (os vínculos promotor → cliente), e "fechada" é a
    loja com as duas contagens: é essa, e só essa, que vira planilha. Somar meia
    visita ao número mostraria um dia melhor do que o que dá para exportar.

  · VISITAS PELA METADE é a mesma informação que a tela de contagens já traz
    linha a linha, com o que falta lá: a idade. Meia visita de hoje é o promotor
    ainda dentro da loja; meia visita de três dias atrás é um telefonema. Por
    isso esta lista vem da mais velha para a mais nova, e não da mais recente.

  As cores são as mesmas da tela de contagens — verde "completa", laranja
  "aguardando", cinza "não chegou" — e nunca aparecem sozinhas: todo estado tem
  ícone e palavra ao lado.
-->
<template>
  <q-page class="q-pa-md">
    <div class="row items-start justify-between q-mb-md q-col-gutter-sm">
      <div class="col">
        <div class="text-h6">Painel do dia</div>
        <div class="text-caption text-grey-7">
          Quanto da carteira já fechou a visita, e o que ficou pela metade.
        </div>
      </div>
      <div class="col-12 col-sm-auto row items-center q-gutter-sm">
        <q-input
          v-model="dia" outlined dense type="date" label="Dia" stack-label
          style="min-width: 150px" @update:model-value="carregar"
        />
        <q-btn
          flat dense round icon="refresh" color="grey-7" :loading="carregando"
          @click="carregar"
        >
          <q-tooltip>Atualizar</q-tooltip>
        </q-btn>
      </div>
    </div>

    <div class="row q-col-gutter-md">
      <!-- ── Cobertura ─────────────────────────────────────────────────── -->
      <div class="col-12 col-md-7">
        <q-card flat bordered class="full-height">
          <q-card-section>
            <div class="text-subtitle1">Cobertura</div>
            <div class="text-caption text-grey-7">{{ legendaDoDia }}</div>
          </q-card-section>

          <q-inner-loading :showing="carregando && !dados">
            <q-spinner color="primary" size="2em" />
          </q-inner-loading>

          <template v-if="cobertura">
            <q-card-section v-if="!cobertura.customers_total" class="q-pt-none">
              <q-banner dense class="bg-grey-2 rounded-borders">
                <template #avatar><q-icon name="link_off" color="grey-7" /></template>
                Nenhum cliente vinculado a um promotor ativo. Enquanto a carteira
                estiver vazia não há com o que comparar as contagens do dia.
                <template #action>
                  <q-btn flat dense no-caps color="primary" label="Definir vínculos"
                         :to="{ name: 'AdminVinculos' }" />
                </template>
              </q-banner>
            </q-card-section>

            <template v-else>
              <q-card-section class="q-pt-none">
                <!-- O número que a tela lidera: lojas fechadas sobre a carteira -->
                <div class="row items-baseline q-gutter-x-sm">
                  <div class="numero-heroi">{{ cobertura.closed }}</div>
                  <div class="text-h6 text-grey-6">de {{ cobertura.customers_total }}</div>
                </div>
                <div class="text-body2 text-grey-8">
                  lojas com gôndola e estoque contados — as que já viram planilha
                </div>

                <div class="barra q-mt-md">
                  <div
                    v-for="faixa in faixas" :key="faixa.chave"
                    v-show="faixa.valor"
                    :class="`bg-${faixa.cor}`"
                    :style="{ width: `${(faixa.valor / cobertura.customers_total) * 100}%` }"
                  />
                </div>

                <!-- Estado nunca fica só na cor: ícone e palavra do lado -->
                <div class="row q-col-gutter-md q-mt-sm">
                  <div v-for="faixa in faixas" :key="faixa.chave" class="col-auto row items-center">
                    <q-icon :name="faixa.icone" :color="faixa.cor" size="18px" class="q-mr-xs" />
                    <span class="text-weight-medium q-mr-xs">{{ faixa.valor }}</span>
                    <span class="text-caption text-grey-7">{{ faixa.rotulo }}</span>
                  </div>
                </div>
              </q-card-section>

              <q-separator />

              <q-card-section>
                <div class="text-caption text-grey-7 q-mb-sm">
                  Cada promotor na própria carteira. Loja atendida por dois conta
                  para os dois — por isso a soma pode passar do total acima.
                </div>

                <div
                  v-for="linha in cobertura.by_promoter" :key="linha.promoter_id"
                  class="row items-center q-py-xs q-col-gutter-sm"
                >
                  <div class="col-12 col-sm-4 ellipsis">
                    {{ linha.promoter_name || 'Sem nome' }}
                  </div>
                  <div class="col">
                    <div class="barra barra--fina">
                      <div
                        v-for="faixa in faixasDe(linha)" :key="faixa.chave"
                        v-show="faixa.valor"
                        :class="`bg-${faixa.cor}`"
                        :style="{ width: `${(faixa.valor / linha.customers_total) * 100}%` }"
                      />
                    </div>
                  </div>
                  <div class="col-auto text-caption text-grey-8 numero-tabela">
                    {{ linha.closed }}/{{ linha.customers_total }}
                  </div>
                </div>
              </q-card-section>
            </template>
          </template>
        </q-card>
      </div>

      <!-- ── Visitas pela metade ───────────────────────────────────────── -->
      <div class="col-12 col-md-5">
        <q-card flat bordered class="full-height">
          <q-card-section class="row items-start justify-between q-col-gutter-sm">
            <div class="col">
              <div class="text-subtitle1">Visitas pela metade</div>
              <div class="text-caption text-grey-7">
                Chegou um lado só — sem o outro, não sai planilha.
              </div>
            </div>
            <div class="col-auto">
              <q-btn-toggle
                v-model="janela" dense unelevated no-caps
                toggle-color="primary" color="grey-3" text-color="grey-8"
                :options="[{ label: '7d', value: 7 }, { label: '30d', value: 30 }, { label: '90d', value: 90 }]"
                @update:model-value="carregar"
              />
            </div>
          </q-card-section>

          <template v-if="travadas">
            <q-card-section class="q-pt-none">
              <div class="row items-baseline q-gutter-x-sm">
                <div class="text-h4 text-weight-medium"
                     :class="travadas.total ? 'text-orange-9' : 'text-grey-6'">
                  {{ travadas.total }}
                </div>
                <div class="text-body2 text-grey-8">
                  {{ travadas.total === 1 ? 'visita aberta' : 'visitas abertas' }}
                  nos últimos {{ travadas.window_days }} dias
                </div>
              </div>
              <div v-if="travadas.overdue" class="text-caption text-grey-8 q-mt-xs">
                <q-icon name="priority_high" color="negative" size="16px" />
                {{ travadas.overdue }}
                {{ travadas.overdue === 1 ? 'passou' : 'passaram' }} do próprio dia —
                {{ travadas.overdue === 1 ? 'essa não fecha' : 'essas não fecham' }}
                mais sozinha{{ travadas.overdue === 1 ? '' : 's' }}.
              </div>
            </q-card-section>

            <q-card-section v-if="!travadas.total" class="q-pt-none">
              <q-banner dense class="bg-green-1 rounded-borders">
                <template #avatar><q-icon name="done_all" color="positive" /></template>
                Nenhuma contagem esperando o outro lado.
              </q-banner>
            </q-card-section>

            <q-list v-else separator style="max-height: 420px; overflow-y: auto">
              <q-item
                v-for="linha in travadas.items"
                :key="`${linha.customer_id}|${linha.promoter_id}|${linha.day}`"
                clickable v-ripple @click="abrirNasContagens(linha)"
              >
                <q-item-section>
                  <q-item-label class="ellipsis">{{ linha.customer_name }}</q-item-label>
                  <q-item-label caption>
                    {{ linha.promoter_name }} · {{ formatDia(linha.day) }}
                  </q-item-label>
                  <q-item-label class="q-mt-xs">
                    <q-chip dense square outline color="orange-9" icon="hourglass_top"
                            class="q-ml-none">
                      Falta {{ rotuloTipo(linha.missing_side).toLowerCase() }}
                    </q-chip>
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-chip dense square :color="idade(linha).cor" text-color="white"
                          :icon="idade(linha).icone">
                    {{ idade(linha).texto }}
                  </q-chip>
                </q-item-section>
              </q-item>
            </q-list>

            <q-card-section
              v-if="travadas.total > travadas.items.length" class="text-caption text-grey-7"
            >
              Mostrando as {{ travadas.items.length }} mais antigas de
              {{ travadas.total }}.
            </q-card-section>
          </template>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()
const router = useRouter()

const dados = ref(null)
const carregando = ref(false)
const janela = ref(30)

/** 'AAAA-MM-DD' de hoje no relógio de quem está olhando — o mesmo dia local que
 *  o servidor usa para parear gôndola e estoque. */
const hoje = () => {
  const agora = new Date()
  const mes = String(agora.getMonth() + 1).padStart(2, '0')
  return `${agora.getFullYear()}-${mes}-${String(agora.getDate()).padStart(2, '0')}`
}
const dia = ref(hoje())

const cobertura = computed(() => dados.value?.coverage || null)
const travadas = computed(() => dados.value?.stuck || null)

const formatDia = (v) => (v ? new Date(`${v}T00:00:00`).toLocaleDateString('pt-BR') : '—')
const rotuloTipo = (v) => (v === 'gondola' ? 'Gôndola' : 'Estoque')

const legendaDoDia = computed(() =>
  dia.value === hoje() ? 'Hoje' : formatDia(dia.value)
)

/** As três faixas da barra, na ordem em que a visita caminha: fechou, está pela
 *  metade, não começou. */
function faixasDe(numeros) {
  return [
    { chave: 'closed', valor: numeros.closed, cor: 'positive',
      icone: 'done_all', rotulo: 'fechadas' },
    { chave: 'partial', valor: numeros.partial, cor: 'orange-9',
      icone: 'hourglass_top', rotulo: 'pela metade' },
    { chave: 'missing', valor: numeros.missing, cor: 'grey-5',
      icone: 'remove', rotulo: 'sem contagem' },
  ]
}
const faixas = computed(() => (cobertura.value ? faixasDe(cobertura.value) : []))

/** Quanto tempo a visita está esperando. Hoje é cinza porque pode ser o promotor
 *  ainda na loja; de três dias em diante deixa de ser espera. */
function idade({ days_waiting: dias }) {
  if (!dias) return { texto: 'hoje', cor: 'grey-6', icone: 'schedule' }
  if (dias >= 3) return { texto: `${dias} dias`, cor: 'negative', icone: 'priority_high' }
  return { texto: dias === 1 ? '1 dia' : `${dias} dias`, cor: 'orange-9', icone: 'schedule' }
}

/** Leva para a tela de contagens já filtrada naquele promotor e naquele dia — a
 *  linha da visita é a primeira que aparece lá. */
function abrirNasContagens(linha) {
  router.push({
    name: 'AdminVisitas',
    query: { promoter_id: linha.promoter_id, date_from: linha.day, date_to: linha.day },
  })
}

async function carregar() {
  carregando.value = true
  try {
    dados.value = await merchandisingApi.dashboard({
      day: dia.value || undefined,
      stuck_days: janela.value,
    })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar o painel',
    })
  } finally {
    carregando.value = false
  }
}

onMounted(carregar)
</script>

<style scoped>
/* O número que a tela lidera. Figuras proporcionais: `tabular-nums` daria a
   todo dígito a largura do zero, e em corpo grande isso fica frouxo. */
.numero-heroi {
  font-size: 52px;
  line-height: 1;
  font-weight: 600;
}

/* Nas colunas é o contrário: os números precisam alinhar entre as linhas. */
.numero-tabela {
  font-variant-numeric: tabular-nums;
}

/* Barra empilhada: pontas arredondadas e 2px da própria superfície entre as
   faixas — separador desenhado, e não borda em volta de cada pedaço. */
.barra {
  display: flex;
  gap: 2px;
  height: 12px;
  border-radius: 6px;
  overflow: hidden;
  background: transparent;
}
.barra--fina {
  height: 8px;
  border-radius: 4px;
}
</style>
