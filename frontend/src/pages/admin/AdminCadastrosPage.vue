<!--
  CRUD mínimo, deliberadamente simples: esta tela MORRE na fusão com o ERP, onde
  clientes e produtos virão do Firebird. A via de entrada preferida é a
  importação de planilha (aba "Importar planilhas").
-->
<template>
  <q-page class="q-pa-md">
    <q-tabs v-model="aba" dense no-caps align="left" class="text-grey-7 q-mb-md"
            active-color="primary" indicator-color="primary">
      <q-tab name="clientes" label="Clientes" icon="store" />
      <q-tab name="produtos" label="Produtos" icon="inventory_2" />
      <q-tab name="promotores" label="Promotores" icon="badge" />
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
          <template #body-cell-is_active="props">
            <q-td :props="props">
              <q-chip dense square :color="props.value ? 'positive' : 'grey-5'" text-color="white">
                {{ props.value ? 'Ativo' : 'Inativo' }}
              </q-chip>
            </q-td>
          </template>
          <template #body-cell-acoes="props">
            <q-td :props="props" class="text-right">
              <q-btn flat dense round icon="edit" color="primary" @click="abrirProduto(props.row)" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ── Promotores ─────────────────────────────────────────────── -->
      <q-tab-panel name="promotores" class="q-pa-none">
        <div class="row justify-end q-mb-sm">
          <q-btn color="primary" no-caps unelevated icon="add" label="Novo promotor"
                 @click="abrirPromotor()" />
        </div>

        <q-table :rows="promotores" :columns="colunasPromotor" row-key="id" flat bordered>
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
              <q-item-section>
                <q-item-label>{{ p.name }}</q-item-label>
                <q-item-label caption>{{ p.sku }} · {{ p.unit }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card>
      </q-tab-panel>
    </q-tab-panels>

    <!-- ── Diálogo: cliente ─────────────────────────────────────────── -->
    <q-dialog v-model="dialogCliente">
      <q-card style="min-width: 340px; max-width: 640px; width: 90vw">
        <q-card-section class="text-subtitle1">
          {{ clienteForm.id ? 'Editar cliente' : 'Novo cliente' }}
        </q-card-section>
        <q-separator />
        <q-card-section class="row q-col-gutter-sm">
          <q-input class="col-12 col-sm-8" v-model="clienteForm.name" outlined dense
                   label="Nome fantasia *" />
          <q-input class="col-12 col-sm-4" v-model="clienteForm.document" outlined dense
                   label="CNPJ/CPF" hint="Só dígitos" />
          <q-input class="col-12" v-model="clienteForm.corporate_name" outlined dense
                   label="Razão social" />
          <q-input class="col-12 col-sm-6" v-model="clienteForm.phone" outlined dense label="Telefone" />
          <q-input class="col-12 col-sm-6" v-model="clienteForm.email" outlined dense label="E-mail" />
          <q-input class="col-12 col-sm-8" v-model="clienteForm.address.street" outlined dense
                   label="Logradouro" />
          <q-input class="col-12 col-sm-4" v-model="clienteForm.address.number" outlined dense
                   label="Número" />
          <q-input class="col-12 col-sm-5" v-model="clienteForm.address.neighborhood" outlined dense
                   label="Bairro" />
          <q-input class="col-12 col-sm-5" v-model="clienteForm.address.city" outlined dense
                   label="Cidade" />
          <q-input class="col-12 col-sm-2" v-model="clienteForm.address.state" outlined dense
                   label="UF" maxlength="2" />
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
      <q-card style="min-width: 340px; max-width: 640px; width: 90vw">
        <q-card-section class="text-subtitle1">
          {{ produtoForm.id ? 'Editar produto' : 'Novo produto' }}
        </q-card-section>
        <q-separator />
        <q-card-section class="row q-col-gutter-sm">
          <q-input class="col-12 col-sm-4" v-model="produtoForm.sku" outlined dense label="SKU *" />
          <q-input class="col-12 col-sm-8" v-model="produtoForm.name" outlined dense label="Nome *" />
          <q-input class="col-12 col-sm-6" v-model="produtoForm.barcode" outlined dense
                   label="Código de barras (EAN-13)" />
          <q-input class="col-12 col-sm-6" v-model="produtoForm.category" outlined dense
                   label="Categoria" />
          <q-input class="col-6 col-sm-3" v-model="produtoForm.unit" outlined dense label="Unidade" />
          <q-input class="col-6 col-sm-3" v-model.number="produtoForm.price" outlined dense
                   type="number" step="0.01" label="Preço" />
          <q-input class="col-6 col-sm-3" v-model.number="produtoForm.package_size" outlined dense
                   type="number" label="Un. por caixa" />
          <q-input class="col-6 col-sm-3" v-model.number="produtoForm.shelf_life_days" outlined dense
                   type="number" label="Validade (dias)" />
          <div class="col-12">
            <q-toggle v-model="produtoForm.is_active" label="Ativo" />
            <q-toggle v-model="produtoForm.is_perishable" label="Perecível" />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn color="primary" unelevated no-caps label="Salvar"
                 :loading="salvando" @click="salvarProduto" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ── Diálogo: promotor ────────────────────────────────────────── -->
    <q-dialog v-model="dialogPromotor">
      <q-card style="min-width: 340px; max-width: 480px; width: 90vw">
        <q-card-section class="text-subtitle1">Novo promotor</q-card-section>
        <q-separator />
        <q-card-section class="q-gutter-sm">
          <q-input v-model="promotorForm.full_name" outlined dense label="Nome completo" />
          <q-input v-model="promotorForm.email" outlined dense label="E-mail *" type="email" />
          <q-input v-model="promotorForm.phone" outlined dense label="Telefone" />
          <q-input v-model="promotorForm.password" outlined dense label="Senha *" type="text"
                   hint="Mínimo 6 caracteres. O promotor usa este e-mail e senha para entrar." />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn color="primary" unelevated no-caps label="Criar"
                 :loading="salvando" @click="salvarPromotor" />
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
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
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

const emptyAddress = () => ({
  zip_code: null, street: null, number: null, complement: null,
  neighborhood: null, city: null, state: null,
})
const clienteForm = reactive({ id: null, name: '', document: '', corporate_name: '',
  phone: '', email: '', address: emptyAddress() })

const colunasCliente = [
  { name: 'name', label: 'Nome', field: 'name', align: 'left', sortable: true },
  { name: 'document', label: 'CNPJ/CPF', field: 'document', align: 'left' },
  { name: 'city', label: 'Cidade', field: (r) => r.address?.city || '—', align: 'left' },
  { name: 'phone', label: 'Telefone', field: 'phone', align: 'left' },
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
    id: row?.id || null,
    name: row?.name || '',
    document: row?.document || '',
    corporate_name: row?.corporate_name || '',
    phone: row?.phone || '',
    email: row?.email || '',
    address: { ...emptyAddress(), ...(row?.address || {}) },
  })
  dialogCliente.value = true
}

