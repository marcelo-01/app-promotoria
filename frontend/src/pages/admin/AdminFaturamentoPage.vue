<!--
  O faturamento e os brindes do ERP: o que ENTROU em cada cliente.

  Esta é a metade da história que a contagem do promotor nunca viu. A diferença
  entre duas contagens é líquida — sem saber o que entrou, "o cliente vendeu 20"
  e "o cliente vendeu 40 e recebeu 20" são o mesmo número. Com as notas, a
  contagem deixa de ser a fonte dos lotes e vira a conferência deles.

  As notas chegam sozinhas: o computador da empresa lê a cópia do banco do ERP
  e manda as dos últimos 120 dias (`sync/sincronizar-faturamento-e-brindes.bat`),
  e cada envio troca as do período inteiro. Esta tela não grava nada — ela diz
  se os números estão em dia e mostra o relato do último envio.

  O relato trata o que não casou como TAREFA, não como erro: cada código
  desconhecido vem com quantas peças ficaram de fora, porque é esse número que
  diz se vale a pena cadastrar aquele item ou ignorá-lo.

  Até nov/2026 as notas vinham em planilhas anexadas aqui. O anexo saiu porque
  os dois caminhos juntos contariam a mesma nota duas vezes: a coluna EMPRESA
  da exportação vinha deslocada, e a chave da planilha não casa com a do banco.
