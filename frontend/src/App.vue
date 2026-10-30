<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from './api'
import DashboardView from './components/DashboardView.vue'
import ProfileChat from './components/ProfileChat.vue'
import ResourceStudio from './components/ResourceStudio.vue'
import LearningPath from './components/LearningPath.vue'
import TutorPanel from './components/TutorPanel.vue'
import AssessmentPanel from './components/AssessmentPanel.vue'
import UploadLab from './components/UploadLab.vue'
import CreateStudentModal from './components/CreateStudentModal.vue'

const tabs = [
  { key: 'dashboard', index: '01', label: '学习总览', title: '学习总览', sub: '画像、资源、路径与智能体运行轨迹' },
  { key: 'profile', index: '02', label: '画像对话', title: '对话式画像构建', sub: '用自然语言补全 7 个维度，随学随新' },
  { key: 'resources', index: '03', label: '资源工坊', title: '多智能体资源工坊', sub: '6 类资源并行生成，规划 — 生成 — 审核全链路' },
  { key: 'path', index: '04', label: '学习路径', title: '个性化学习路径', sub: '把资源组织成可执行、可检查的步骤' },
  { key: 'tutor', index: '05', label: '智能辅导', title: '智能辅导', sub: '结合画像与资源上下文即时答疑' },
  { key: 'assessment', index: '06', label: '学习评估', title: '学习效果评估', sub: '行为数据 → 评估 → 回写画像的闭环' },
  { key: 'upload', index: '07', label: '上传实验', title: '文件传输实验台', sub: '分片上传 · 断点续传 · 上传/下载进度条 · Range 下载' },
]

const activeTab = ref('dashboard')
const currentTab = computed(() => tabs.find((tab) => tab.key === activeTab.value) || tabs[0])

const students = ref([])
const currentId = ref(null)
const profile = ref(null)
const dashboard = ref(null)
const resources = ref([])
const path = ref(null)
const runs = ref([])
const records = ref([])
const stats = ref({})
const report = ref(null)
const meta = ref(null)
const health = ref(null)
const loading = ref(true)
const createOpen = ref(false)
const pendingResourceId = ref(null)
const toast = ref(null)
let toastTimer = null

const currentStudent = computed(
  () => students.value.find((student) => student.id === currentId.value) || profile.value?.student || null,
)

const llmMode = computed(() => {
  const provider = health.value?.llm?.provider || 'mock'
  return {
    label: provider === 'claude' ? 'Claude 已启用' : 'Mock 模式',
    mock: provider !== 'claude',
    model: health.value?.llm?.model || 'template-engine',
  }
})

function notify(message, type = 'success') {
  if (!message) return
  toast.value = { message, type }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = null), 3600)
}

async function optional(promise, fallback = null) {
  try {
    return await promise
  } catch {
    return fallback
  }
}

async function loadAll() {
  const id = currentId.value
  if (!id) return
  loading.value = true
  try {
    profile.value = await api.profile(id)
    dashboard.value = await optional(api.dashboard(id), dashboard.value)
    const resourceData = await optional(api.resources(id), { resources: [] })
    resources.value = resourceData.resources || []
    path.value = await optional(api.path(id), null)
    const runData = await optional(api.agentRuns(id, 60), { runs: [] })
    runs.value = runData.runs || []
    const recordData = await optional(api.records(id), { records: [], stats: {} })
    records.value = recordData.records || []
    stats.value = recordData.stats || {}
    report.value = await optional(api.latestReport(id), null)
  } catch (error) {
    notify(error.message, 'error')
  } finally {
    loading.value = false
  }
}

async function refreshAfterWrite() {
  const id = currentId.value
  if (!id) return
  const [dash, resourceData, runData, recordData, latest] = await Promise.all([
    optional(api.dashboard(id), dashboard.value),
    optional(api.resources(id), { resources: resources.value }),
    optional(api.agentRuns(id, 60), { runs: runs.value }),
    optional(api.records(id), { records: records.value, stats: stats.value }),
    optional(api.latestReport(id), report.value),
  ])
  dashboard.value = dash
  resources.value = resourceData.resources || []
  runs.value = runData.runs || []
  records.value = recordData.records || []
  stats.value = recordData.stats || stats.value
  report.value = latest
}

async function boot() {
  loading.value = true
  try {
    const [healthData, metaData] = await Promise.all([api.health(), api.meta()])
    health.value = healthData
    meta.value = metaData
  } catch (error) {
    notify(`无法连接后端：${error.message}`, 'error')
  }

  try {
    const data = await api.students()
    students.value = data.students || []
  } catch (error) {
    notify(`读取学生列表失败：${error.message}`, 'error')
  }

  const saved = Number(localStorage.getItem('learning.studentId'))
  if (saved && students.value.some((student) => student.id === saved)) {
    currentId.value = saved
  } else if (students.value.length) {
    currentId.value = students.value[0].id
  } else {
    loading.value = false
    createOpen.value = true
  }
}

watch(currentId, (id) => {
  if (!id) return
  localStorage.setItem('learning.studentId', String(id))
  loadAll()
})

function onProfileUpdated(payload) {
  profile.value = payload
  if (dashboard.value) dashboard.value = { ...dashboard.value, profile: payload }
}

function onGenerated() {
  refreshAfterWrite()
}

function onRecorded() {
  refreshAfterWrite()
}

