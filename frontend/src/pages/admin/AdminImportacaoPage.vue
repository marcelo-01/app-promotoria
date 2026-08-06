<template>
  <q-page class="q-pa-md">
    <div class="text-h6 q-mb-md">Importar cadastros</div>

    <div class="row q-col-gutter-md">
      <div v-for="entidade in entidades" :key="entidade.key" class="col-12 col-md-6">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-subtitle1">{{ entidade.label }}</div>
            <div class="text-caption text-grey-7">{{ entidade.hint }}</div>
          </q-card-section>

          <q-card-section>
            <q-btn
              flat no-caps dense color="primary" icon="description"
              label="Baixar planilha-modelo"
              @click="merchandisingApi.downloadTemplate(entidade.key)"
            />
          </q-card-section>

          <q-card-section>
            <q-file
              v-model="arquivos[entidade.key]" outlined dense
              label="Selecione o arquivo .xlsx"
              accept=".xlsx,.csv"
            >
              <template #prepend><q-icon name="attach_file" /></template>
            </q-file>
          </q-card-section>

          <q-card-actions>
            <q-btn
              color="primary" no-caps unelevated label="Importar"
              :disable="!arquivos[entidade.key]"
              :loading="carregando[entidade.key]"
              @click="importar(entidade.key)"
            />
          </q-card-actions>

          <q-card-section v-if="relatorios[entidade.key]">
            <q-banner dense class="bg-grey-2 rounded-borders">
              {{ relatorios[entidade.key].created }} criados ·
              {{ relatorios[entidade.key].updated }} atualizados ·
              {{ relatorios[entidade.key].skipped }} ignorados ·
              {{ relatorios[entidade.key].errors.length }} erros
            </q-banner>

            <q-list v-if="relatorios[entidade.key].errors.length" dense class="q-mt-sm">
              <q-item v-for="e in relatorios[entidade.key].errors" :key="e.row">
                <q-item-section class="text-negative text-caption">
                  Linha {{ e.row }}: {{ e.reason }}
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { reactive } from 'vue'
import { useQuasar } from 'quasar'
import { merchandisingApi } from '@/api/merchandising'

const $q = useQuasar()

const entidades = [
  { key: 'customers', label: 'Clientes',
    hint: 'Atualiza pelo CNPJ/CPF. Rodar a mesma planilha duas vezes não duplica nada.' },
  { key: 'products', label: 'Produtos',
    hint: 'Atualiza pelo SKU. Rodar a mesma planilha duas vezes não duplica nada.' },
]

const arquivos = reactive({ customers: null, products: null })
const carregando = reactive({ customers: false, products: false })
const relatorios = reactive({ customers: null, products: null })

async function importar(entidade) {
  carregando[entidade] = true
  try {
    relatorios[entidade] = await merchandisingApi.importFile(entidade, arquivos[entidade])
    $q.notify({ type: 'positive', message: 'Importação concluída.' })
  } catch (error) {
    $q.notify({
      type: 'negative',
      message: error.response?.data?.detail || 'Falha na importação',
    })
  } finally {
    carregando[entidade] = false
  }
}
</script>