-->
<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Faturamento e brindes do ERP</div>
    <div class="text-caption text-grey-7 q-mb-md">
      O que saiu para cada cliente, vendido ou de brinde. É por aqui que o sistema
      sabe o que entrou na loja — sem isso, ele só consegue adivinhar pela
      variação do estoque. As notas chegam sozinhas do computador da empresa, que
      lê a cópia do banco do ERP.
    </div>

    <q-btn-toggle
      v-model="origem" no-caps unelevated spread
      toggle-color="primary" color="white" text-color="grey-8"
      class="seletor q-mb-md"
      :options="ORIGENS"
      :disable="carregando"
      @update:model-value="carregar"
    />

    <!-- ── Está em dia? ────────────────────────────────────────────────── -->
    <q-card v-if="carregando && !carregado" flat bordered class="q-mb-md">
      <q-card-section class="text-caption text-grey-6">
        <q-spinner-dots size="18px" color="primary" /> Buscando…
      </q-card-section>
    </q-card>

    <q-banner v-else-if="!ultima" class="bg-blue-1 rounded-borders q-mb-md">
      <template #avatar><q-icon name="sync" color="primary" /></template>
      <div class="text-weight-bold">
        Nenhuma sincronização de {{ origemAtual.label.toLowerCase() }} chegou ainda.
      </div>
      No computador da empresa, dê dois cliques em
      <b>sincronizar-faturamento-e-brindes.bat</b>, na pasta <b>sync</b> do
      app-promotoria. Ele lê a cópia do banco do ERP e manda as notas de venda e
      de brinde dos últimos 120 dias.
    </q-banner>

    <q-banner
      v-else
      class="rounded-borders q-mb-md"
      :class="atraso ? 'bg-orange-1' : 'bg-green-1'"
    >
      <template #avatar>
        <q-icon
          :name="atraso ? 'update' : 'cloud_done'"
          :color="atraso ? 'orange-9' : 'positive'"
        />
      </template>
      <div class="text-weight-bold">
        Última sincronização em {{ formatQuando(ultima.imported_at) }}
      </div>
      <span v-if="ultima.copy_at">Cópia do banco do ERP de {{ formatQuando(ultima.copy_at) }} · </span>
      notas de {{ formatDia(ultima.first_day) }} a {{ formatDia(ultima.last_day) }}.
      <div v-if="atraso" class="q-mt-xs">
        As notas mais recentes que chegaram são de {{ formatDia(ultima.last_day) }},
        há {{ atraso }} dias. Rode o <b>sincronizar-faturamento-e-brindes.bat</b>
        no computador da empresa, com a cópia do banco do dia.
      </div>
    </q-banner>

    <!-- ── O relato do último envio ──────────────────────────────────────── -->
    <template v-if="relato">
      <q-card flat bordered class="q-mb-md">
        <q-card-section>
          <div class="text-subtitle1 text-weight-bold q-mb-sm">
            O que entrou no último envio
          </div>

          <div class="row q-col-gutter-md">
            <div v-for="n in numeros" :key="n.label" class="col-6 col-md-3">
              <div class="numero" :class="n.cor">{{ n.valor }}</div>
              <div class="text-caption text-grey-7">{{ n.label }}</div>
            </div>
          </div>

          <div class="text-caption text-grey-7 q-mt-md">
            {{ formatQtd(relato.matched_customers) }} cliente(s) deste app receberam
            mercadoria no período. O envio trocou as
            {{ formatQtd(relato.previous_lines) }} entrada(s) que havia de
            {{ formatDia(relato.first_day) }} a {{ formatDia(relato.last_day) }}.
            <span v-if="relato.ignored_cfop">
              {{ formatQtd(relato.ignored_cfop) }} item(ns) ficaram de fora pelo
              CFOP ({{ origemAtual.cfop }}).
            </span>
            <span v-if="relato.ignored_reason">
              {{ formatQtd(relato.ignored_reason) }} item(ns) de brinde de outro
              motivo também — só entra a troca de vencido e de danificado.
            </span>
            <span v-if="relato.ignored_incomplete">
              {{ formatQtd(relato.ignored_incomplete) }} sem a contagem de peças.
            </span>
          </div>

          <!-- Sem nenhuma linha casada não há o que contar — e um zero sem
               explicação parece defeito. O motivo tem de estar aqui. -->
          <q-banner
            v-if="!relato.matched_lines && relato.usable_lines"
            class="bg-orange-1 rounded-borders q-mt-md"
          >
            <template #avatar><q-icon name="link_off" color="orange-9" /></template>
            <div class="text-weight-bold">
              Nenhum item casou com o cadastro — por isso nada entrou.
            </div>
            As notas identificam o produto pelo <b>código do ERP</b> e o cliente
            pelo <b>CNPJ</b>, e o sistema só aproveita o item quando encontra os
            dois no cadastro. Preencha o código no produto e o CNPJ no cliente
            (as listas abaixo dizem quais faltam, a começar pelos que mais pesam);
            o próximo envio já os traz.
            <template #action>
              <q-btn flat no-caps label="Ir para Cadastros" :to="{ name: 'AdminCadastros' }" />
            </template>
          </q-banner>
        </q-card-section>
      </q-card>

      <!-- ── Brindes por motivo: o que entrou e o que o motivo deixou de fora ── -->
      <q-card
        v-if="relato.by_reason?.length || relato.ignored_by_reason?.length"
        flat bordered class="q-mb-md"
      >
        <q-card-section class="q-pb-none">
          <div class="text-subtitle2 text-weight-bold">Brindes por motivo</div>
          <div class="text-caption text-grey-7">
            Só entra o brinde de troca — vencido ou danificado. Doação,
            degustação, pagamento de contrato e brinde sem motivo saem com o mesmo
            CFOP, mas não viram mercadoria na gôndola. Confira aqui se algum
            motivo entrou (ou ficou de fora) indevidamente.
          </div>
        </q-card-section>
        <q-list separator dense>
          <q-item-label v-if="relato.by_reason?.length" header class="q-py-sm">
            Entraram, nas lojas deste app
          </q-item-label>
          <q-item v-for="m in relato.by_reason" :key="`entrou-${m.code}`">
            <q-item-section>
              <q-item-label>{{ m.code }}</q-item-label>
            </q-item-section>
            <q-item-section side class="text-right">
              <q-item-label class="text-weight-bold text-primary">
                {{ formatQtd(m.quantity) }} pç
              </q-item-label>
              <q-item-label caption>{{ m.lines }} item(ns)</q-item-label>
            </q-item-section>
          </q-item>
          <q-item-label v-if="relato.ignored_by_reason?.length" header class="q-py-sm">
            Não entram, em todas as lojas do ERP
          </q-item-label>
          <q-item v-for="m in relato.ignored_by_reason" :key="`fora-${m.code}`">
            <q-item-section>
              <q-item-label class="text-grey-8">{{ m.code }}</q-item-label>
            </q-item-section>
            <q-item-section side class="text-right">
              <q-item-label class="text-grey-7">{{ formatQtd(m.quantity) }} pç</q-item-label>
              <q-item-label caption>{{ m.lines }} item(ns)</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>

      <!-- ── O que ficou de fora ──────────────────────────────────────── -->
      <div class="row q-col-gutter-md q-mb-md">
        <div v-for="lista in pendencias" :key="lista.titulo" class="col-12 col-md-6">
          <q-card flat bordered>
            <q-card-section class="q-pb-none">
              <div class="row items-center no-wrap">
                <div class="col text-subtitle2 text-weight-bold">{{ lista.titulo }}</div>
                <q-chip v-if="lista.total" dense square color="orange-9" text-color="white">
                  {{ formatQtd(lista.total) }}
                </q-chip>
              </div>
              <div class="text-caption text-grey-7">{{ lista.ajuda }}</div>
              <div v-if="lista.total > lista.itens.length" class="text-caption text-grey-7">
                Mostrando os {{ lista.itens.length }} com mais itens.
              </div>
            </q-card-section>

            <q-card-section v-if="!lista.total" class="text-caption text-positive">
              <q-icon name="check_circle" /> Tudo casou com o cadastro.
            </q-card-section>

            <q-list v-else separator dense style="max-height: 340px; overflow-y: auto">
              <q-item v-for="item in lista.itens" :key="item.code">
                <q-item-section>
                  <q-item-label class="text-weight-medium quebra">{{ item.name }}</q-item-label>
                  <q-item-label caption>
                    {{ lista.rotulo }} {{ item.code }}
                    <span v-if="item.document"> · CNPJ {{ formatDoc(item.document) }}</span>
                  </q-item-label>
                </q-item-section>
                <q-item-section side class="text-right">
                  <q-item-label class="text-weight-bold text-orange-9">
                    {{ formatQtd(item.quantity) }} pç
                  </q-item-label>
                  <q-item-label caption>{{ item.lines }} item(ns)</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card>
        </div>
      </div>

      <!-- Quando nada casou, o aviso já está em cima, junto dos números. -->
      <q-banner v-if="temPendencia && relato.matched_lines" class="bg-blue-1 rounded-borders q-mb-md">
        <template #avatar><q-icon name="lightbulb" color="primary" /></template>
        Para trazer esses itens, preencha o <b>código do ERP</b> no cadastro do
        produto e o <b>CNPJ</b> no cadastro do cliente. O próximo envio já os
        traz — cada um troca as notas do período inteiro, sem duplicar nada.
        <template #action>
          <q-btn flat no-caps label="Ir para Cadastros" :to="{ name: 'AdminCadastros' }" />
        </template>
      </q-banner>
    </template>

    <!-- ── O que já chegou ─────────────────────────────────────────────── -->
    <q-card flat bordered>
      <q-card-section class="q-pb-none">
        <div class="row items-center no-wrap">
          <div class="col text-subtitle2 text-weight-bold">
            Envios de {{ origemAtual.label.toLowerCase() }} recebidos
          </div>
          <q-chip v-if="recebidos.length" dense square color="positive" text-color="white">
            {{ recebidos.length }}
          </q-chip>
        </div>
        <div class="text-caption text-grey-7">
          Cada linha é um envio que entrou no sistema, do mais recente para o mais
          antigo — e, antes da sincronização, as planilhas anexadas à mão.
        </div>
      </q-card-section>

      <q-card-section v-if="!recebidos.length" class="text-caption text-grey-6">
        <q-icon name="inbox" /> Nada de {{ origemAtual.label.toLowerCase() }} chegou ainda.
      </q-card-section>

      <q-list v-else separator dense style="max-height: 320px; overflow-y: auto">
        <q-item v-for="imp in recebidos" :key="imp.id">
          <q-item-section avatar>
            <q-icon
              :name="imp.source === 'erp' ? 'sync' : 'description'"
              :color="imp.source === 'erp' ? 'positive' : 'grey-7'"
            />
          </q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-medium quebra">
              <template v-if="imp.source === 'erp'">
                Sincronização<span v-if="imp.copy_at">
                  · cópia do banco de {{ formatQuando(imp.copy_at) }}</span>
              </template>
              <template v-else>{{ imp.file_name }}</template>
            </q-item-label>
            <q-item-label caption>
              {{ formatQuando(imp.imported_at) }}
              <span v-if="imp.imported_by"> · por {{ imp.imported_by }}</span>
              <span v-if="imp.first_day">
                · notas de {{ formatDia(imp.first_day) }}<template
                  v-if="imp.last_day !== imp.first_day"> a {{ formatDia(imp.last_day) }}</template>
              </span>
            </q-item-label>
          </q-item-section>
          <q-item-section side class="text-right">
            <q-item-label class="text-weight-bold text-positive">
              {{ formatQtd(imp.matched_lines) }} item(ns)
            </q-item-label>
            <q-item-label caption>{{ formatQtd(imp.matched_quantity) }} pç</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>
    </q-card>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const ORIGENS = [
  { value: 'venda', label: 'Faturamento', cfop: 'só saída, 5xxx e 6xxx' },
  { value: 'brinde', label: 'Brindes', cfop: 'só remessa ao cliente, 5910 e 6910' },
]

