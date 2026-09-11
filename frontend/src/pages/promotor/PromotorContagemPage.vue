<!--
  Contagem de um cliente, em um dos dois lugares (gôndola ou estoque).

  Um produto por tela: o promotor tem o celular numa mão e o produto na outra,
  então a foto ocupa a metade de cima — grande o bastante para reconhecer a
  embalagem sem ler nada — e a metade de baixo traz os dois quadrados de
  quantidade. São dois porque o cliente quase nunca tem só caixas ou só
  unidades: tem "1 caixa e 5 unidades" do mesmo produto. Arrastar para baixo
  passa para o próximo produto (scroll-snap), e produto sem nenhum número
  digitado simplesmente não é enviado.

  A mesma tela serve para CORRIGIR um envio (rota com `visitId`): o promotor que
  digitou um número errado precisa reencontrar o produto exatamente onde o viu
  da primeira vez. Muda só o que entra e o que sai — os produtos são os que ele
  contou naquele envio, já preenchidos, e o botão grava direto no servidor em
  vez de fechar uma contagem nova.
-->
<template>
  <q-page class="contagem-page">
    <div v-if="loading" class="column items-center justify-center full-height">
      <q-spinner-dots size="40px" color="primary" />
    </div>

    <q-banner
      v-else-if="!products.length && !editando"
      class="bg-grey-2 text-grey-8 rounded-borders q-ma-md"
    >
      <template #avatar><q-icon name="inventory_2" color="grey-6" /></template>
      Nenhum produto cadastrado para este cliente. Fale com o administrador.
    </q-banner>

    <div v-else class="painel-scroll">
      <!-- ── O quadrado, antes de tudo: "aqui não tem produto" ───────── -->
      <section class="declaracao">
        <div class="declaracao-card">
          <q-checkbox
            v-model="semProdutos" size="lg" color="primary"
            :disable="!podeDeclarar"
            @update:model-value="marcarSemProdutos"
          >
            <div class="q-ml-xs">
              <div class="text-weight-bold">Não tem produtos {{ ondeLabel }}</div>
              <div class="text-caption text-grey-7">
                Marque se hoje não há nenhum produto {{ ondeLabel }} deste cliente.
                A contagem é enviada assim mesmo.
              </div>
            </div>
          </q-checkbox>

          <div v-if="!podeDeclarar" class="text-caption text-orange-9 q-mt-sm">
            Este envio foi feito sem produtos. Para contar produtos aqui, faça uma
            contagem nova por este cliente.
          </div>
        </div>
      </section>

      <section v-for="(product, index) in produtosVisiveis" :key="product.id" class="painel">
        <!-- ── Foto: metade de cima da tela ──────────────────────────── -->
        <div class="foto">
          <img
            v-if="imagem(product)"
            :src="imagem(product)" :alt="product.name" class="foto-img"
          />
          <div v-else class="foto-vazia column items-center justify-center">
            <q-icon name="photo_camera" size="52px" color="indigo-4" />
            <div class="text-caption text-indigo-4 q-mt-sm">sem foto</div>
          </div>

          <q-badge class="contador" color="primary" text-color="white">
            {{ index + 1 }} / {{ products.length }}
          </q-badge>

          <!-- Só no primeiro: ensina o gesto e some depois de rolar -->
          <div v-if="index === 0 && products.length > 1" class="dica-scroll">
            <q-icon name="keyboard_double_arrow_down" size="14px" />
            arraste para o próximo
          </div>

          <div class="foto-nome">{{ product.name }}</div>

          <!-- Aviso, e não bloqueio: o bloqueio é no envio. Aparece aqui para
               o promotor não ser surpreendido pela tela de datas no fim. -->
          <q-badge v-if="product.collect_expiry" class="aviso-vencimento" color="orange-9">
            <q-icon name="schedule" size="13px" class="q-mr-xs" />
            vencimento
          </q-badge>
        </div>

        <!-- ── Quantidade: um quadrado para caixas, outro para unidades ─ -->
        <div class="quadros">
          <div v-for="campo in CAMPOS" :key="campo.key" class="quadro column items-center">
            <div class="quadro-titulo row items-center no-wrap">
              <q-icon :name="campo.icon" size="16px" class="q-mr-xs" />
              {{ campo.label }}
            </div>

            <q-input
              v-model="form[product.id][campo.key]"
              outlined dense type="number" inputmode="numeric" min="0" step="1"
              placeholder="—" class="quantidade"
              input-class="text-center text-weight-bolder"
              @update:model-value="persistir(product.id)"
            />

            <div class="row items-center justify-between full-width no-wrap">
              <q-btn
                round unelevated color="grey-3" text-color="dark" icon="remove"
                :aria-label="`Diminuir ${campo.label}`"
                @click="ajustar(product.id, campo.key, -1)"
              />
              <q-btn
                round unelevated color="grey-3" text-color="dark" icon="add"
                :aria-label="`Aumentar ${campo.label}`"
                @click="ajustar(product.id, campo.key, 1)"
              />
            </div>
          </div>
        </div>

        <!-- ── Rodapé do produto: conversão, contagem anterior e limpar ─ -->
        <div class="rodape row items-center no-wrap">
          <div class="col text-caption text-grey-7 ellipsis">
            <span v-if="Number(product.package_size) > 1">
              caixa com {{ formatQtd(product.package_size) }} un
            </span>
            <span v-if="anterior(product)">
              {{ Number(product.package_size) > 1 ? ' · ' : '' }}anterior:
              {{ anterior(product) }}
            </span>
          </div>
          <q-btn
            flat dense no-caps size="sm" color="grey-7" label="Limpar"
            class="col-auto"
            :disable="!preenchido(product.id)"
            @click="limpar(product.id)"
          />
        </div>
      </section>
    </div>

    <!-- ── Barra de envio ──────────────────────────────────────────── -->
    <div v-if="products.length || semProdutos" class="barra-envio row items-center q-gutter-sm">
      <div class="col text-caption text-grey-8">
        <template v-if="semProdutos">
          <div class="text-weight-bold text-body2">Sem produtos</div>
          {{ ondeLabel }}
        </template>
        <template v-else>
          <div class="text-weight-bold text-body2">{{ preenchidos }} de {{ products.length }}</div>
          produtos preenchidos
        </template>
      </div>
      <q-btn
        size="lg" unelevated no-caps class="col-auto"
        :color="editando ? 'primary' : 'positive'"
        :icon="editando ? 'save' : 'cloud_upload'"
        :label="editando ? 'Salvar' : 'Enviar'"
        :disable="!semProdutos && preenchidos === 0" :loading="enviando"
        @click="editando ? confirmarCorrecao() : confirmarEnvio()"
      />
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { mediaUrl } from '@/api/client'
import { merchandisingApi } from '@/api/merchandising'
import { useVisitaStore } from '@/stores/visita'

