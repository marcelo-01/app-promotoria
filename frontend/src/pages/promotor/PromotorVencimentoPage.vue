<!--
  Coleta de vencimento: a tela que segura a contagem.

  Ela só existe porque o sistema decidiu, olhando o histórico do cliente, que
  aqueles produtos estão há tempo demais na loja. O promotor chegou aqui tentando
  ENVIAR — e a contagem dele está inteira no rascunho, parada, esperando estas
  datas. Nada subiu, e nada sobe enquanto houver número vermelho.

  O número grande é o que ele acabou de contar (gôndola + estoque somados, porque
  a caixa que vence dia 20 pode estar metade em cada lugar). Cada data que ele
  digita desconta dali. Quando chega a zero, fecha e fica verde: aquilo não é um
  resumo bonito, é a prova de que a pilha inteira foi olhada e não sobrou
  mercadoria sem data.

  Mesma anatomia da tela de contagem — foto em cima, números embaixo, um produto
  por tela com scroll-snap — porque é a mesma mão, no mesmo corredor, no mesmo
  minuto.
-->
<template>
  <q-page class="vencimento-page">
    <q-banner
      v-if="!pendencia"
      class="bg-grey-2 text-grey-8 rounded-borders q-ma-md"
    >
      <template #avatar><q-icon name="event_available" color="grey-6" /></template>
      Não há vencimento a coletar neste cliente hoje.
      <template #action>
        <q-btn flat no-caps label="Voltar" @click="voltarAosClientes" />
      </template>
    </q-banner>

    <div v-else class="painel-scroll">
      <section class="aviso">
        <div class="aviso-card row items-start no-wrap">
          <q-icon name="schedule" color="orange-9" size="22px" class="q-mr-sm" />
          <div>
            <div class="text-weight-bold">A contagem ainda não foi enviada</div>
            <div class="text-caption text-grey-7">
              {{ produtos.length }} produto(s) estão há tempo demais nesta loja.
              Informe a data de vencimento de cada unidade contada — a contagem
              sobe junto com as datas, assim que todas fecharem.
            </div>
          </div>
        </div>
      </section>

      <section v-for="(produto, index) in produtos" :key="produto.product_id" class="painel">
        <!-- ── Foto: mesma metade de cima da contagem ─────────────────── -->
        <div class="foto">
          <img
            v-if="imagem(produto)"
            :src="imagem(produto)" :alt="produto.name" class="foto-img"
          />
          <div v-else class="foto-vazia column items-center justify-center">
            <q-icon name="photo_camera" size="52px" color="indigo-4" />
            <div class="text-caption text-indigo-4 q-mt-sm">sem foto</div>
          </div>

          <q-badge class="contador" color="primary" text-color="white">
            {{ index + 1 }} / {{ produtos.length }}
          </q-badge>

          <div class="foto-nome">{{ produto.name }}</div>
        </div>

        <!-- ── O número que tem de chegar a zero ──────────────────────── -->
        <div
          class="saldo row items-center no-wrap"
          :class="fechado(produto) ? 'saldo--fechado' : 'saldo--aberto'"
        >
          <div class="col">
            <div class="saldo-titulo">
              {{ fechado(produto) ? 'Tudo com data' : 'Falta informar' }}
            </div>
            <div class="text-caption saldo-detalhe">
              {{ formatQtd(produto.total) }} un contadas
            </div>
          </div>
          <div class="saldo-numero col-auto">
            {{ formatQtd(restante(produto)) }}
            <q-icon v-if="fechado(produto)" name="check_circle" size="24px" class="q-ml-xs" />
          </div>
        </div>

        <!-- ── As datas ───────────────────────────────────────────────── -->
        <div class="datas">
          <div
            v-for="(linha, i) in linhasDe(produto.product_id)" :key="i"
            class="linha row items-center no-wrap q-gutter-xs"
          >
            <q-input
              v-model="linha.texto" outlined dense mask="##/##/####"
              placeholder="dd/mm/aaaa" class="col campo-data"
              :error="Boolean(linha.texto) && !isoDe(linha.texto)"
              hide-bottom-space
              @update:model-value="gravar(produto.product_id)"
            >
              <template #append>
                <q-icon name="event" class="cursor-pointer" size="20px">
                  <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                    <q-date
                      :model-value="isoDe(linha.texto)" mask="YYYY-MM-DD" minimal
                      @update:model-value="(iso) => escolherData(produto.product_id, i, iso)"
                    />
                  </q-popup-proxy>
                </q-icon>
              </template>
            </q-input>

            <q-input
              v-if="produto.package_size > 1"
              v-model="linha.boxes" outlined dense type="number" inputmode="numeric"
              min="0" step="1" placeholder="cx" class="col-auto campo-qtd"
              input-class="text-center text-weight-bold" hide-bottom-space
              @update:model-value="gravar(produto.product_id)"
            />
            <q-input
              v-model="linha.units" outlined dense type="number" inputmode="numeric"
              min="0" step="1" placeholder="un" class="col-auto campo-qtd"
              input-class="text-center text-weight-bold" hide-bottom-space
              @update:model-value="gravar(produto.product_id)"
            />

            <q-btn
              flat dense round icon="close" color="grey-6" size="sm" class="col-auto"
              aria-label="Remover esta data"
              @click="removerLinha(produto.product_id, i)"
            />
          </div>

          <q-btn
            flat dense no-caps icon="add" color="primary" class="q-mt-xs"
            label="Adicionar outra data"
            @click="adicionarLinha(produto.product_id)"
          />

          <div v-if="excedeu(produto)" class="text-caption text-negative q-mt-xs">
            As datas somam mais do que as {{ formatQtd(produto.total) }} unidades contadas.
          </div>
        </div>

        <div class="rodape text-caption text-grey-7">
          <span v-if="produto.package_size > 1">
            caixa com {{ formatQtd(produto.package_size) }} un ·
          </span>
          {{ motivo(produto) }}
        </div>
      </section>
    </div>

    <!-- ── Barra de envio ──────────────────────────────────────────── -->
    <div v-if="pendencia" class="barra-envio row items-center q-gutter-sm">
      <div class="col text-caption text-grey-8">
        <div class="text-weight-bold text-body2">
          {{ fechados }} de {{ produtos.length }}
        </div>
        produtos com todas as datas
      </div>
      <q-btn
        size="lg" unelevated no-caps class="col-auto" color="positive"
        icon="cloud_upload" label="Enviar"
        :disable="!podeEnviar" :loading="enviando"
        @click="enviar"
      />
    </div>
  </q-page>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useQuasar } from 'quasar'
