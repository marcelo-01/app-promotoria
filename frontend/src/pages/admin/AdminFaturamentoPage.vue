<!--
  As planilhas do ERP: o que ENTROU em cada cliente.

  Esta é a metade da história que a contagem do promotor nunca viu. A diferença
  entre duas contagens é líquida — sem saber o que entrou, "o cliente vendeu 20"
  e "o cliente vendeu 40 e recebeu 20" são o mesmo número. Com as notas, a
  contagem deixa de ser a fonte dos lotes e vira a conferência deles.

  A tela é deliberadamente em dois tempos. Anexar só LÊ e relata; nada vai para o
  banco até alguém confirmar. Um arquivo errado anexado por engano não pode sujar
  a base antes de um par de olhos passar por ele.

  E o relatório trata o que não casou como TAREFA, não como erro: cada código
  desconhecido vem com quantas peças ficaram de fora, porque é esse número que
  diz se vale a pena cadastrar aquele item ou ignorá-lo.

  São duas planilhas, e não duas telas: o fluxo é idêntico (anexar, conferir,
  confirmar) e o relatório é o mesmo. Só muda o arquivo que o ERP gera e o que
  cada um deixa de fora.
-->
<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Planilhas do ERP</div>
    <div class="text-caption text-grey-7 q-mb-md">
      O que saiu para cada cliente, vendido ou de brinde. É por aqui que o sistema
      sabe o que entrou na loja — sem isso, ele só consegue adivinhar pela
      variação do estoque.
    </div>

    <q-btn-toggle
      v-model="origem" no-caps unelevated spread
      toggle-color="primary" color="white" text-color="grey-8"
      class="seletor q-mb-md"
      :options="ORIGENS"
      :disable="lendo || gravando"
      @update:model-value="limpar"
    />

    <!-- ── Anexar ─────────────────────────────────────────────────────── -->
    <q-card flat bordered class="q-mb-md">
      <q-card-section class="row items-center q-col-gutter-md">
        <div class="col-12 col-md">
          <div class="text-caption text-grey-7 q-mb-sm">{{ origemAtual.ajuda }}</div>
          <q-file
            v-model="arquivo" outlined dense clearable
            accept=".xlsx,.xlsm" :label="`${origemAtual.label} (.xlsx)`"
            :disable="lendo || gravando"
            @update:model-value="aoAnexar"
          >
            <template #prepend><q-icon name="attach_file" /></template>
          </q-file>
        </div>
        <div class="col-12 col-md-auto">
          <q-btn
            unelevated no-caps color="primary" icon="upload_file"
            label="Conferir planilha"
            :loading="lendo" :disable="!arquivo || gravando"
            @click="conferir"
          />
        </div>
      </q-card-section>

      <!-- ── O que já entrou ───────────────────────────────────────────── -->
      <q-separator />
      <q-card-section class="q-pb-none">
        <div class="row items-center no-wrap">
          <div class="col text-subtitle2 text-weight-bold">
            Planilhas de {{ origemAtual.label.toLowerCase() }} já importadas
          </div>
          <q-chip v-if="importadas.length" dense square color="positive" text-color="white">
            {{ importadas.length }}
          </q-chip>
        </div>
        <div class="text-caption text-grey-7">
          Cada linha é um arquivo que entrou no sistema. Se a sua não está aqui,
          ela ainda não foi importada.
        </div>
      </q-card-section>

      <q-card-section v-if="carregandoImportadas && !importadas.length" class="text-caption text-grey-6">
        <q-spinner-dots size="18px" color="primary" /> Buscando…
      </q-card-section>

      <q-card-section v-else-if="!importadas.length" class="text-caption text-grey-6">
        <q-icon name="inbox" /> Nenhuma planilha de
        {{ origemAtual.label.toLowerCase() }} foi importada ainda.
      </q-card-section>

      <q-list v-else separator dense style="max-height: 320px; overflow-y: auto">
        <q-item
          v-for="(imp, i) in importadas" :key="imp.id"
          :class="{ 'bg-green-1': i === 0 && recemImportada === imp.id }"
        >
          <q-item-section avatar>
            <q-icon name="task" color="positive" />
          </q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-medium ellipsis">{{ imp.file_name }}</q-item-label>
            <q-item-label caption>
              {{ formatQuando(imp.imported_at) }}
              <span v-if="imp.imported_by"> · por {{ imp.imported_by }}</span>
              <span v-if="imp.first_day">
                · período {{ formatDia(imp.first_day) }}<template
                  v-if="imp.last_day !== imp.first_day"> a {{ formatDia(imp.last_day) }}</template>
              </span>
            </q-item-label>
          </q-item-section>
          <q-item-section side class="text-right">
            <q-item-label class="text-weight-bold text-positive">
              {{ imp.matched_lines }} linha(s)
            </q-item-label>
            <q-item-label caption>{{ formatQtd(imp.matched_quantity) }} pç</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>

      <q-inner-loading :showing="lendo">
        <q-spinner-dots size="32px" color="primary" />
      </q-inner-loading>
    </q-card>

    <!-- ── Arquivo não entendido ──────────────────────────────────────── -->
    <q-banner v-if="relato?.missing_columns?.length" class="bg-red-1 rounded-borders q-mb-md">
      <template #avatar><q-icon name="report" color="negative" /></template>
      <div class="text-weight-bold">Esta planilha não tem as colunas esperadas.</div>
      Faltou: {{ relato.missing_columns.join(', ') }}.
      Confira se a exportação é a de faturamento por item.
    </q-banner>

    <template v-else-if="relato">
      <!-- ── O resumo ─────────────────────────────────────────────────── -->
      <q-card flat bordered class="q-mb-md">
        <q-card-section>
          <div class="row items-center justify-between q-mb-sm">
            <div class="text-subtitle1 text-weight-bold">
              {{ relato.saved ? 'Importado' : 'Prévia — nada foi gravado ainda' }}
            </div>
            <q-chip
              dense square :color="relato.saved ? 'positive' : 'orange-9'" text-color="white"
              :icon="relato.saved ? 'check_circle' : 'visibility'"
            >
              {{ relato.saved ? 'gravado' : 'só leitura' }}
            </q-chip>
          </div>

          <div class="row q-col-gutter-md">
            <div v-for="n in numeros" :key="n.label" class="col-6 col-md-3">
              <div class="numero" :class="n.cor">{{ n.valor }}</div>
              <div class="text-caption text-grey-7">{{ n.label }}</div>
            </div>
          </div>

          <q-banner v-if="descartePorPeso" dense class="bg-orange-1 rounded-borders q-mt-md">
            <template #avatar><q-icon name="scale" color="orange-9" /></template>
            <b>{{ descartePorPeso }} linha(s) não puderam ser contadas em peças.</b>
            A planilha de brindes traz a quantidade na unidade de faturamento, e
            nessas linhas ela é peso (queijo e manteiga a granel são vendidos por
            quilo). Virar "32,75 peças" de um queijo de 4&nbsp;kg inflaria a
            entrada em oito vezes, então elas ficam de fora. A correção é pedir a
            coluna de peças também nesta exportação.
          </q-banner>

          <div v-if="relato.first_day" class="text-caption text-grey-7 q-mt-md">
            Período da planilha: {{ formatDia(relato.first_day) }}
            <span v-if="relato.last_day !== relato.first_day">
              a {{ formatDia(relato.last_day) }}
            </span>
            · {{ relato.ignored_cfop }} linha(s) ficaram de fora pelo CFOP.
          </div>
        </q-card-section>

        <q-card-actions v-if="!relato.saved" align="right" class="q-pa-md q-pt-none">
          <q-btn flat no-caps label="Descartar" color="grey-8" @click="limpar" />
          <q-btn
            unelevated no-caps color="positive" icon="save"
            :label="`Importar ${relato.matched_lines} linha(s)`"
            :loading="gravando" :disable="!relato.matched_lines"
            @click="importar"
          />
        </q-card-actions>
      </q-card>

      <!-- ── O que entrou, por motivo (só a planilha de brindes traz) ──── -->
      <q-card v-if="relato.by_reason?.length" flat bordered class="q-mb-md">
        <q-card-section class="q-pb-none">
          <div class="text-subtitle2 text-weight-bold">Brindes por motivo</div>
          <div class="text-caption text-grey-7">
            O que passou pelo filtro de CFOP. Confira aqui se algum motivo entrou
            (ou ficou de fora) indevidamente.
          </div>
        </q-card-section>
        <q-list separator dense>
          <q-item v-for="m in relato.by_reason" :key="m.code">
            <q-item-section>
              <q-item-label>{{ m.code }}</q-item-label>
            </q-item-section>
            <q-item-section side class="text-right">
              <q-item-label class="text-weight-bold text-primary">
                {{ formatQtd(m.quantity) }} pç
              </q-item-label>
              <q-item-label caption>{{ m.lines }} linha(s)</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>

      <!-- ── O que ficou de fora ──────────────────────────────────────── -->
      <div class="row q-col-gutter-md">
        <div v-for="lista in pendencias" :key="lista.titulo" class="col-12 col-md-6">
          <q-card flat bordered>
            <q-card-section class="q-pb-none">
              <div class="row items-center no-wrap">
                <div class="col text-subtitle2 text-weight-bold">{{ lista.titulo }}</div>
                <q-chip v-if="lista.itens.length" dense square color="orange-9" text-color="white">
                  {{ lista.itens.length }}
                </q-chip>
              </div>
              <div class="text-caption text-grey-7">{{ lista.ajuda }}</div>
            </q-card-section>

            <q-card-section v-if="!lista.itens.length" class="text-caption text-positive">
              <q-icon name="check_circle" /> Tudo casou com o cadastro.
            </q-card-section>

            <q-list v-else separator dense style="max-height: 340px; overflow-y: auto">
              <q-item v-for="item in lista.itens" :key="item.code">
                <q-item-section>
                  <q-item-label class="text-weight-medium">{{ item.name }}</q-item-label>
                  <q-item-label caption>
                    {{ lista.rotulo }} {{ item.code }}
                    <span v-if="item.document"> · CNPJ {{ formatDoc(item.document) }}</span>
                  </q-item-label>
                </q-item-section>
                <q-item-section side class="text-right">
                  <q-item-label class="text-weight-bold text-orange-9">
                    {{ formatQtd(item.quantity) }} pç
                  </q-item-label>
                  <q-item-label caption>{{ item.lines }} linha(s)</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card>
        </div>
      </div>

      <q-banner v-if="temPendencia" class="bg-blue-1 rounded-borders q-mt-md">
        <template #avatar><q-icon name="lightbulb" color="primary" /></template>
        Para trazer esses itens, preencha o <b>código do ERP</b> no cadastro do
        produto e o <b>CNPJ</b> no cadastro do cliente, e anexe a planilha de
        novo. Reanexar não duplica nada — cada linha é identificada pelo número
        da venda.
        <template #action>
          <q-btn flat no-caps label="Ir para Cadastros" :to="{ name: 'AdminCadastros' }" />
        </template>
      </q-banner>
    </template>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const ORIGENS = [
  {
    value: 'venda',
    label: 'Faturamento',
    ajuda: 'A exportação de vendas por item. Entram as saídas de mercadoria; '
      + 'devolução fica de fora — ela só é lançada no ERP quando a mercadoria '
      + 'volta ao estoque, dias depois.',
  },
  {
    value: 'brinde',
    label: 'Brindes',
    ajuda: 'A exportação de brindes. Entram só as remessas ao cliente (CFOP 5910 '
      + 'e 6910); transferência entre filiais, retorno, consumo interno e baixa '
      + 'por perda ficam de fora, porque não põem mercadoria em loja nenhuma.',
  },
]