const props = defineProps({
  // Contagem nova: cliente e lugar vêm da URL
  customerId: { type: String, default: '' },
  visitType: { type: String, default: '' },
  // Correção de um envio já feito: a URL traz só o id da contagem
  visitId: { type: String, default: '' },
})

const editando = computed(() => Boolean(props.visitId))

const router = useRouter()
const $q = useQuasar()
const visita = useVisitaStore()

const CAMPOS = [
  { key: 'boxes', label: 'Caixas', icon: 'inventory_2' },
  { key: 'units', label: 'Unidades', icon: 'widgets' },
]

const products = ref([])
const form = reactive({})
const loading = ref(false)
const enviando = ref(false)

// "Não tem produtos aqui": o quadrado no topo da lista
const semProdutos = ref(false)
// Onde esta contagem é feita. Na correção, vem do envio e não da URL.
const tipo = ref(props.visitType)

const ondeLabel = computed(() => (tipo.value === 'gondola' ? 'na gôndola' : 'no estoque'))

/** Quadrado marcado: não há produto para contar, então não há painel para
 *  mostrar. Some a lista em vez de apagar o que já estava digitado — desmarcar
 *  traz tudo de volta. */
const produtosVisiveis = computed(() => (semProdutos.value ? [] : products.value))

/** Na correção de um envio feito sem produtos não há o que desmarcar: a folha
 *  não traz produto nenhum para preencher. O quadrado fica visível, mostrando o
 *  que foi declarado, mas travado. */
