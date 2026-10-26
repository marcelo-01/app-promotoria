<!--
  Evolução do estoque dos clientes.

  O QUE ESTES NÚMEROS SÃO. Este app não conhece entregas nem pedidos, então a
  diferença entre duas contagens é líquida, não bruta: o que subiu quer dizer
  que houve entrega de pelo menos aquilo, e o que caiu, que saiu pelo menos
  aquilo. Nada aqui se chama "venda", e a tela repete isso onde o número aparece
  — é a diferença entre um indicador útil e um que induz a decisão errada.

  CONTAGEM IRREGULAR. O promotor não passa todo dia. Por isso a linha do tempo
  anda por contagem e não por dia, sem interpolar: dia sem contagem é dia sem
  ponto, e o espaçamento desigual entre eles é informação, não defeito. As
  comparações de total usam só os dias em que gôndola e estoque foram contados —
  a mesma regra da planilha, e pelo mesmo motivo.

  O gráfico é SVG escrito à mão, sem biblioteca. Não é bravata: o plano trata
  cada dependência nova como custo no dia da fusão com o ERP, e uma biblioteca
  de gráficos aqui obrigaria o ERP a adotá-la junto. São cem linhas.
-->
<template>
  <q-page class="q-pa-md">
    <div class="cabecalho q-mb-md">
      <div class="cabecalho__texto">
        <div class="text-h6">Evolução do estoque</div>
        <div class="text-caption text-grey-7">
          O que mudou no estoque dos clientes entre uma contagem e outra.
        </div>
      </div>
      <div class="cabecalho__acoes row items-center q-gutter-sm">
        <q-btn-toggle
          v-model="janela" dense unelevated no-caps
          toggle-color="primary" color="grey-3" text-color="grey-8"
          :options="[{ label: '30d', value: 30 }, { label: '90d', value: 90 }, { label: '180d', value: 180 }]"
          @update:model-value="carregarTudo"
        />
        <q-btn flat dense round icon="refresh" color="grey-7" :loading="carregando"
               @click="carregarTudo">
          <q-tooltip>Atualizar</q-tooltip>
        </q-btn>
      </div>
    </div>

    <q-banner v-if="insights && !insights.customers.length" class="bg-grey-2 rounded-borders">
      <template #avatar><q-icon name="inventory" color="grey-7" /></template>
      Nenhuma contagem nos últimos {{ janela }} dias. A evolução do estoque só
      aparece depois que houver pelo menos duas contagens de um mesmo cliente.
    </q-banner>

    <template v-else>
      <!-- ── A linha do tempo ────────────────────────────────────────────── -->
      <q-card flat bordered class="q-mb-md" ref="cardGrafico">
        <q-card-section class="cabecalho">
          <div class="cabecalho__texto">
            <div class="text-subtitle1">Quanto havia, contagem a contagem</div>
            <div class="text-caption text-grey-7">
              Um ponto por contagem, na data em que foi feita. Dia sem contagem
              não vira ponto.
            </div>
          </div>
          <div class="cabecalho__acoes row items-center q-gutter-sm">
            <q-select
              v-model="clienteId" outlined dense emit-value map-options stack-label
              style="min-width: 210px" label="Cliente"
              :options="opcoesClientes" option-value="customer_id" option-label="label"
              @update:model-value="trocarCliente"
            />
            <q-chip
              v-if="produtoId" removable dense square color="grey-3" text-color="grey-9"
              icon="filter_alt" class="chip-produto" @remove="verProduto(null)"
            >
              {{ historico?.product_name || 'produto' }}
            </q-chip>
          </div>
        </q-card-section>

        <q-card-section class="q-pt-none">
          <div v-if="carregandoHistorico" class="text-center q-pa-lg">
            <q-spinner color="primary" size="2em" />
          </div>

          <q-banner v-else-if="pontos.length < 2" dense class="bg-grey-2 rounded-borders">
            <template #avatar><q-icon name="timeline" color="grey-7" /></template>
            {{ pontos.length === 1
              ? 'Este cliente tem uma contagem só na janela — não há evolução para mostrar ainda.'
              : 'Nenhuma contagem deste cliente na janela escolhida.' }}
          </q-banner>

          <template v-else>
            <!-- Legenda sempre presente: são duas séries, e a identidade delas
                 nunca fica só na cor. -->
            <div class="row q-gutter-md q-mb-sm">
              <div v-for="serie in SERIES" :key="serie.chave" class="row items-center">
                <span class="marca-serie" :style="{ background: serie.cor }" />
                <span class="text-caption text-grey-8 q-ml-xs">{{ serie.rotulo }}</span>
              </div>
            </div>

            <div ref="caixaGrafico" class="grafico">
              <svg :width="largura" :height="ALTURA" @mousemove="mover" @mouseleave="foco = null">
                <!-- Grade: hairline sólida, um tom fora da superfície -->
                <g>
                  <line
                    v-for="t in ticksY" :key="`g${t.valor}`"
                    :x1="MARGEM.esq" :x2="largura - MARGEM.dir" :y1="t.y" :y2="t.y"
                    stroke="#e4e4e7" stroke-width="1"
                  />
                  <text
                    v-for="t in ticksY" :key="`r${t.valor}`"
                    :x="MARGEM.esq - 8" :y="t.y + 4" text-anchor="end"
                    class="rotulo-eixo"
                  >{{ formatQtd(t.valor) }}</text>
                </g>

                <!-- Datas: só as que cabem, nunca uma por ponto -->
                <text
                  v-for="t in ticksX" :key="`d${t.dia}`"
                  :x="t.x" :y="ALTURA - 8" text-anchor="middle" class="rotulo-eixo"
                >{{ t.rotulo }}</text>

                <!-- Cruz do ponto sob o cursor -->
                <line
                  v-if="foco" :x1="foco.x" :x2="foco.x" :y1="MARGEM.topo"
                  :y2="ALTURA - MARGEM.base" stroke="#a1a1aa" stroke-width="1"
                />

                <g v-for="serie in SERIES" :key="serie.chave">
                  <polyline
                    :points="linha(serie.chave)" fill="none" :stroke="serie.cor"
                    stroke-width="2" stroke-linejoin="round" stroke-linecap="round"
                  />
                  <circle
                    v-for="p in pontosDe(serie.chave)" :key="`${serie.chave}${p.day}`"
                    :cx="p.x" :cy="p.y" r="4" :fill="serie.cor"
                    stroke="#fff" stroke-width="2"
                  />
                  <!-- Rótulo direto só na ponta: valor em todo ponto vira ruído -->
                  <text
                    v-if="ultimoDe(serie.chave)"
                    :x="ultimoDe(serie.chave).x + 8" :y="ultimoDe(serie.chave).y + 4"
                    class="rotulo-ponta" :fill="serie.cor"
                  >{{ formatQtd(ultimoDe(serie.chave).valor) }}</text>
                </g>
              </svg>

              <div v-if="foco" class="dica" :style="posicaoDica">
                <div class="text-weight-medium">{{ formatDia(foco.dia) }}</div>
                <div v-for="serie in SERIES" :key="serie.chave" class="row items-center no-wrap">
                  <span class="marca-serie" :style="{ background: serie.cor }" />
                  <span class="q-ml-xs">{{ serie.rotulo }}:</span>
                  <span class="q-ml-xs text-weight-medium">
                    {{ foco.valores[serie.chave] === null
                      ? 'não contado' : `${formatQtd(foco.valores[serie.chave])} un` }}
                  </span>
                </div>
              </div>
            </div>

            <div class="text-caption text-grey-7 q-mt-sm">
              {{ pontos.length }} contagens entre {{ formatDia(pontos[0].day) }} e
              {{ formatDia(pontos[pontos.length - 1].day) }}.
              Variação entre contagens — não é venda: sem os dados de entrega, o
              que caiu saiu <em>pelo menos</em> aquilo.
            </div>
          </template>
        </q-card-section>
      </q-card>

      <!-- ── Os três indicadores ─────────────────────────────────────────── -->
      <div class="row q-col-gutter-md">
        <div class="col-12 col-md-4">
          <q-card flat bordered class="full-height">
            <q-card-section>
              <div class="text-subtitle1">
                Produtos parados
                <q-badge v-if="insights?.stalled_total" color="grey-6" class="q-ml-xs">
                  {{ insights.stalled_total }}
                </q-badge>
              </div>
              <div class="text-caption text-grey-7">
                Mesma quantidade em três contagens ou mais — não vendeu nem foi
                reposto. É o indicador que menos sofre com contagem irregular:
                a planura é o sinal.
              </div>
            </q-card-section>
            <q-separator />
            <ListaVazia v-if="!insights?.stalled.length" texto="Nada parado na janela." />
            <q-list v-else separator>
              <q-item
                v-for="p in insights.stalled" :key="`${p.customer_id}${p.product_id}`"
                clickable v-ripple @click="verProduto(p)"
              >
                <q-item-section>
                  <q-item-label>{{ p.product_name }}</q-item-label>
                  <q-item-label caption>{{ p.customer_name }}</q-item-label>
                </q-item-section>
                <q-item-section side>
                  <div class="text-right">
                    <div class="text-weight-medium text-grey-9">
                      {{ formatQtd(p.quantity) }} un
                    </div>
                    <div class="text-caption text-grey-7">
                      {{ p.days }} dias · {{ p.counts }} contagens
                    </div>
                  </div>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card>
        </div>

        <div class="col-12 col-md-4">
          <q-card flat bordered class="full-height">
            <q-card-section>
              <div class="text-subtitle1">Sumiu e voltou</div>
              <div class="text-caption text-grey-7">
                Comparando as duas últimas contagens do cliente. Compara a loja
                com ela mesma, então não depende de o promotor ter digitado zero.
              </div>
            </q-card-section>
            <q-separator />

            <template v-for="grupo in GRUPOS" :key="grupo.chave">
              <q-item-label header class="text-uppercase text-caption">
                <q-icon :name="grupo.icone" :color="grupo.cor" size="16px" class="q-mr-xs" />
                {{ grupo.rotulo }}
                <span class="text-grey-6">({{ insights?.[`${grupo.chave}_total`] || 0 }})</span>
              </q-item-label>
              <div v-if="!insights?.[grupo.chave].length" class="q-px-md q-pb-sm text-caption text-grey-7">
                {{ grupo.vazio }}
              </div>
              <q-list v-else separator>
                <q-item
                  v-for="m in insights[grupo.chave]" :key="`${m.customer_id}${m.product_id}`"
                  clickable v-ripple @click="verProduto(m)"
                >
                  <q-item-section>
                    <q-item-label>{{ m.product_name }}</q-item-label>
                    <q-item-label caption>
                      {{ m.customer_name }} · {{ m.days }} dias
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side class="text-caption numero-tabela"
                                  :class="grupo.chave === 'gone' ? 'text-negative' : 'text-positive'">
                    {{ formatQtd(m.previous) }} → {{ formatQtd(m.current) }}
                  </q-item-section>
                </q-item>
              </q-list>
            </template>
          </q-card>
        </div>

        <div class="col-12 col-md-4">
          <q-card flat bordered class="full-height">
            <q-card-section>
              <div class="text-subtitle1">
                Gôndola vazia com estoque
                <q-badge v-if="insights?.shelf_gap_total" color="orange-9" class="q-ml-xs">
                  {{ insights.shelf_gap_total }}
                </q-badge>
              </div>
              <div class="text-caption text-grey-7">
                Zerado na prateleira e com saldo no depósito: a mercadoria está
                na loja, atrás. É falha de reposição, não falta de produto.
              </div>
            </q-card-section>
            <q-separator />
            <ListaVazia v-if="!insights?.shelf_gap.length"
                        texto="Nenhuma prateleira vazia com saldo guardado." />
            <q-list v-else separator>
              <q-item
                v-for="f in insights.shelf_gap" :key="`${f.customer_id}${f.product_id}`"
                clickable v-ripple @click="verProduto(f)"
              >
                <q-item-section>
                  <q-item-label>{{ f.product_name }}</q-item-label>
                  <q-item-label caption>{{ f.customer_name }}</q-item-label>
                  <q-item-label v-if="f.repeated" class="q-mt-xs">
                    <q-chip dense square outline color="orange-9" icon="repeat" class="q-ml-none">
                      Repetido
                    </q-chip>
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <div class="text-right">
                    <div class="text-weight-medium text-grey-9">
                      {{ formatQtd(f.estoque) }} un
                    </div>
                    <div class="text-caption text-grey-7">no depósito</div>
                  </div>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card>
        </div>
      </div>
    </template>
  </q-page>