const origem = ref('venda')
const arquivo = ref(null)
const relato = ref(null)
const lendo = ref(false)
const gravando = ref(false)

// As planilhas desta origem que já entraram — o que responde "essa eu já
// mandei?" sem precisar anexar de novo para descobrir.
const importadas = ref([])
const carregandoImportadas = ref(false)
// A que acabou de entrar nesta sessão, para destacar na lista.
const recemImportada = ref(null)

const origemAtual = computed(
  () => ORIGENS.find((o) => o.value === origem.value) || ORIGENS[0]
)

const formatQtd = (v) =>
  Number(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

const formatDia = (iso) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('pt-BR') : '—'

const formatQuando = (iso) =>
  iso
    ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
    : '—'

/** 14 dígitos viram CNPJ; 11, CPF. Qualquer outra coisa sai como veio. */
function formatDoc(digitos) {
  const d = String(digitos || '')
  if (d.length === 14) {
    return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
  }
  if (d.length === 11) {
    return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`
  }
  return d
}

const numeros = computed(() => {
  const r = relato.value
  if (!r) return []
  return [
    { label: 'linhas na planilha', valor: r.total_lines, cor: 'text-grey-8' },
    {
      label: 'entraram no sistema',
      valor: r.matched_lines,
      cor: r.matched_lines ? 'text-positive' : 'text-grey-6',
    },
    {
      label: 'sem cadastro',
      valor: r.usable_lines - r.matched_lines,
      cor: r.usable_lines - r.matched_lines ? 'text-orange-9' : 'text-grey-6',
    },
    { label: 'peças contabilizadas', valor: formatQtd(r.matched_quantity), cor: 'text-primary' },
  ]
})

/** A planilha de brindes não traz contagem de peças — só quantidade na unidade
 *  de faturamento, que mistura unidades e quilos. Linha fracionada é peso, e é
 *  descartada em vez de virar peça inventada. */
const descartePorPeso = computed(() => relato.value?.ignored_weight || 0)

const pendencias = computed(() => [
  {
    titulo: 'Produtos sem cadastro',
    ajuda: 'Códigos que a planilha traz e este app não conhece.',
    rotulo: 'código',
    itens: relato.value?.unknown_products || [],
  },
  {
    titulo: 'Clientes sem cadastro',
    ajuda: 'CNPJ da planilha sem cliente correspondente aqui.',
    rotulo: 'cliente',
    itens: relato.value?.unknown_customers || [],
  },
])

const temPendencia = computed(() =>
  pendencias.value.some((lista) => lista.itens.length > 0)
)

/** Anexar já confere: o passo separado não acrescenta nada e esconde o resultado
 *  atrás de mais um clique. */
function aoAnexar(file) {
  relato.value = null
  if (file) conferir()
}

function limpar() {
  arquivo.value = null
  relato.value = null
  carregarImportadas()
}

/** A lista de baixo é por origem: trocar de aba troca a lista. */
async function carregarImportadas() {
  carregandoImportadas.value = true
  try {
    importadas.value = await merchandisingApi.listInvoiceImports(origem.value)
  } catch {
    importadas.value = []
    $q.notify({ type: 'negative', message: 'Não foi possível listar as planilhas importadas.' })
  } finally {
    carregandoImportadas.value = false
  }
}

onMounted(carregarImportadas)

async function conferir() {
  if (!arquivo.value) return
  lendo.value = true
  try {
    relato.value = await merchandisingApi.previewInvoices(arquivo.value, origem.value)
  } catch (error) {
    relato.value = null
    $q.notify({ type: 'negative', message: error.message, timeout: 6000 })
  } finally {
    lendo.value = false
  }
}

async function importar() {
  gravando.value = true
  try {
    relato.value = await merchandisingApi.importInvoices(arquivo.value, origem.value)
    $q.notify({
      type: 'positive',
      message: `${relato.value.matched_lines} linha(s) importada(s).`,
      position: 'top',
    })
    // O recibo entra na lista de baixo: é ele que prova que a planilha entrou.
    await carregarImportadas()
    recemImportada.value = importadas.value[0]?.id || null
  } catch (error) {
    $q.notify({ type: 'negative', message: error.message, timeout: 6000 })
  } finally {
    gravando.value = false
  }
}
</script>

<style scoped>
.seletor {
  max-width: 26rem;
  border: 1px solid rgba(0, 0, 0, 0.14);
  border-radius: 4px;
  overflow: hidden;
}

.numero {
  font-size: 1.8rem;
  font-weight: 800;
  line-height: 1.1;
}
</style>