const podeDeclarar = computed(() => !editando.value || products.value.length > 0)

const preenchido = (productId) =>
  form[productId].boxes !== '' || form[productId].units !== ''

const preenchidos = computed(
  () => Object.values(form).filter((item) => item.boxes !== '' || item.units !== '').length
)

const imagem = (product) => mediaUrl(product.image_url)

const formatQtd = (value) =>
  Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

/** "2 cx + 5 un" da última contagem deste mesmo tipo, ou '' se nunca teve. */
function anterior(product) {
  if (product.last_boxes == null && product.last_units == null) return ''
  const partes = []
  if (Number(product.last_boxes)) partes.push(`${formatQtd(product.last_boxes)} cx`)
  if (Number(product.last_units)) partes.push(`${formatQtd(product.last_units)} un`)
  return partes.length ? partes.join(' + ') : '0'
}

/** Grava no rascunho local a cada digitação — sair da tela não perde nada.
 *  Na correção não há rascunho: o que vale é o que está no servidor, e sair da
 *  tela sem salvar tem que deixar o envio como estava. */
function persistir(productId) {
  if (editando.value) return
  visita.setItem(props.customerId, props.visitType, productId, {
    boxes: form[productId].boxes,
    units: form[productId].units,
  })
}

function ajustar(productId, campo, delta) {
  const atual = form[productId][campo]
  // Campo em branco + "menos" continua em branco: quem não contou ainda não
  // está declarando zero.
  if (atual === '' && delta < 0) return
  form[productId][campo] = String(Math.max(0, Number(atual || 0) + delta))
  persistir(productId)
}

/** Grava a marcação no rascunho. O que já estava digitado continua lá: o
 *  promotor que marcou sem querer desmarca e encontra tudo como deixou. */
function marcarSemProdutos(valor) {
  if (editando.value) return
  visita.setSemProdutos(props.customerId, tipo.value, valor)
}

function limpar(productId) {
  form[productId].boxes = ''
  form[productId].units = ''
  persistir(productId)
}

function confirmarEnvio() {
  // Antes de qualquer coisa: o par fechou e há produto que precisa de data?
  // Então esta contagem NÃO sobe agora. Ela fica no rascunho — onde já estava —
  // e só sai do aparelho depois que as datas fecharem.
  const desteLado = totaisPorProduto()
  const pendentes = visita.pendenciaDeVencimento(
    props.customerId, tipo.value, products.value, desteLado
  )
  if (pendentes.length) {
    return $q.dialog({
      title: 'Falta o vencimento',
      message: `${pendentes.length} produto(s) deste cliente estão há tempo demais `
        + 'na loja. Colete a data de vencimento deles — a contagem é enviada '
        + 'logo depois, junto com as datas.',
      cancel: { label: 'Voltar', flat: true, noCaps: true },
      ok: { label: 'Coletar', color: 'orange-9', unelevated: true, noCaps: true },
    }).onOk(() => {
      visita.abrirVencimento(props.customerId, tipo.value, pendentes, desteLado)
      router.push({
        name: 'PromotorVencimento', params: { customerId: props.customerId },
      })
    })
  }

  if (semProdutos.value) {
    return $q.dialog({
      title: 'Enviar sem produtos?',
      message: `Você está informando que hoje não há nenhum produto ${ondeLabel.value} deste cliente.`,
      cancel: { label: 'Voltar', flat: true, noCaps: true },
      ok: { label: 'Enviar', color: 'positive', unelevated: true, noCaps: true },
    }).onOk(enviar)
  }

  const faltando = products.value.length - preenchidos.value
  if (faltando === 0) return enviar()

  $q.dialog({
    title: 'Enviar contagem?',
    message: `${faltando} produto(s) ficaram em branco e não serão enviados.`,
    cancel: { label: 'Voltar', flat: true, noCaps: true },
    ok: { label: 'Enviar', color: 'positive', unelevated: true, noCaps: true },
  }).onOk(enviar)
}