</template>

<script setup>
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

// Par validado para daltonismo: ΔE 22,5 sob deuteranopia contra a superfície
// clara. O azul é um degrau mais claro do índigo da marca — o #1a237e do
// cabeçalho é escuro demais para linha fina, e o teal escuro lê como cinza.
const SERIES = [
  { chave: 'gondola', rotulo: 'Gôndola', cor: '#3f51b5' },
  { chave: 'estoque', rotulo: 'Estoque', cor: '#00a08f' },
]

const GRUPOS = [
  { chave: 'gone', rotulo: 'Sumiu', icone: 'trending_down', cor: 'negative',
    vazio: 'Nenhum produto zerou na última contagem.' },
  { chave: 'returned', rotulo: 'Voltou', icone: 'trending_up', cor: 'positive',
    vazio: 'Nenhum produto voltou depois de zerado.' },
]

const ALTURA = 240
const MARGEM = { esq: 52, dir: 46, topo: 16, base: 30 }

const janela = ref(90)
const insights = ref(null)
const historico = ref(null)
const clienteId = ref(null)
const produtoId = ref(null)
const carregando = ref(false)
const carregandoHistorico = ref(false)

const caixaGrafico = ref(null)
const largura = ref(720)
const foco = ref(null)
let observador = null

const formatQtd = (v) => Number(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })
const formatDia = (v) => (v ? new Date(`${v}T00:00:00`).toLocaleDateString('pt-BR') : '—')
const diaCurto = (v) =>
  new Date(`${v}T00:00:00`).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })

const pontos = computed(() => historico.value?.points || [])

const opcoesClientes = computed(() =>
  (insights.value?.customers || []).map((c) => ({
    ...c,
    label: `${c.customer_name || 'Sem nome'} · ${c.complete_counts} ${
      c.complete_counts === 1 ? 'contagem' : 'contagens'}`,
  }))
)

/** Componente local para o "nada aqui" das listas — três delas repetem isso. */
const ListaVazia = (props) =>
  h('div', { class: 'q-pa-md text-caption text-grey-7' }, props.texto)
ListaVazia.props = ['texto']

// ── Escalas ─────────────────────────────────────────────────────────────
// O eixo X é TEMPO, não posição na lista: contagem quinzenal e contagem diária
// não podem sair com o mesmo espaçamento, senão o gráfico mente sobre o ritmo.

const emMs = (dia) => new Date(`${dia}T00:00:00`).getTime()

const dominioX = computed(() => {
  if (!pontos.value.length) return [0, 1]
  const datas = pontos.value.map((p) => emMs(p.day))
  const [min, max] = [Math.min(...datas), Math.max(...datas)]
  return min === max ? [min - 86400000, max + 86400000] : [min, max]
})

const maiorValor = computed(() => {
  const todos = pontos.value.flatMap((p) =>
    SERIES.map((s) => p[s.chave]).filter((v) => v !== null && v !== undefined)
  )
  return Math.max(1, ...todos)
})