// Notas mais velhas que isto avisam que a sincronização parou. Na segunda de
// manhã a cópia costuma trazer até o sábado: dois dias, sem alarme.
const DIAS_ATRASO = 3

const origem = ref('venda')
const ultima = ref(null)
const recebidos = ref([])
const carregando = ref(false)
const carregado = ref(false)

const origemAtual = computed(
  () => ORIGENS.find((o) => o.value === origem.value) || ORIGENS[0]
)

const relato = computed(() => ultima.value?.report || null)

/** Dias desde as notas mais recentes que chegaram; 0 = em dia. */
const atraso = computed(() => {
  const ate = ultima.value?.last_day
  if (!ate) return 0
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const dias = Math.round((hoje - new Date(`${ate}T00:00:00`)) / 86400000)
  return dias > DIAS_ATRASO ? dias : 0
})

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
  const fora = r.usable_lines - r.matched_lines
  return [
    { label: 'itens nas notas do período', valor: formatQtd(r.total_lines), cor: 'text-grey-8' },
    {
      label: 'entraram no sistema',
      valor: formatQtd(r.matched_lines),
      cor: r.matched_lines ? 'text-positive' : 'text-grey-6',
    },
    {
      // A maioria é cliente do ERP que os promotores não atendem: o pacote traz
      // as notas de todos, e o casamento separa as das lojas daqui.
      label: 'de clientes ou produtos fora do app',
      valor: formatQtd(fora),
      cor: 'text-grey-7',
    },
    { label: 'peças contabilizadas', valor: formatQtd(r.matched_quantity), cor: 'text-primary' },
  ]
})

