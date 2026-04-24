import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

function redirectToAdmin(path: string) {
  return (to: { query: Record<string, unknown>; hash: string }) => ({
    path,
    query: to.query,
    hash: to.hash,
  })
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/admin'
    },
    {
      path: '/dashboard',
      redirect: '/admin'
    },
    {
      path: '/jobs',
      redirect: redirectToAdmin('/admin/jobs')
    },
    {
      path: '/interview-history',
      redirect: redirectToAdmin('/admin/interview-history')
    },
    {
      path: '/candidates',
      redirect: redirectToAdmin('/admin/candidates')
    },
    {
      path: '/candidate-detail',
      redirect: redirectToAdmin('/admin/candidate-detail')
    },
    {
      path: '/hiring',
      redirect: redirectToAdmin('/admin/hiring')
    },
    {
      path: '/agents',
      redirect: redirectToAdmin('/admin/agents')
    },
    {
      path: '/reports',
      redirect: redirectToAdmin('/admin/reports')
    },
    {
      path: '/settings',
      redirect: redirectToAdmin('/admin/settings')
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/auth/Login.vue'),
      meta: { publicOnly: true }
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('../views/auth/Register.vue'),
      meta: { publicOnly: true }
    },
    {
      path: '/admin',
      component: () => import('../layouts/AdminLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: 'dashboard',
          redirect: '/admin'
        },
        {
          path: '',
          name: 'Dashboard',
          component: () => import('../views/admin/Dashboard.vue')
        },
        {
          path: 'jobs',
          name: 'Jobs',
          component: () => import('../views/admin/Jobs.vue')
        },
        {
          path: 'interview-history',
          name: 'InterviewInvites',
          component: () => import('../views/admin/InterviewInvites.vue')
        },
        {
          path: 'candidates',
          name: 'Candidates',
          component: () => import('../views/admin/Candidates.vue')
        },
        {
          path: 'candidate-detail',
          name: 'CandidateDetail',
          component: () => import('../views/admin/CandidateDetail.vue')
        },
        {
            path: 'hiring',
            name: 'HiringCenter',
            component: () => import('../views/admin/HiringCenter.vue')
        },
        {
          path: 'agents',
          name: 'AgentCenter',
          component: () => import('../views/admin/AgentCenter.vue')
        },
        {
            path: 'interview/:id',
            name: 'InterviewDetails',
            component: () => import('../views/admin/InterviewDetails.vue')
        },
        {
          path: 'reports',
          name: 'Reports',
          component: () => import('../views/admin/Reports.vue')
        },
        {
          path: 'settings',
          name: 'SettingsHome',
          component: () => import('../views/admin/Settings.vue')
        },
        {
          path: 'settings/org',
          name: 'OrganizationSettings',
          component: () => import('../views/admin/OrganizationSettings.vue')
        },
        {
          path: 'settings/members',
          name: 'WorkspaceMembers',
          component: () => import('../views/admin/WorkspaceMembers.vue')
        },
        {
          path: 'settings/credentials',
          name: 'CredentialSettings',
          component: () => import('../views/admin/CredentialSettings.vue')
        }
      ]
    },
    {
      path: '/interview/:id',
      name: 'InterviewRoom',
      component: () => import('../views/interview/InterviewRoom.vue')
    },
    {
      path: '/interview/invitation/:token',
      name: 'InterviewInvitationEntry',
      component: () => import('../views/interview/InterviewInvitationEntry.vue')
    }
  ]
})

function resolveSafeRedirect(raw: unknown): string {
  const value = String(raw || '').trim()
  if (!value || !value.startsWith('/')) {
    return '/admin'
  }
  if (!value.startsWith('/admin')) {
    return '/admin'
  }
  return value
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) {
    await auth.bootstrap()
  }

  const requiresAuth = to.matched.some((item) => Boolean(item.meta?.requiresAuth))
  if (requiresAuth && !auth.isAuthenticated) {
    return {
      path: '/login',
      query: { redirect: to.fullPath }
    }
  }

  const publicOnly = to.matched.some((item) => Boolean(item.meta?.publicOnly))
  if (publicOnly && auth.isAuthenticated) {
    return resolveSafeRedirect(to.query.redirect)
  }

  return true
})

export default router