/** Passo redondo entre as marcas do eixo — 1, 2, 5 ou 10 vezes uma potência de
 *  dez. É o passo que decide o topo, e não o contrário: partir o valor máximo em
 *  quatro daria marcas em 6,25 e 18,75, que fazem o leitor decifrar o eixo em
 *  vez de ler a curva. */
const passoY = computed(() => {
  const bruto = maiorValor.value / 4
  const grandeza = 10 ** Math.floor(Math.log10(bruto))
  const norma = bruto / grandeza
  return (norma <= 1 ? 1 : norma <= 2 ? 2 : norma <= 5 ? 5 : 10) * grandeza
})

const topoY = computed(
  () => Math.max(passoY.value, Math.ceil(maiorValor.value / passoY.value) * passoY.value)
)

const escalaX = (dia) => {
  const [min, max] = dominioX.value
  const util = largura.value - MARGEM.esq - MARGEM.dir
  return MARGEM.esq + ((emMs(dia) - min) / (max - min)) * util
}
const escalaY = (valor) => {
  const util = ALTURA - MARGEM.topo - MARGEM.base
  return MARGEM.topo + util - (valor / topoY.value) * util
}

const ticksY = computed(() => {
  const marcas = []
  for (let v = 0; v <= topoY.value + 1e-9; v += passoY.value) {
    marcas.push({ valor: v, y: escalaY(v) })
  }
  return marcas
})

/** Só as datas que cabem sem colidir: uma a cada N pontos, sempre com a
 *  primeira e a última. */
const ticksX = computed(() => {
  const cabem = Math.max(2, Math.floor((largura.value - MARGEM.esq - MARGEM.dir) / 64))
  const passo = Math.max(1, Math.ceil(pontos.value.length / cabem))
  return pontos.value
    .map((p, i) => ({ dia: p.day, x: escalaX(p.day), rotulo: diaCurto(p.day), i }))
    .filter((t, i) => i % passo === 0 || i === pontos.value.length - 1)
})

/** Os pontos medidos de uma série. Lado não contado não vira ponto — e a linha
 *  liga as duas medições vizinhas, que é o que de fato se sabe. */
function pontosDe(chave) {
  return pontos.value
    .filter((p) => p[chave] !== null && p[chave] !== undefined)
    .map((p) => ({ day: p.day, valor: p[chave], x: escalaX(p.day), y: escalaY(p[chave]) }))
}
const linha = (chave) => pontosDe(chave).map((p) => `${p.x},${p.y}`).join(' ')
const ultimoDe = (chave) => pontosDe(chave).at(-1) || null

// ── Cursor ──────────────────────────────────────────────────────────────