/**
 * O que este lado contou, em unidades, por produto.
 *
 * A conversão de caixas é feita aqui, com o `package_size` que veio na folha —
 * é neste número que o total do par se soma e que as datas de vencimento vão ter
 * de fechar.
 */
function totaisPorProduto() {
  if (semProdutos.value) return {}

  const totais = {}
  products.value.forEach((product) => {
    if (!preenchido(product.id)) return
    const caixas = Number(form[product.id].boxes || 0)
    const unidades = Number(form[product.id].units || 0)
    totais[product.id] = caixas * (Number(product.package_size) || 1) + unidades
  })
  return totais
}

async function enviar() {
  enviando.value = true
  const { sent } = await visita.submit(props.customerId, tipo.value, {
    totaisPorProduto: totaisPorProduto(),
  })
  enviando.value = false

  $q.notify({
    type: sent ? 'positive' : 'warning',
    message: sent
      ? 'Contagem enviada com sucesso.'
      : 'Sem conexão. A contagem foi salva e será enviada automaticamente.',
    position: 'top',
    timeout: 4000,
  })
  router.push({ name: 'PromotorClientes' })
}

/**
 * Correção: substitui as quantidades do envio no servidor.
 *
 * Sem fila offline aqui de propósito — a tela só abriu porque o servidor
 * respondeu, então falhar no salvar quer dizer que a conexão caiu no meio. É
 * mais honesto avisar e deixar o promotor tentar de novo do que guardar a
 * correção num aparelho onde ela pode ficar semanas sem subir.
 */
/** Marcar o quadrado numa correção apaga o que já tinha sido contado —
 *  confirma antes, como no envio. */
function confirmarCorrecao() {
  if (!semProdutos.value || !products.value.length) return salvarCorrecao()

  $q.dialog({
    title: 'Salvar sem produtos?',
    message: `Os ${products.value.length} produto(s) deste envio serão apagados, e a contagem passa a informar que não há nada ${ondeLabel.value}.`,
    cancel: { label: 'Voltar', flat: true, noCaps: true },
    ok: { label: 'Salvar', color: 'primary', unelevated: true, noCaps: true },
  }).onOk(salvarCorrecao)
}

async function salvarCorrecao() {
  // Produto que ficou com os dois campos em branco sai da contagem
  const itens = semProdutos.value
    ? []
    : products.value
      .filter((product) => preenchido(product.id))
      .map((product) => ({
        product_id: product.id,
        boxes: form[product.id].boxes || 0,
        units: form[product.id].units || 0,
      }))

  enviando.value = true
  try {
    await merchandisingApi.updateVisit(props.visitId, {
      no_products: semProdutos.value,
      items: itens,
    })
    $q.notify({ type: 'positive', message: 'Contagem corrigida.', position: 'top' })
    router.push({ name: 'PromotorEnvios' })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail
        || 'Não foi possível salvar. Verifique a conexão e tente de novo.',
      position: 'top',
      timeout: 5000,
    })
  } finally {
    enviando.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const sheet = editando.value
      ? await merchandisingApi.visitSheet(props.visitId)
      : await merchandisingApi.countSheet(props.customerId, props.visitType)

    // O formulário é preenchido ANTES da lista: o template lê `form[id]` em todo
    // painel, e uma renderização com a lista pronta e o formulário vazio quebra.
    // Recupera também o que já tinha sido digitado nesta contagem (mesmo aparelho).
    const draft = editando.value
      ? { items: {} }
      : visita.getDraft(props.customerId, props.visitType)

    // Na correção o tipo vem do envio; na contagem nova, da URL.
    tipo.value = sheet.visit_type || props.visitType
    semProdutos.value = Boolean(editando.value ? sheet.no_products : draft.no_products)

    sheet.products.forEach((product) => {
      // Na correção o ponto de partida é o que está gravado no envio; na
      // contagem nova, o que ficou digitado neste aparelho.
      const gravado = editando.value ? product : draft.items[product.id]
      form[product.id] = {
        boxes: numeroDoCampo(gravado?.boxes),
        units: numeroDoCampo(gravado?.units),
      }
    })

    products.value = sheet.products
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao carregar os produtos',
    })
  } finally {
    loading.value = false
  }
})