function onEvaluated(payload) {
  if (payload.profile) profile.value = payload.profile
  if (payload.report) report.value = payload.report
  refreshAfterWrite()
}

function onPathUpdated(payload) {
  path.value = payload
  optional(api.dashboard(currentId.value)).then((data) => {
    if (data) dashboard.value = data
  })
}

function openResource(id) {
  pendingResourceId.value = id
  activeTab.value = 'resources'
  window.history.replaceState(null, '', `#resources/${id}`)
}

function onStudentCreated(payload) {
  const student = payload.student
  if (student && !students.value.some((item) => item.id === student.id)) {
    students.value = [student, ...students.value]
  }
  profile.value = payload
  currentId.value = student?.id || currentId.value
  createOpen.value = false
}

const visibleKeys = new Set(tabs.map((tab) => tab.key))

function syncFromHash() {
  const [key, id] = window.location.hash.replace('#', '').split('/')
  if (visibleKeys.has(key)) activeTab.value = key
  if (key === 'resources' && id) pendingResourceId.value = Number(id)
}

watch(activeTab, (key) => {
  const current = window.location.hash.replace('#', '').split('/')[0]
  if (current !== key) {
    window.history.replaceState(null, '', `#${key}`)
  }
})

onMounted(() => {
  syncFromHash()
  window.addEventListener('hashchange', syncFromHash)
  boot()
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncFromHash)
})

</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">知</div>
        <div class="brand-text">
          <strong>知径</strong>
          <span>Learning Multi-Agent</span>
        </div>
      </div>

      <nav class="nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="nav-index">{{ tab.index }}</span>
          <span class="nav-label">{{ tab.label }}</span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <div class="mode-card">
          <strong>运行环境</strong>
          <div class="flex between center">
            <span class="mode-pill" :class="{ mock: llmMode.mock }">
              <span class="dot"></span>{{ llmMode.label }}
            </span>
            <span class="small">{{ llmMode.model }}</span>
          </div>
          <div class="mt-8 flex between center">
            <span>MySQL 主从</span>
            <span :style="{ color: health?.database?.replica?.ok ? '#7ddfb4' : '#f3c979' }">
              {{ health?.database?.replica?.ok ? '3306 / 3307' : '已降级主库' }}
            </span>
          </div>
        </div>
        <div class="sidebar-note">
          画像作为共享黑板：所有智能体读取同一份画像，评估结果再写回它，形成学习闭环。
        </div>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="page-heading">
          <h1>{{ currentTab.title }}</h1>
          <p>{{ currentTab.sub }}</p>
        </div>
        <div v-if="activeTab !== 'upload'" class="topbar-actions">
          <select v-model.number="currentId" class="student-select" aria-label="选择学生">
            <option v-for="student in students" :key="student.id" :value="student.id">
              {{ student.name }} · {{ student.major || '未填专业' }}
            </option>
          </select>
          <button class="btn btn-ghost btn-small" @click="createOpen = true">+ 新学生</button>
          <button class="btn btn-ghost btn-small" @click="loadAll">刷新</button>
        </div>
      </header>

      <div v-if="loading && !profile" class="page">
        <div class="grid grid-4">
          <div v-for="i in 4" :key="i" class="skeleton" style="height: 100px"></div>
        </div>
        <div class="grid grid-2 mt-20">
          <div class="skeleton" style="height: 420px"></div>
          <div class="skeleton" style="height: 420px"></div>
        </div>
      </div>

      <template v-else>
        <DashboardView
          v-if="activeTab === 'dashboard'"
          :student="currentStudent"
          :profile="profile"
          :dashboard="dashboard"
          :runs="runs"
          :resources="resources"
          :health="health"
          :meta="meta"
          @navigate="activeTab = $event"
          @open-resource="openResource"
        />
        <ProfileChat
          v-else-if="activeTab === 'profile'"
          :student-id="currentId"
          :profile="profile"
          @updated="onProfileUpdated"
          @notify="notify"
        />
        <ResourceStudio
          v-else-if="activeTab === 'resources'"
          :student-id="currentId"
          :resources="resources"
          :meta="meta"
          :open-resource-id="pendingResourceId"
          @generated="onGenerated"
          @notify="notify"
          @recorded="onRecorded"
          @resource-opened="pendingResourceId = null"
          @goto-path="activeTab = 'path'"
        />
        <LearningPath
          v-else-if="activeTab === 'path'"
          :student-id="currentId"
          :path="path"
          @updated="onPathUpdated"
          @notify="notify"
          @open-resource="openResource"
          @goto-resources="activeTab = 'resources'"
        />
        <TutorPanel
          v-else-if="activeTab === 'tutor'"
          :student-id="currentId"
          :resources="resources"
          @notify="notify"
          @recorded="onRecorded"
        />
        <AssessmentPanel
          v-else-if="activeTab === 'assessment'"
          :student-id="currentId"
          :records="records"
          :stats="stats"
          :report="report"
          :resources="resources"
          @notify="notify"
          @updated="onEvaluated"
          @recorded="onRecorded"
        />
        <UploadLab
          v-else-if="activeTab === 'upload'"
          @notify="notify"
        />
      </template>
    </main>

    <CreateStudentModal
      :open="createOpen"
      @close="createOpen = false"
      @created="onStudentCreated"
      @notify="notify"
    />

    <div v-if="toast" class="toast" :class="toast.type">{{ toast.message }}</div>
  </div>
</template>