import { mediaUrl } from '@/api/client'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({
  customerId: { type: String, default: '' },
})

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const enviando = ref(false)

// Quantidade abaixo disto é arredondamento de caixa fracionada, não mercadoria.
const EPS = 0.001

const pendencia = computed(() => visita.vencimentoPendente(props.customerId))
const produtos = computed(() => pendencia.value?.produtos || [])

/** { [productId]: [{ texto, boxes, units }] } — o que está na tela.
 *  `texto` é o que o promotor digita (dd/mm/aaaa); o ISO só aparece na hora de
 *  enviar e de guardar. */
const form = reactive({})

const formatQtd = (value) =>
  Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

const formatDia = (iso) => {
  const [ano, mes, dia] = String(iso).split('-')
  return dia ? `${dia}/${mes}/${ano}` : iso
}

const imagem = (produto) => mediaUrl(produto.image_url)

/** 'dd/mm/aaaa' → 'aaaa-mm-dd', ou null se a data não existe no calendário.
 *  Valida de verdade: 31/02 e 00/00 não passam. */
function isoDe(texto) {
  const partes = String(texto || '').split('/')
  if (partes.length !== 3 || partes[2].length !== 4) return null

  const [dia, mes, ano] = partes.map(Number)
  if (!dia || !mes || !ano) return null

  const data = new Date(ano, mes - 1, dia)
  if (data.getFullYear() !== ano || data.getMonth() !== mes - 1 || data.getDate() !== dia) {
    return null
  }
  return `${ano}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`
}

const linhasDe = (productId) => form[productId] || []

/** Unidades já cobertas por datas válidas neste produto. */
function atribuido(produto) {
  return linhasDe(produto.product_id).reduce((soma, linha) => {
    if (!isoDe(linha.texto)) return soma
    const caixas = Number(linha.boxes || 0)
    const unidades = Number(linha.units || 0)
    return soma + caixas * produto.package_size + unidades
  }, 0)
}

const restante = (produto) => produto.total - atribuido(produto)
const fechado = (produto) => Math.abs(restante(produto)) < EPS
const excedeu = (produto) => restante(produto) < -EPS

const fechados = computed(() => produtos.value.filter(fechado).length)

/** O verde é obrigatório: todo produto fechado em zero, sem sobra e sem excesso.
 *  Deixar passar com sobra seria convidar o promotor a inventar data para sair
 *  da tela — e data inventada estraga justamente o dado que esta tela existe
 *  para criar. */