const pendencias = computed(() => [
  {
    titulo: 'Produtos sem cadastro',
    ajuda: 'Códigos que o ERP traz e este app não conhece.',
    rotulo: 'código',
    itens: relato.value?.unknown_products || [],
    total: relato.value?.unknown_products_total || 0,
  },
  {
    titulo: 'Clientes sem cadastro',
    ajuda: 'CNPJ do ERP sem cliente correspondente aqui. Vem todo cliente que '
      + 'comprou no período; os que os promotores atendem precisam do CNPJ no cadastro.',
    rotulo: 'cliente',
    itens: relato.value?.unknown_customers || [],
    total: relato.value?.unknown_customers_total || 0,
  },
])

const temPendencia = computed(() => pendencias.value.some((lista) => lista.total > 0))

/** As duas consultas são por origem: trocar de aba troca tudo. */
async function carregar() {
  carregando.value = true
  try {
    const [ultimo, lista] = await Promise.all([
      merchandisingApi.latestErpImport(origem.value),
      merchandisingApi.listInvoiceImports(origem.value),
    ])
    ultima.value = ultimo
    recebidos.value = lista
  } catch {
    ultima.value = null
    recebidos.value = []
    $q.notify({ type: 'negative', message: 'Não foi possível buscar os envios do ERP.' })
  } finally {
    carregando.value = false
    carregado.value = true
  }
}

onMounted(carregar)
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

/* Nome de cliente e de produto não se corta: quebra linha */
.quebra {
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
