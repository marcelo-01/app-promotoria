<template>
  <q-page class="q-pa-md row q-col-gutter-md">
    <div class="col-12 col-md-4">
      <q-card flat bordered>
        <q-card-section class="text-subtitle1">Promotores</q-card-section>
        <q-separator />
        <q-list separator>
          <q-item
            v-for="p in promotores" :key="p.id"
            clickable v-ripple :active="p.id === selecionado?.id"
            active-class="bg-blue-1"
            @click="selecionar(p)"
          >
            <q-item-section>
              <q-item-label>{{ p.full_name }}</q-item-label>
              <q-item-label caption>{{ p.email }}</q-item-label>
            </q-item-section>
          </q-item>

          <q-item v-if="!promotores.length">
            <q-item-section class="text-grey-7 text-caption">
              Nenhum promotor cadastrado. Crie um em "Cadastros".
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
              <q-item-label caption>{{ c.document || 'sem documento' }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'
import { customersApi } from '@/api/customers'
import { usersApi } from '@/api/users'

const $q = useQuasar()

const promotores = ref([])
const clientes = ref([])
const selecionado = ref(null)
const marcados = ref([])
const busca = ref('')
const salvando = ref(false)

const filtrados = computed(() => {
  const term = busca.value?.trim().toLowerCase()
  if (!term) return clientes.value
  return clientes.value.filter(
    (c) => c.name.toLowerCase().includes(term) || (c.document || '').includes(term)
  )
})

async function selecionar(promotor) {
  selecionado.value = promotor
  marcados.value = await merchandisingApi.getAssignments(promotor.id)
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

onMounted(async () => {
  promotores.value = await usersApi.list({ role: 'promoter' })
  clientes.value = await customersApi.list()
})
</script>