const podeEnviar = computed(
  () => produtos.value.length > 0 && produtos.value.every(fechado)
)

/**
 * Por que este produto apareceu, em uma linha.
 *
 * É a conta do aparelho dita em português. O promotor não precisa dela para
 * digitar as datas — mas precisa dela para não achar que o aplicativo pediu por
 * acaso, e para conseguir discordar quando o número estiver errado.
 */
function motivo(produto) {
  if (produto.expiry_reason === 'parado') {
    return 'não saiu nenhuma unidade desde a visita passada'
  }
  const dias = Number(produto.expiry_days_to_clear || 0)
  const vida = Number(produto.expiry_shelf_life || 0)
  if (!dias || !vida) return 'o estoque não escoa antes de vencer'
  return `neste ritmo são ~${Math.round(dias)} dias para escoar, `
    + `e o produto vive ${vida}`
}

// ── Edição ──────────────────────────────────────────────────────────────

function adicionarLinha(productId) {
  form[productId] = [...linhasDe(productId), { texto: '', boxes: '', units: '' }]
  gravar(productId)
}

function removerLinha(productId, index) {
  form[productId] = linhasDe(productId).filter((_, i) => i !== index)
  // Sem nenhuma linha a tela fica sem onde digitar — sempre sobra uma em branco.
  if (!form[productId].length) form[productId] = [{ texto: '', boxes: '', units: '' }]
  gravar(productId)
}

function escolherData(productId, index, iso) {
  if (!iso) return
  form[productId][index].texto = formatDia(iso)
  gravar(productId)
}

/** Cada tecla vai para o localStorage: o bloqueio segura a contagem por tempo
 *  indeterminado, e fechar o app no meio não pode custar o que já foi digitado. */
function gravar(productId) {
  visita.setLinhasVencimento(props.customerId, productId, linhasDe(productId))
}

// ── Envio ───────────────────────────────────────────────────────────────

/**
 * As linhas da tela → o que sobe no payload.
 *
 * Datas repetidas no mesmo produto viram uma só, somada: o banco tem única por
 * (envio, produto, data), e o promotor que digitou a mesma data duas vezes quis
 * dizer a mesma coisa que teria dito numa linha só.
 */
function montarExpiries() {
  const juntas = new Map()

  produtos.value.forEach((produto) => {
    linhasDe(produto.product_id).forEach((linha) => {
      const iso = isoDe(linha.texto)
      const caixas = Number(linha.boxes || 0)
      const unidades = Number(linha.units || 0)
      if (!iso || caixas + unidades <= 0) return

      const chave = `${produto.product_id}|${iso}`
      const atual = juntas.get(chave)
      if (atual) {
        atual.boxes += caixas
        atual.units += unidades
      } else {
        juntas.set(chave, {
          product_id: produto.product_id,
          expires_at: iso,
          boxes: caixas,
          units: unidades,
        })
      }
    })
  })

  return [...juntas.values()]
}

async function enviar() {
  if (!podeEnviar.value) return

  const { visit_type: visitType } = pendencia.value
  const totaisPorProduto = pendencia.value.totais_lado

  enviando.value = true
  const { sent } = await visita.submit(props.customerId, visitType, {
    totaisPorProduto,
    expiries: montarExpiries(),
  })
  enviando.value = false

  // A coleta só se fecha depois que a contagem saiu do rascunho — enviada ou na
  // fila. Antes disso, as duas continuam sendo a mesma pendência.
  visita.fecharVencimento(props.customerId)

  $q.notify({
    type: sent ? 'positive' : 'warning',
    message: sent
      ? 'Contagem e vencimentos enviados.'
      : 'Sem conexão. A contagem e as datas foram salvas e serão enviadas automaticamente.',
    position: 'top',
    timeout: 4000,
  })
  router.push({ name: 'PromotorClientes' })
}

const voltarAosClientes = () => router.push({ name: 'PromotorClientes' })

// Sair daqui não perde nada — mas o promotor precisa saber que a contagem dele
// continua parada, e não enviada.
onBeforeRouteLeave((to, from, next) => {
  if (!pendencia.value || enviando.value) return next()

  $q.dialog({
    title: 'Sair sem enviar?',
    message: 'A contagem deste cliente fica guardada neste aparelho e NÃO será '
      + 'enviada enquanto faltar vencimento. Você pode voltar pelo card do '
      + 'cliente e terminar.',
    cancel: { label: 'Continuar aqui', flat: true, noCaps: true },
    ok: { label: 'Sair', color: 'grey-8', unelevated: true, noCaps: true },
  })
    .onOk(() => next())
    .onCancel(() => next(false))
})

