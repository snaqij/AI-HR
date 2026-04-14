import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/admin'
    },
    {
      path: '/admin',
      component: () => import('../layouts/AdminLayout.vue'),
      children: [
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
          name: 'Settings',
          component: () => import('../views/admin/Settings.vue')
        }
      ]
    },
    {
      path: '/interview/:id',
      name: 'InterviewRoom',
      component: () => import('../views/interview/InterviewRoom.vue')
    }
  ]
})

export default router
