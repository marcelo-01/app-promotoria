import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'

// ── Rotas do promotor: migram para o ERP como um bloco ────────────────────
export const promotorRoutes = [
  {
    path: '/promotor',
    component: () => import('@/layouts/PromotorLayout.vue'),
    meta: { requiresAuth: true, requiresRoles: ['promoter', 'admin', 'supervisor'] },
    children: [
      {
        path: '',
        name: 'PromotorClientes',
        component: () => import('@/pages/promotor/PromotorClientesPage.vue'),
      },
      {
        // O tipo vai no caminho e é validado aqui: uma URL com tipo inventado
        // cai no catch-all e volta para a lista de clientes.
        path: 'clientes/:customerId/:visitType(gondola|estoque)',
        name: 'PromotorContagem',
        component: () => import('@/pages/promotor/PromotorContagemPage.vue'),
        props: true,
      },
      {
        path: 'envios',
        name: 'PromotorEnvios',
        component: () => import('@/pages/promotor/PromotorEnviosPage.vue'),
      },
      {
        // Correção de um envio: é a mesma tela da contagem, só que carregada a
        // partir do que está no servidor em vez do mix do cliente.
        path: 'envios/:visitId',
        name: 'PromotorEdicao',
        component: () => import('@/pages/promotor/PromotorContagemPage.vue'),
        props: true,
      },
    ],
  },
]

// ── Rotas do administrador: viram filhas do MainLayout do ERP ─────────────
export const adminRoutes = [
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresRoles: ['admin', 'supervisor'] },
    children: [
      { path: '', redirect: { name: 'AdminDashboard' } },
      {
        path: 'painel',
        name: 'AdminDashboard',
        component: () => import('@/pages/admin/AdminDashboardPage.vue'),
      },
      {
        path: 'visitas',
        name: 'AdminVisitas',
        component: () => import('@/pages/admin/AdminVisitasPage.vue'),
      },
      {
        path: 'vinculos',
        name: 'AdminVinculos',
        component: () => import('@/pages/admin/AdminVinculosPage.vue'),
      },
      {
        path: 'cadastros',
        name: 'AdminCadastros',
        component: () => import('@/pages/admin/AdminCadastrosPage.vue'),
      },
    ],
  },
]

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { requiresAuth: false },
  },
  ...promotorRoutes,
  ...adminRoutes,
  // A raiz redireciona conforme o papel — ver guard abaixo
  { path: '/', redirect: () => (roleOf() === 'promoter' ? '/promotor' : '/admin') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

function roleOf() {
  return JSON.parse(localStorage.getItem('user') || 'null')?.role
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Guard idêntico em espírito ao do ERP (router/index.js:117)
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const userStore = useUserStore()

  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth !== false)
  const requiredRoles = to.matched.flatMap((r) => r.meta.requiresRoles || [])
  const role = userStore.user?.role || roleOf()

  if (requiresAuth && !authStore.isAuthenticated) {
    next('/login')
  } else if (requiredRoles.length > 0 && !requiredRoles.includes(role)) {
    next(role === 'promoter' ? '/promotor' : '/admin')
  } else if (to.path === '/login' && authStore.isAuthenticated) {
    next('/')
  } else {
    next()
  }
})

export default router