async function salvarCliente() {
  if (!clienteForm.name) {
    $q.notify({ type: 'warning', message: 'Informe o nome do cliente.' })
    return
  }
  salvando.value = true
  const { id, ...payload } = clienteForm
  try {
    if (id) await customersApi.update(id, payload)
    else await customersApi.create(payload)
    dialogCliente.value = false
    await carregarClientes()
    $q.notify({ type: 'positive', message: 'Cliente salvo.' })
  } catch (error) {
    notifyError(error, 'Erro ao salvar cliente')
  } finally {
    salvando.value = false
  }
}

// ── Produtos ────────────────────────────────────────────────────────────
const produtos = ref([])
const buscaProduto = ref('')
const carregandoProdutos = ref(false)
const dialogProduto = ref(false)

const produtoForm = reactive({ id: null, sku: '', name: '', barcode: '', category: '',
  unit: 'UN', price: 0, package_size: 1, shelf_life_days: null,
  is_active: true, is_perishable: true })

const colunasProduto = [
  { name: 'sku', label: 'SKU', field: 'sku', align: 'left', sortable: true },
  { name: 'name', label: 'Produto', field: 'name', align: 'left', sortable: true },
  { name: 'barcode', label: 'Cód. barras', field: 'barcode', align: 'left' },
  { name: 'unit', label: 'Un.', field: 'unit', align: 'left' },
  { name: 'is_active', label: 'Status', field: 'is_active', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

async function carregarProdutos() {
  carregandoProdutos.value = true
  try {
    produtos.value = await productsApi.list({ search: buscaProduto.value })
  } finally {
    carregandoProdutos.value = false
  }
}

function abrirProduto(row) {
  Object.assign(produtoForm, {
    id: row?.id || null,
    sku: row?.sku || '',
    name: row?.name || '',
    barcode: row?.barcode || '',
    category: row?.category || '',
    unit: row?.unit || 'UN',
    price: Number(row?.price || 0),
    package_size: Number(row?.package_size || 1),
    shelf_life_days: row?.shelf_life_days ?? null,
    is_active: row?.is_active ?? true,
    is_perishable: row?.is_perishable ?? true,
  })
  dialogProduto.value = true
}

async function salvarProduto() {
  if (!produtoForm.sku || !produtoForm.name) {
    $q.notify({ type: 'warning', message: 'SKU e nome são obrigatórios.' })
    return
  }
  salvando.value = true
  const { id, ...payload } = produtoForm
  try {
    if (id) await productsApi.update(id, payload)
    else await productsApi.create(payload)
    dialogProduto.value = false
    await carregarProdutos()
    $q.notify({ type: 'positive', message: 'Produto salvo.' })
  } catch (error) {
    notifyError(error, 'Erro ao salvar produto')
  } finally {
    salvando.value = false
  }
}

// ── Promotores ──────────────────────────────────────────────────────────
const promotores = ref([])
const dialogPromotor = ref(false)
const dialogSenha = ref(false)
const senhaAlvo = ref(null)
const novaSenha = ref('')

const promotorForm = reactive({ full_name: '', email: '', phone: '', password: '' })

const colunasPromotor = [
  { name: 'full_name', label: 'Nome', field: 'full_name', align: 'left' },
  { name: 'email', label: 'E-mail', field: 'email', align: 'left' },
  { name: 'phone', label: 'Telefone', field: 'phone', align: 'left' },
  { name: 'acoes', label: '', field: 'acoes', align: 'right' },
]

async function carregarPromotores() {
  promotores.value = await usersApi.list({ role: 'promoter' })
}

function abrirPromotor() {
  Object.assign(promotorForm, { full_name: '', email: '', phone: '', password: '' })
  dialogPromotor.value = true
}

async function salvarPromotor() {
  if (!promotorForm.email || !promotorForm.password) {
    $q.notify({ type: 'warning', message: 'E-mail e senha são obrigatórios.' })
    return
  }
  salvando.value = true
  try {
    await usersApi.create({ ...promotorForm, role: 'promoter' })
    dialogPromotor.value = false
    await carregarPromotores()
    $q.notify({ type: 'positive', message: 'Promotor criado.' })
  } catch (error) {
    notifyError(error, 'Erro ao criar promotor')
  } finally {
    salvando.value = false
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
  await Promise.all([carregarClientes(), carregarProdutos(), carregarPromotores()])
  clientesFiltradosMix.value = clientes.value
})
</script>
