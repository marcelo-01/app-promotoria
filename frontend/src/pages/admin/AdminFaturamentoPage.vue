<!--
  A planilha de faturamento do ERP: o que ENTROU em cada cliente.

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
-->
<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Planilha de faturamento</div>
    <div class="text-caption text-grey-7 q-mb-md">
      O que saiu para cada cliente. É por aqui que o sistema sabe o que entrou na
      loja — sem isso, ele só consegue adivinhar pela variação do estoque.
    </div>

    <!-- ── Anexar ─────────────────────────────────────────────────────── -->
    <q-card flat bordered class="q-mb-md">
      <q-card-section class="row items-center q-col-gutter-md">
        <div class="col-12 col-md">
          <q-file
            v-model="arquivo" outlined dense clearable
            accept=".xlsx,.xlsm" label="Planilha do ERP (.xlsx)"
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

          <div v-if="relato.first_day" class="text-caption text-grey-7 q-mt-md">
            Período da planilha: {{ formatDia(relato.first_day) }}
            <span v-if="relato.last_day !== relato.first_day">
              a {{ formatDia(relato.last_day) }}
            </span>
            · devolução não entra: ela só é lançada no ERP quando a mercadoria
            volta ao estoque, dias depois. Quem cobre a perda por validade é a
            retirada que o promotor registra no aplicativo.
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
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const arquivo = ref(null)
const relato = ref(null)
const lendo = ref(false)
const gravando = ref(false)

const formatQtd = (v) =>
  Number(v || 0).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

const formatDia = (iso) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('pt-BR') : '—'

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
}

async function conferir() {
  if (!arquivo.value) return
  lendo.value = true
  try {
    relato.value = await merchandisingApi.previewInvoices(arquivo.value)
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
    relato.value = await merchandisingApi.importInvoices(arquivo.value)
    $q.notify({
      type: 'positive',
      message: `${relato.value.matched_lines} linha(s) importada(s).`,
      position: 'top',
    })
  } catch (error) {
    $q.notify({ type: 'negative', message: error.message, timeout: 6000 })
  } finally {
    gravando.value = false
  }
}
</script>

<style scoped>
.numero {
  font-size: 1.8rem;
  font-weight: 800;
  line-height: 1.1;
}
</style>