function mover(evento) {
  if (!pontos.value.length) return
  const caixa = evento.currentTarget.getBoundingClientRect()
  const x = evento.clientX - caixa.left

  let perto = pontos.value[0]
  for (const p of pontos.value) {
    if (Math.abs(escalaX(p.day) - x) < Math.abs(escalaX(perto.day) - x)) perto = p
  }
  foco.value = {
    dia: perto.day,
    x: escalaX(perto.day),
    valores: Object.fromEntries(
      SERIES.map((s) => [s.chave, perto[s.chave] ?? null])
    ),
  }
}

/** A dica acompanha o ponto, mas não sai da caixa pelos lados. */
const posicaoDica = computed(() => {
  if (!foco.value) return {}
  const meio = largura.value / 2
  return foco.value.x > meio
    ? { right: `${largura.value - foco.value.x + 12}px`, top: '12px' }
    : { left: `${foco.value.x + 12}px`, top: '12px' }
})

// ── Dados ───────────────────────────────────────────────────────────────

async function carregarInsights() {
  const dados = await merchandisingApi.stockInsights({ days: janela.value })
  insights.value = dados

  // Mantém o cliente escolhido se ele ainda tiver contagem na nova janela;
  // senão cai no que tem mais história, que é onde há o que ver.
  const existe = dados.customers.some((c) => c.customer_id === clienteId.value)
  if (!existe) {
    clienteId.value = dados.customers[0]?.customer_id || null
    produtoId.value = null
  }
}

async function carregarHistorico() {
  if (!clienteId.value) {
    historico.value = null
    return
  }
  carregandoHistorico.value = true
  try {
    historico.value = await merchandisingApi.stockHistory({
      customer_id: clienteId.value,
      product_id: produtoId.value || undefined,
      days: janela.value,
    })
  } finally {
    carregandoHistorico.value = false
  }
}

async function carregarTudo() {
  carregando.value = true
  try {
    await carregarInsights()
    await carregarHistorico()
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar a evolução',
    })
  } finally {
    carregando.value = false
  }
}

function trocarCliente() {
  produtoId.value = null
  carregarHistorico()
}

/** Clicar numa linha dos indicadores leva o gráfico até aquele produto — é a
 *  pergunta seguinte de quem lê "parado há 28 dias": parado em que patamar. */
function verProduto(linha) {
  produtoId.value = linha?.product_id || null
  if (linha?.customer_id) clienteId.value = linha.customer_id
  carregarHistorico()
  nextTick(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
}

function medir() {
  if (caixaGrafico.value) largura.value = caixaGrafico.value.clientWidth || 720
}

onMounted(async () => {
  await carregarTudo()
  await nextTick()
  medir()
  observador = new ResizeObserver(medir)
  if (caixaGrafico.value) observador.observe(caixaGrafico.value)
})

onBeforeUnmount(() => observador?.disconnect())
</script>

<style scoped>
/* Título e controles lado a lado enquanto couberem, empilhados quando não.
   Não dá para deixar isso com `col` + `col-12`: `col` tem `flex-shrink: 1` e
   base zero, então ele encolhe até o título virar uma letra por linha em vez de
   empurrar os controles para baixo. A base de 240px é o que decide a quebra. */
.cabecalho {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.cabecalho__texto {
  flex: 1 1 240px;
  min-width: 0;
}
/* Encolhe só quando já está sozinho na linha e ainda assim não cabe — o chip
   com o nome do produto comprido; aí o nome quebra em vez de vazar da tela. */
.cabecalho__acoes {
  flex: 0 1 auto;
  min-width: 0;
}

.grafico {
  position: relative;
  width: 100%;
}
.grafico svg {
  display: block;
  overflow: visible;
}

.rotulo-eixo {
  font-size: 11px;
  fill: #71717a;
  font-variant-numeric: tabular-nums;
}
.rotulo-ponta {
  font-size: 12px;
  font-weight: 600;
}

.marca-serie {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}

.dica {
  position: absolute;
  background: #fff;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
  box-shadow: 0 2px 8px rgb(0 0 0 / 12%);
  white-space: nowrap;
}

/* Números em coluna precisam alinhar entre as linhas. */
.numero-tabela {
  font-variant-numeric: tabular-nums;
}

/* O QChip tem altura de uma linha e não quebra o texto; nome de produto
   comprido vazava para fora dele. */
.chip-produto {
  height: auto;
  min-height: 1.5em;
  padding-top: 2px;
  padding-bottom: 2px;
}
.chip-produto :deep(.q-chip__content) {
  white-space: normal;
}
</style>
