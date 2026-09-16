<!--
  Quais clientes cada pessoa de campo atende. Promotor e vendedor usam o mesmo
  vínculo — a mesma tabela, os mesmos endpoints — e por isso a tela é uma só,
  com um seletor de papel em cima da lista. O promotor conta a loja; o
  vendedor recebe o pedido sugerido a partir do que o promotor contou.

  Quem acumula os dois papéis aparece nas duas listas, com os mesmos clientes:
  o vínculo é da pessoa, não do papel — ela conta e vê o pedido das mesmas
  lojas, e salvar de um lado vale para o outro.
-->
<template>
  <q-page class="q-pa-md row q-col-gutter-md">
    <div class="col-12 col-md-4">
      <q-card flat bordered>
        <q-card-section class="row items-center justify-between q-py-sm">
          <div class="text-subtitle1">{{ papel.plural }}</div>
          <q-btn-toggle
            v-model="papelAtual" dense no-caps unelevated toggle-color="primary"
            color="grey-3" text-color="grey-8" :options="opcoesPapel"
          />
        </q-card-section>
        <q-separator />
        <q-list separator>
          <q-item
            v-for="p in pessoas" :key="p.id"
            clickable v-ripple :active="p.id === selecionado?.id"
            active-class="bg-blue-1"
            @click="selecionar(p)"
          >
            <q-item-section>
              <q-item-label>{{ p.full_name }}</q-item-label>
              <q-item-label caption>
                {{ p.email }}
                <span v-if="acumula(p)"> · também {{ PAPEIS[outroPapel].singular }}</span>
              </q-item-label>
            </q-item-section>
          </q-item>

          <q-item v-if="!pessoas.length">
            <q-item-section class="text-grey-7 text-caption">
              Nenhum {{ papel.singular }} cadastrado. Crie um em "Cadastros".
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </div>

    <div class="col-12 col-md-8">
      <q-card flat bordered>
        <q-card-section class="row items-center justify-between">
          <div class="text-subtitle1">
            Clientes de {{ selecionado?.full_name || '—' }}
            <q-badge color="primary" class="q-ml-sm">{{ marcados.length }}</q-badge>
          </div>
          <q-btn
            color="primary" no-caps unelevated label="Salvar vínculos"
            :disable="!selecionado" :loading="salvando" @click="salvar"
          />
        </q-card-section>
        <q-separator />

        <q-card-section>
          <q-input v-model="busca" outlined dense clearable placeholder="Buscar cliente...">
            <template #prepend><q-icon name="search" /></template>
          </q-input>
        </q-card-section>

        <q-list separator style="max-height: 60vh; overflow-y: auto">
          <q-item v-for="c in filtrados" :key="c.id" tag="label" v-ripple>
            <q-item-section side top>
              <q-checkbox v-model="marcados" :val="c.id" :disable="!selecionado" />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ c.name }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { customersApi } from '@/api/customers'
import { usersApi } from '@/api/users'

const $q = useQuasar()

const PAPEIS = {
  promoter: { plural: 'Promotores', singular: 'promotor' },
  seller: { plural: 'Vendedores', singular: 'vendedor' },
}
const opcoesPapel = Object.entries(PAPEIS).map(([value, p]) => ({ value, label: p.plural }))

const papelAtual = ref('promoter')
const pessoas = ref([])
const clientes = ref([])
const selecionado = ref(null)
const marcados = ref([])
const busca = ref('')
const salvando = ref(false)

const papel = computed(() => PAPEIS[papelAtual.value])
const outroPapel = computed(() => (papelAtual.value === 'promoter' ? 'seller' : 'promoter'))
const acumula = (pessoa) => (pessoa.roles || []).includes(outroPapel.value)

const filtrados = computed(() => {
  const term = busca.value?.trim().toLowerCase()
  if (!term) return clientes.value
  return clientes.value.filter((c) => c.name.toLowerCase().includes(term))
})

async function carregarPessoas() {
  // Trocar de papel esvazia a seleção: os vínculos marcados eram da pessoa
  // anterior, e deixá-los na tela seria convidar a salvá-los na errada.
  selecionado.value = null
  marcados.value = []
  pessoas.value = await usersApi.list({ role: papelAtual.value })
}

async function selecionar(pessoa) {
  selecionado.value = pessoa
  marcados.value = await merchandisingApi.getAssignments(pessoa.id)
}

async function salvar() {
  salvando.value = true
  try {
    await merchandisingApi.setAssignments(selecionado.value.id, marcados.value)
    $q.notify({ type: 'positive', message: 'Vínculos salvos.' })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Erro ao salvar vínculos',
    })
  } finally {
    salvando.value = false
  }
}

watch(papelAtual, carregarPessoas)

onMounted(async () => {
  await carregarPessoas()
  clientes.value = await customersApi.list()
})
</script>
