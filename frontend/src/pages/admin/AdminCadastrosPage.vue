<!--
  CRUD mínimo e deliberadamente simples: esta tela MORRE na fusão com o ERP, onde
  clientes e produtos virão do Firebird. Cliente é só um nome; produto é nome e
  foto — é a foto que o promotor usa para reconhecer a embalagem na gôndola.
-->
<template>
  <q-page class="q-pa-md">
    <q-tabs v-model="aba" dense no-caps align="left" class="text-grey-7 q-mb-md"
            active-color="primary" indicator-color="primary">
      <q-tab name="clientes" label="Clientes" icon="store" />
      <q-tab name="produtos" label="Produtos" icon="inventory_2" />
      <q-tab name="promotores" label="Promotores" icon="badge" />
      <q-tab name="vendedores" label="Vendedores" icon="storefront" />
      <q-tab name="mix" label="Mix por cliente" icon="checklist" />
    </q-tabs>

    <q-tab-panels v-model="aba" animated class="bg-transparent">
      <!-- ── Clientes ───────────────────────────────────────────────── -->
      <q-tab-panel name="clientes" class="q-pa-none">
        <div class="row items-center justify-between q-mb-sm">
          <q-input v-model="buscaCliente" outlined dense clearable placeholder="Buscar cliente..."
                   style="min-width: 260px" @update:model-value="carregarClientes">
            <template #prepend><q-icon name="search" /></template>
          </q-input>
          <q-btn color="primary" no-caps unelevated icon="add" label="Novo cliente"
                 @click="abrirCliente(null)" />
        </div>

        <q-table :rows="clientes" :columns="colunasCliente" row-key="id"
                 flat bordered :loading="carregandoClientes" :rows-per-page-options="[25, 50, 100]">
          <template #body-cell-status="props">
            <q-td :props="props">
              <q-toggle
                :model-value="props.value === 'active'" color="positive"
                :label="props.value === 'active' ? 'Ativo' : 'Inativo'"
                @update:model-value="alternarCliente(props.row, $event)"
              />
            </q-td>
          </template>
          <template #body-cell-acoes="props">
            <q-td :props="props" class="text-right">
              <q-btn flat dense round icon="edit" color="primary" @click="abrirCliente(props.row)" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ── Produtos ───────────────────────────────────────────────── -->
      <q-tab-panel name="produtos" class="q-pa-none">
        <div class="row items-center justify-between q-mb-sm">
          <q-input v-model="buscaProduto" outlined dense clearable placeholder="Buscar produto..."
                   style="min-width: 260px" @update:model-value="carregarProdutos">
            <template #prepend><q-icon name="search" /></template>
          </q-input>
          <q-btn color="primary" no-caps unelevated icon="add" label="Novo produto"
                 @click="abrirProduto(null)" />
        </div>

        <q-table :rows="produtos" :columns="colunasProduto" row-key="id"
                 flat bordered :loading="carregandoProdutos" :rows-per-page-options="[25, 50, 100]">
          <template #body-cell-foto="props">
            <q-td :props="props">
              <q-avatar rounded size="52px" color="grey-3">
                <img v-if="mediaUrl(props.row.image_url)" :src="mediaUrl(props.row.image_url)"
                     :alt="props.row.name" />
                <q-icon v-else name="photo_camera" color="grey-6" />
              </q-avatar>
            </q-td>
          </template>
          <template #body-cell-is_active="props">
            <q-td :props="props">
              <q-toggle
                :model-value="props.value" color="positive"
                :label="props.value ? 'Ativo' : 'Inativo'"
                @update:model-value="alternarProduto(props.row, $event)"
              />
            </q-td>
          </template>
          <template #body-cell-acoes="props">
            <q-td :props="props" class="text-right">
              <q-btn flat dense round icon="edit" color="primary" @click="abrirProduto(props.row)" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ── Promotores e vendedores ────────────────────────────────── -->
      <!-- O mesmo painel para os dois: são o mesmo cadastro (nome, e-mail e
           senha), só muda o papel. Uma pessoa pode ter os dois — quem conta a
           loja e também lança o pedido — e aí aparece nas duas abas. O papel
           da aba em que foi criada é o principal: é onde ela cai ao entrar;
           o outro app fica no menu. -->
      <q-tab-panel v-for="papel in PAPEIS" :key="papel.role" :name="papel.aba" class="q-pa-none">
        <div class="row justify-end q-mb-sm">
          <q-btn color="primary" no-caps unelevated icon="add" :label="`Novo ${papel.singular}`"
                 @click="abrirUsuario(papel)" />
        </div>

        <q-table :rows="usuarios[papel.role]" :columns="colunasUsuario(papel)" row-key="id"
                 flat bordered>
          <template #body-cell-outro="props">
            <q-td :props="props">
              <q-toggle
                :model-value="props.row.roles.includes(papel.outro)" color="positive"
                :label="`também ${papel.outroRotulo}`"
                @update:model-value="alternarPapel(props.row, papel, $event)"
              />
            </q-td>
          </template>
          <template #body-cell-acoes="props">
            <q-td :props="props" class="text-right">
              <q-btn flat dense round icon="key" color="primary"
                     title="Redefinir senha" @click="abrirSenha(props.row)" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ── Mix por cliente ────────────────────────────────────────── -->
      <q-tab-panel name="mix" class="q-pa-none">
        <q-card flat bordered>
          <q-card-section class="row items-center q-col-gutter-md">
            <div class="col-12 col-md-6">
              <q-select
                v-model="mixCliente" outlined dense clearable use-input
                label="Cliente" :options="clientesFiltradosMix"
                option-value="id" option-label="name" emit-value map-options
                @filter="filtrarClientesMix" @update:model-value="carregarMix"
              />
            </div>
            <div class="col-12 col-md-6 text-right">
              <span class="text-caption text-grey-7 q-mr-md">
                {{ mixSelecionado.length }} produto(s) no mix
              </span>
              <q-btn color="primary" no-caps unelevated label="Salvar mix"
                     :disable="!mixCliente" :loading="salvandoMix" @click="salvarMix" />
            </div>
          </q-card-section>

          <q-card-section class="q-pt-none">
            <q-banner dense class="bg-grey-2 rounded-borders text-caption">
              Sem mix cadastrado, o promotor vê o catálogo completo neste cliente.
              Com mix, vê só os itens marcados — na ordem em que aparecem aqui.
            </q-banner>
          </q-card-section>

          <q-separator />

          <q-list separator style="max-height: 55vh; overflow-y: auto">
            <q-item v-for="p in produtos" :key="p.id" tag="label" v-ripple>
              <q-item-section side top>
                <q-checkbox v-model="mixSelecionado" :val="p.id" :disable="!mixCliente" />
              </q-item-section>
              <q-item-section avatar>
                <q-avatar rounded size="40px" color="grey-3">
                  <img v-if="mediaUrl(p.image_url)" :src="mediaUrl(p.image_url)" :alt="p.name" />
                  <q-icon v-else name="photo_camera" color="grey-6" size="20px" />
                </q-avatar>
              </q-item-section>
              <q-item-section>
                <q-item-label>{{ p.name }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card>
      </q-tab-panel>
    </q-tab-panels>

    <!-- ── Diálogo: cliente ─────────────────────────────────────────── -->
    <q-dialog v-model="dialogCliente">
      <q-card style="min-width: 320px; max-width: 480px; width: 90vw">
        <q-card-section class="text-subtitle1">
          {{ clienteForm.id ? 'Editar cliente' : 'Novo cliente' }}
        </q-card-section>
        <q-separator />
        <q-card-section>
          <q-input v-model="clienteForm.name" outlined dense autofocus
                   label="Nome do cliente *" @keyup.enter="salvarCliente" />

          <q-input
            v-model="clienteForm.document" outlined dense clearable class="q-mt-md"
            label="CNPJ / CPF"
            hint="É por ele que a planilha de faturamento encontra este cliente.
                  Em branco, as notas dele não entram no sistema."
            @keyup.enter="salvarCliente"
          >
            <template #prepend><q-icon name="badge" /></template>
          </q-input>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn color="primary" unelevated no-caps label="Salvar"
                 :loading="salvando" @click="salvarCliente" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Diálogo: produto ─────────────────────────────────────────── -->
    <q-dialog v-model="dialogProduto">
      <q-card style="min-width: 320px; max-width: 480px; width: 90vw">
        <q-card-section class="text-subtitle1">
          {{ produtoForm.id ? 'Editar produto' : 'Novo produto' }}
        </q-card-section>
        <q-separator />
        <q-card-section class="q-gutter-md">
          <q-input v-model="produtoForm.name" outlined dense autofocus
                   label="Nome do produto *" />

          <q-input
            v-model="produtoForm.sku" outlined dense clearable
            label="Código no ERP"
            hint="O COD. ITEM da planilha de faturamento (ex.: A21030). Em branco,
                  as notas deste produto não entram no sistema."
          >
            <template #prepend><q-icon name="qr_code_2" /></template>
          </q-input>

          <q-input
            v-model.number="produtoForm.package_size" outlined dense
            type="number" min="1" step="1" label="Unidades por caixa *"
            hint="É por aqui que a planilha converte a contagem: 1 caixa + 10 unidades
                  de um produto com 10 por caixa chega ao relatório como 20 unidades."
          >
            <template #prepend><q-icon name="inventory_2" /></template>
          </q-input>

          <q-input
            v-model="produtoForm.shelf_life_days" outlined dense clearable
            type="number" min="1" step="1" label="Dias de validade"
            hint="Quantos dias o produto dura a partir da fabricação.
                  Deixe em branco enquanto não souber."
          >
            <template #prepend><q-icon name="event" /></template>
            <template #append><span class="text-caption text-grey-7">dias</span></template>
          </q-input>

          <q-input
            v-model="produtoForm.arrival_shelf_life_days" outlined dense clearable
            type="number" min="1" step="1" label="Validade na chegada"
            hint="Com quantos dias PARA VENCER a mercadoria costuma chegar ao cliente.
                  É o que faz o app pedir a coleta de vencimento na hora certa —
                  em branco, este produto nunca entra na coleta."
          >
            <template #prepend><q-icon name="local_shipping" /></template>
            <template #append><span class="text-caption text-grey-7">dias</span></template>
          </q-input>

          <div class="row items-center q-col-gutter-md">
            <div class="col-auto">
              <q-avatar rounded size="96px" color="grey-3">
                <img v-if="fotoPreview" :src="fotoPreview" alt="Foto do produto" />
                <q-icon v-else name="photo_camera" color="grey-6" size="32px" />
              </q-avatar>
            </div>
            <div class="col">
              <q-file
                v-model="fotoArquivo" outlined dense clearable
                accept="image/*" label="Foto do produto"
                hint="JPG, PNG ou WEBP — até 8 MB"
                @update:model-value="onFotoSelecionada"
              >
                <template #prepend><q-icon name="add_a_photo" /></template>
              </q-file>
              <q-btn
                v-if="produtoForm.image_url && !fotoArquivo"
                flat dense no-caps size="sm" color="negative"
                icon="delete" label="Remover foto atual" class="q-mt-xs"
                @click="removerFoto"
              />
            </div>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn color="primary" unelevated no-caps label="Salvar"
                 :loading="salvando" @click="salvarProduto" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Diálogo: promotor ou vendedor ────────────────────────────── -->
    <q-dialog v-model="dialogUsuario">
      <q-card style="min-width: 320px; max-width: 480px; width: 90vw">
        <q-card-section class="text-subtitle1">Novo {{ papelNovo.singular }}</q-card-section>
        <q-separator />
        <q-card-section class="q-gutter-sm">
          <q-input v-model="usuarioForm.full_name" outlined dense autofocus label="Nome" />
          <q-input v-model="usuarioForm.email" outlined dense label="E-mail *" type="email" />
          <q-input v-model="usuarioForm.password" outlined dense label="Senha *" type="text"
                   :hint="`Mínimo 6 caracteres. O ${papelNovo.singular} usa este e-mail e senha para entrar.`" />
          <q-checkbox v-model="usuarioForm.outro" :label="`Também é ${papelNovo.outroRotulo}`" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn color="primary" unelevated no-caps label="Criar"
                 :loading="salvando" @click="salvarUsuario" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Diálogo: redefinir senha ─────────────────────────────────── -->
    <q-dialog v-model="dialogSenha">
      <q-card style="min-width: 320px">
        <q-card-section class="text-subtitle1">
          Redefinir senha de {{ senhaAlvo?.full_name || senhaAlvo?.email }}
        </q-card-section>
        <q-separator />
        <q-card-section>
          <q-input v-model="novaSenha" outlined dense label="Nova senha *" type="text"
                   hint="Mínimo 6 caracteres" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn color="primary" unelevated no-caps label="Salvar"
                 :loading="salvando" @click="salvarSenha" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { mediaUrl } from '@/api/client'
import { customersApi } from '@/api/customers'
import { productsApi } from '@/api/products'
import { usersApi } from '@/api/users'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const aba = ref('clientes')
const salvando = ref(false)

const notifyError = (error, fallback) =>
  $q.notify({ type: 'negative', message: error.response?.data?.detail || fallback })

// ── Clientes ────────────────────────────────────────────────────────────
const clientes = ref([])
const buscaCliente = ref('')
const carregandoClientes = ref(false)
const dialogCliente = ref(false)

const clienteForm = reactive({ id: null, name: '', document: '' })

const colunasCliente = [
  { name: 'name', label: 'Nome', field: 'name', align: 'left', sortable: true },
  // Sem CNPJ o cliente não recebe as notas da planilha — a coluna existe para
  // esse buraco aparecer na lista, não só no relatório da importação.
  { name: 'document', label: 'CNPJ / CPF', field: 'document', align: 'left',
    sortable: true, format: (v) => (v ? formatDoc(v) : '—') },
  { name: 'status', label: 'Situação', field: 'status', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

async function carregarClientes() {
  carregandoClientes.value = true
  try {
    clientes.value = await customersApi.list({ search: buscaCliente.value })
  } finally {
    carregandoClientes.value = false
  }
}

function abrirCliente(row) {
  Object.assign(clienteForm, {
    id: row?.id || null, name: row?.name || '', document: row?.document || '',
  })
  dialogCliente.value = true
}

async function salvarCliente() {
  if (!clienteForm.name.trim()) {
    $q.notify({ type: 'warning', message: 'Informe o nome do cliente.' })
    return
  }
  salvando.value = true
  try {
    // O servidor guarda só os dígitos; em branco vai como null e desfaz o
    // vínculo com a planilha.
    const payload = {
      name: clienteForm.name,
      document: clienteForm.document || null,
    }
    if (clienteForm.id) {
      await customersApi.update(clienteForm.id, payload)
    } else {
      await customersApi.create(payload)
    }
    dialogCliente.value = false
    await carregarClientes()
    $q.notify({ type: 'positive', message: 'Cliente salvo.' })
  } catch (error) {
    notifyError(error, 'Erro ao salvar cliente')
  } finally {
    salvando.value = false
  }
}

/** Cliente inativo some da lista do promotor — é assim que se "remove" um. */
async function alternarCliente(row, ativo) {
  try {
    await customersApi.update(row.id, { status: ativo ? 'active' : 'inactive' })
    await carregarClientes()
  } catch (error) {
    notifyError(error, 'Erro ao alterar a situação do cliente')
  }
}

// ── Produtos ────────────────────────────────────────────────────────────
const produtos = ref([])
const buscaProduto = ref('')
const carregandoProdutos = ref(false)
const dialogProduto = ref(false)

const produtoForm = reactive({
  id: null, name: '', sku: '', package_size: 1, shelf_life_days: null,
  arrival_shelf_life_days: null, image_url: null,
})
const fotoArquivo = ref(null)
const fotoPreview = ref(null)
// A prévia é um object URL: sem revogar, o navegador segura o arquivo na memória
let previewUrl = null

const colunasProduto = [
  { name: 'foto', label: 'Foto', field: 'image_url', align: 'left' },
  { name: 'name', label: 'Produto', field: 'name', align: 'left', sortable: true },
  { name: 'sku', label: 'Cód. ERP', field: 'sku', align: 'left', sortable: true,
    format: (v) => v || '—' },
  { name: 'package_size', label: 'Un. por caixa', field: 'package_size', align: 'right',
    sortable: true, format: (v) => formatQtd(v) },
  { name: 'shelf_life_days', label: 'Validade', field: 'shelf_life_days', align: 'right',
    sortable: true, format: (v) => (v == null ? '—' : `${v} dias`) },
  { name: 'arrival_shelf_life_days', label: 'Na chegada', field: 'arrival_shelf_life_days',
    align: 'right', sortable: true, format: (v) => (v == null ? '—' : `${v} dias`) },
  { name: 'is_active', label: 'Situação', field: 'is_active', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

const formatQtd = (v) =>
  v == null ? '1' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

/** 14 dígitos viram CNPJ; 11, CPF. O banco guarda só os dígitos. */
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

async function carregarProdutos() {
  carregandoProdutos.value = true
  try {
    produtos.value = await productsApi.list({ search: buscaProduto.value })
  } finally {
    carregandoProdutos.value = false
  }
}

function limparPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl)
  previewUrl = null
}

function abrirProduto(row) {
  Object.assign(produtoForm, {
    id: row?.id || null,
    name: row?.name || '',
    sku: row?.sku || '',
    package_size: Number(row?.package_size) || 1,
    shelf_life_days: row?.shelf_life_days ?? null,
    arrival_shelf_life_days: row?.arrival_shelf_life_days ?? null,
    image_url: row?.image_url || null,
  })
  fotoArquivo.value = null
  limparPreview()
  fotoPreview.value = mediaUrl(row?.image_url)
  dialogProduto.value = true
}

function onFotoSelecionada(file) {
  limparPreview()
  if (!file) {
    fotoPreview.value = mediaUrl(produtoForm.image_url)
    return
  }
  previewUrl = URL.createObjectURL(file)
  fotoPreview.value = previewUrl
}

async function removerFoto() {
  salvando.value = true
  try {
    const atualizado = await productsApi.removeImage(produtoForm.id)
    produtoForm.image_url = atualizado.image_url
    fotoPreview.value = null
    await carregarProdutos()
  } catch (error) {
    notifyError(error, 'Erro ao remover a foto')
  } finally {
    salvando.value = false
  }
}

async function salvarProduto() {
  if (!produtoForm.name.trim()) {
    $q.notify({ type: 'warning', message: 'Informe o nome do produto.' })
    return
  }
  if (!(Number(produtoForm.package_size) > 0)) {
    $q.notify({
      type: 'warning',
      message: 'Informe quantas unidades vêm numa caixa (no mínimo 1).',
    })
    return
  }
  // As duas validades são opcionais: em branco (o clearable devolve null) vão
  // como null e apagam o que estava lá. Preenchidas, têm de ser inteiros de dias.
  const validade = produtoForm.shelf_life_days
  const chegada = produtoForm.arrival_shelf_life_days
  const emBranco = (v) => v === null || v === undefined || v === ''
  const inteiroPositivo = (v) => Number.isInteger(Number(v)) && Number(v) > 0

  const semValidade = emBranco(validade)
  const semChegada = emBranco(chegada)

  if (!semValidade && !inteiroPositivo(validade)) {
    $q.notify({
      type: 'warning',
      message: 'Dias de validade deve ser um número inteiro de dias, maior que zero.',
    })
    return
  }
  if (!semChegada && !inteiroPositivo(chegada)) {
    $q.notify({
      type: 'warning',
      message: 'Validade na chegada deve ser um número inteiro de dias, maior que zero.',
    })
    return
  }
  // Chegar com mais vida do que o produto tem é troca dos dois campos de lugar —
  // erro fácil de cometer e que estragaria a estimativa inteira.
  if (!semValidade && !semChegada && Number(chegada) > Number(validade)) {
    $q.notify({
      type: 'warning',
      message: 'A validade na chegada não pode ser maior que os dias de validade.',
    })
    return
  }
  salvando.value = true
  try {
    // A foto vai numa segunda chamada (multipart): produto novo só ganha id aqui.
    const payload = {
      name: produtoForm.name,
      sku: produtoForm.sku || null,
      package_size: Number(produtoForm.package_size),
      shelf_life_days: semValidade ? null : Number(validade),
      arrival_shelf_life_days: semChegada ? null : Number(chegada),
    }
    const salvo = produtoForm.id
      ? await productsApi.update(produtoForm.id, payload)
      : await productsApi.create(payload)

    if (fotoArquivo.value) {
      await productsApi.uploadImage(salvo.id, fotoArquivo.value)
    }

    dialogProduto.value = false
    limparPreview()
    await carregarProdutos()
    $q.notify({ type: 'positive', message: 'Produto salvo.' })
  } catch (error) {
    notifyError(error, 'Erro ao salvar produto')
  } finally {
    salvando.value = false
  }
}

/** Produto inativo some da contagem do promotor. */
async function alternarProduto(row, ativo) {
  try {
    await productsApi.update(row.id, { is_active: ativo })
    await carregarProdutos()
  } catch (error) {
    notifyError(error, 'Erro ao alterar a situação do produto')
  }
}

// ── Promotores e vendedores ─────────────────────────────────────────────
// Os dois papéis de campo. O promotor conta a loja; o vendedor lê o pedido
// sugerido a partir do que o promotor contou. Mesmo cadastro, papel diferente
// — e `outro` é o papel que a pessoa pode acumular a partir desta aba.
const PAPEIS = [
  { role: 'promoter', aba: 'promotores', singular: 'promotor', criado: 'Promotor criado.',
    outro: 'seller', outroRotulo: 'vendedor' },
  { role: 'seller', aba: 'vendedores', singular: 'vendedor', criado: 'Vendedor criado.',
    outro: 'promoter', outroRotulo: 'promotor' },
]

const usuarios = reactive({ promoter: [], seller: [] })
const dialogUsuario = ref(false)
const papelNovo = ref(PAPEIS[0])
const dialogSenha = ref(false)
const senhaAlvo = ref(null)
const novaSenha = ref('')

const usuarioForm = reactive({ full_name: '', email: '', password: '', outro: false })

const colunasUsuario = (papel) => [
  { name: 'full_name', label: 'Nome', field: 'full_name', align: 'left' },
  { name: 'email', label: 'E-mail', field: 'email', align: 'left' },
  { name: 'outro', label: capitalizar(papel.outroRotulo), field: 'roles', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

const capitalizar = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1)

async function carregarUsuarios(role) {
  usuarios[role] = await usersApi.list({ role })
}

function abrirUsuario(papel) {
  papelNovo.value = papel
  Object.assign(usuarioForm, { full_name: '', email: '', password: '', outro: false })
  dialogUsuario.value = true
}

async function salvarUsuario() {
  if (!usuarioForm.email || !usuarioForm.password) {
    $q.notify({ type: 'warning', message: 'E-mail e senha são obrigatórios.' })
    return
  }
  const papel = papelNovo.value
  const { outro, ...dados } = usuarioForm
  salvando.value = true
  try {
    await usersApi.create({
      ...dados, role: papel.role, secondary_role: outro ? papel.outro : null,
    })
    dialogUsuario.value = false
    // Com o outro papel marcado, a pessoa entra também na outra aba
    await Promise.all(PAPEIS.map((p) => carregarUsuarios(p.role)))
    $q.notify({ type: 'positive', message: papel.criado })
  } catch (error) {
    notifyError(error, `Erro ao criar ${papel.singular}`)
  } finally {
    salvando.value = false
  }
}

/** Liga ou desliga o outro papel da pessoa. Recarrega as duas abas: ela
 *  aparece ou some da outra. */
async function alternarPapel(row, papel, ligado) {
  const roles = ligado
    ? [...row.roles, papel.outro]
    : row.roles.filter((r) => r !== papel.outro)
  try {
    await usersApi.setRoles(row.id, roles)
    await Promise.all(PAPEIS.map((p) => carregarUsuarios(p.role)))
  } catch (error) {
    notifyError(error, 'Erro ao alterar o papel')
  }
}

function abrirSenha(row) {
  senhaAlvo.value = row
  novaSenha.value = ''
  dialogSenha.value = true
}

async function salvarSenha() {
  salvando.value = true
  try {
    await usersApi.setPassword(senhaAlvo.value.id, novaSenha.value)
    dialogSenha.value = false
    $q.notify({ type: 'positive', message: 'Senha redefinida.' })
  } catch (error) {
    notifyError(error, 'Erro ao redefinir senha')
  } finally {
    salvando.value = false
  }
}

// ── Mix por cliente ─────────────────────────────────────────────────────
const mixCliente = ref(null)
const mixSelecionado = ref([])
const salvandoMix = ref(false)
const clientesFiltradosMix = ref([])

function filtrarClientesMix(val, update) {
  update(() => {
    const term = (val || '').toLowerCase()
    clientesFiltradosMix.value = term
      ? clientes.value.filter((c) => c.name.toLowerCase().includes(term))
      : clientes.value
  })
}

async function carregarMix() {
  if (!mixCliente.value) {
    mixSelecionado.value = []
    return
  }
  mixSelecionado.value = await merchandisingApi.getCustomerMix(mixCliente.value)
}

async function salvarMix() {
  salvandoMix.value = true
  try {
    await merchandisingApi.setCustomerMix(mixCliente.value, mixSelecionado.value)
    $q.notify({ type: 'positive', message: 'Mix salvo.' })
  } catch (error) {
    notifyError(error, 'Erro ao salvar o mix')
  } finally {
    salvandoMix.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    carregarClientes(), carregarProdutos(),
    ...PAPEIS.map((papel) => carregarUsuarios(papel.role)),
  ])
  clientesFiltradosMix.value = clientes.value
})

onUnmounted(limparPreview)
</script>