/** Valor gravado → texto do campo. Passa por Number porque o servidor manda
 *  decimal ("2.000") e o campo tem que mostrar 2. Nulo é campo em branco. */
function numeroDoCampo(value) {
  return value == null ? '' : String(Number(value))
}
</script>

<style scoped>
.contagem-page {
  overflow: hidden;
}

/* Altura fixa + snap: cada arraste para baixo encaixa o próximo produto.
   `svh` e não `dvh` para o painel não encolher quando o teclado abre. */
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

/* O quadrado do topo: alto o bastante para ser lido de relance, baixo o
   bastante para o primeiro produto aparecer logo abaixo dele. */
.declaracao {
  scroll-snap-align: start;
  padding: 8px 8px 0;
}

.declaracao-card {
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 10px 12px;
}

/* ── Foto ─────────────────────────────────────────────────────────── */
/* Azul claro atrás da foto. As fotos do catálogo vêm com fundo branco chapado;
   `multiply` faz esse branco virar o próprio azul do card (multiplicar por 1 não
   muda nada), então o produto aparece recortado sobre o azul em vez de dentro de
   um quadrado branco. Azul claro e não o da marca justamente por causa do
   multiply: sobre um azul escuro o produto sairia quase preto.
   `isolation` prende a mesclagem ao card — sem ela o blend pega o fundo da
   página junto. */
.foto {
  position: relative;
  flex: 0 0 48%;
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

.aviso-vencimento {
  position: absolute;
  top: 8px;
  left: 8px;
  border-radius: 10px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.contador {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0.75;
}

/* Nome sobre a foto: não rouba altura útil do card */
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

.dica-scroll {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.85);
  font-size: 0.7rem;
  color: rgba(0, 0, 0, 0.6);
  white-space: nowrap;
  pointer-events: none;
}

/* ── Quantidade ───────────────────────────────────────────────────── */
.quadros {
  display: flex;
  gap: 8px;
  flex: 1 1 auto;
  min-height: 0;
}

/* Dois alvos grandes e iguais: o promotor não precisa mirar para acertar. */
.quadro {
  flex: 1 1 0;
  min-width: 0;
  justify-content: space-between;
  border-radius: 14px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  padding: 10px;
}

.quadro-titulo {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: rgba(0, 0, 0, 0.55);
}

.quantidade {
  width: 100%;
}

.quantidade :deep(input) {
  font-size: 2rem;
  padding: 2px 0;
}

/* Some as setinhas nativas do type=number: os botões do app são maiores */
.quantidade :deep(input::-webkit-outer-spin-button),
.quantidade :deep(input::-webkit-inner-spin-button) {
  -webkit-appearance: none;
  margin: 0;
}

.quantidade :deep(input[type='number']) {
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

/* A foto mantém o azul nos dois temas — é ele que dá o contraste com a embalagem. */
.body--dark .quadro,
.body--dark .declaracao-card,
.body--dark .barra-envio {
  background: #1e1e2e;
  border-color: rgba(255, 255, 255, 0.12);
}

.body--dark .quadro-titulo {
  color: rgba(255, 255, 255, 0.7);
}
</style>