// ── Carga ───────────────────────────────────────────────────────────────

/** Monta o formulário a partir do que está guardado. Roda também quando a
 *  pendência aparece depois (recarregar a página direto nesta URL). */
watch(
  pendencia,
  (atual) => {
    if (!atual) return
    atual.produtos.forEach((produto) => {
      const guardadas = atual.linhas?.[produto.product_id]
      form[produto.product_id] = guardadas?.length
        ? guardadas.map((linha) => ({ ...linha }))
        : [{ texto: '', boxes: '', units: '' }]
    })
  },
  { immediate: true }
)
</script>

<style scoped>
/* Mesma moldura da contagem: painel de altura fixa entre o cabeçalho e a barra
   de envio, com scroll-snap. `svh` para o teclado não encolher o painel. */
.painel-scroll {
  height: calc(100vh - 50px - 78px);
  height: calc(100svh - 50px - 78px);
  overflow-y: auto;
  scroll-snap-type: y mandatory;
  -webkit-overflow-scrolling: touch;
}

.painel {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  padding: 8px;
  gap: 8px;
}

.aviso {
  scroll-snap-align: start;
  padding: 8px 8px 0;
}

.aviso-card {
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-left: 4px solid #e65100;
  padding: 10px 12px;
}

/* ── Foto ─────────────────────────────────────────────────────────── */
.foto {
  position: relative;
  flex: 0 0 34%;
  min-height: 0;
  border-radius: 14px;
  overflow: hidden;
  isolation: isolate;
  background: #c5cae9;
}

.foto-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  mix-blend-mode: multiply;
}

.foto-vazia {
  height: 100%;
}

.contador {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0.75;
}

.foto-nome {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 24px 12px 10px;
  color: #fff;
  font-weight: 700;
  font-size: 1rem;
  line-height: 1.2;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.82), rgba(0, 0, 0, 0));
}

/* ── O saldo ──────────────────────────────────────────────────────── */
/* Vermelho enquanto falta, verde quando fecha. É o único lugar da tela em que a
   cor carrega informação sozinha — por isso vem com rótulo e ícone junto, e não
   só a cor. */
.saldo {
  flex: 0 0 auto;
  border-radius: 14px;
  padding: 10px 14px;
  border: 1px solid;
}

.saldo--aberto {
  background: #ffebee;
  border-color: #ef9a9a;
  color: #b71c1c;
}

.saldo--fechado {
  background: #e8f5e9;
  border-color: #a5d6a7;
  color: #1b5e20;
}

.saldo-titulo {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.saldo-detalhe {
  opacity: 0.85;
}

.saldo-numero {
  display: flex;
  align-items: center;
  font-size: 2.4rem;
  font-weight: 800;
  line-height: 1;
}

/* ── As datas ─────────────────────────────────────────────────────── */
.datas {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 10px;
}

.linha + .linha {
  margin-top: 6px;
}

.campo-data :deep(input) {
  font-size: 1rem;
}

.campo-qtd {
  width: 62px;
}

/* Some as setinhas nativas do type=number, como na contagem */
.campo-qtd :deep(input::-webkit-outer-spin-button),
.campo-qtd :deep(input::-webkit-inner-spin-button) {
  -webkit-appearance: none;
  margin: 0;
}

.campo-qtd :deep(input[type='number']) {
  -moz-appearance: textfield;
}

.rodape {
  flex: 0 0 auto;
  min-height: 26px;
  padding: 0 4px;
}

/* ── Barra de envio ───────────────────────────────────────────────── */
.barra-envio {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 78px;
  padding: 0 12px calc(env(safe-area-inset-bottom, 0px)) 12px;
  background: #fff;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
  z-index: 10;
}

.body--dark .aviso-card,
.body--dark .datas,
.body--dark .barra-envio {
  background: #1e1e2e;
  border-color: rgba(255, 255, 255, 0.12);
}

.body--dark .aviso-card {
  border-left-color: #e65100;
}

/* No escuro o fundo claro do saldo cegaria; o que carrega a informação é a
   borda e o texto. */
.body--dark .saldo--aberto {
  background: rgba(183, 28, 28, 0.18);
  color: #ff8a80;
}

.body--dark .saldo--fechado {
  background: rgba(27, 94, 32, 0.18);
  color: #a5d6a7;
}
</style>
