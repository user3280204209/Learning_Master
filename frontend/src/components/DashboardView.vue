<script setup>
import { computed } from 'vue'
import ProfileRadar from './ProfileRadar.vue'

const props = defineProps({
  student: { type: Object, default: null },
  profile: { type: Object, default: null },
  dashboard: { type: Object, default: null },
  runs: { type: Array, default: () => [] },
  resources: { type: Array, default: () => [] },
  health: { type: Object, default: null },
  meta: { type: Object, default: null },
})
const emit = defineEmits(['navigate', 'open-resource'])

const circumference = 2 * Math.PI * 58
const dimensions = computed(() => props.profile?.dimensions || [])
const completeness = computed(() => props.profile?.completeness || 0)
const dash = computed(
  () => `${(completeness.value / 100) * circumference} ${circumference}`,
)
const recentRuns = computed(() => [...props.runs].slice(-8).reverse())
const recentResources = computed(() => props.resources.slice(0, 3))
const pathInfo = computed(() => props.dashboard?.path || { steps: 0, completed: 0 })
const records = computed(() => props.dashboard?.records || { actions: 0, minutes: 0, avg_score: 0 })
const typeLabels = computed(() => props.meta?.resource_types || {})

const llmMode = computed(() => {
  const provider = props.health?.llm?.provider || 'mock'
  return {
    label: provider === 'claude' ? 'Claude 真实模型' : 'Mock 模板引擎',
    mock: provider !== 'claude',
    model: props.health?.llm?.model || 'template-engine',
  }
})

function formatTime(value) {
  return value ? String(value).slice(5, 16) : ''
}

function statusLabel(status) {
  return { success: '成功', failed: '失败', fallback: '降级' }[status] || status
}
</script>

<template>
  <div class="page">
    <template v-if="dashboard && profile">
      <section class="hero">
        <div class="hero-content">
          <div class="hero-kicker"><span class="dot"></span> PERSONAL LEARNING WORKBENCH</div>
          <h1 class="hero-name">{{ student?.name }}</h1>
          <div class="hero-major">{{ student?.major }} · 目标：{{ student?.goal }}</div>
          <p class="hero-goal">
            这里不是资源仓库，而是一条闭环：对话更新画像 → 6 个智能体协作生成资源 →
            路径规划 → 学习行为 → 评估回写画像。当前画像已覆盖
            {{ dimensions.length }} 个维度，最近一次更新来自
            {{ dimensions[0]?.source === 'assessment' ? '学习评估' : '对话 / 种子数据' }}。
          </p>
          <div class="hero-actions">
            <button class="btn btn-accent" @click="emit('navigate', 'profile')">继续完善画像</button>
            <button class="btn btn-ghost" @click="emit('navigate', 'resources')">生成一组新资源</button>
          </div>
        </div>
        <div class="hero-side">
          <div class="completeness">
            <div class="ring">
              <svg width="148" height="148" viewBox="0 0 148 148">
                <circle cx="74" cy="74" r="58" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="9" />
                <circle
                  cx="74"
                  cy="74"
                  r="58"
                  fill="none"
                  stroke="#eaa63c"
                  stroke-width="9"
                  stroke-linecap="round"
                  :stroke-dasharray="dash"
                />
              </svg>
              <div class="ring-value">
                <div>
                  <strong>{{ completeness }}%</strong>
                  <span>画像完整度</span>
                </div>
              </div>
            </div>
            <p>7 个维度 · 置信度加权展示</p>
          </div>
        </div>
      </section>

      <section class="grid grid-4 mt-20">
        <div class="metric">
          <div class="metric-value">{{ dashboard.resource_total || 0 }}<small>份</small></div>
          <div class="metric-label">已生成个性化资源</div>
          <div class="metric-trend">{{ Object.keys(dashboard.resource_counts || {}).length }} 种类型</div>
        </div>
        <div class="metric">
          <div class="metric-value">{{ pathInfo.completed || 0 }}<small>/ {{ pathInfo.steps || 0 }}</small></div>
          <div class="metric-label">学习路径步骤完成</div>
          <div class="metric-trend">{{ pathInfo.steps ? Math.round((pathInfo.completed / pathInfo.steps) * 100) : 0 }}% 进度</div>
        </div>
        <div class="metric">
          <div class="metric-value">{{ records.minutes || 0 }}<small>分钟</small></div>
          <div class="metric-label">累计学习投入</div>
          <div class="metric-trend">{{ records.actions || 0 }} 次行为记录</div>
        </div>
        <div class="metric">
          <div class="metric-value">{{ runs.length }}<small>次</small></div>
          <div class="metric-label">智能体运行记录</div>
          <div class="metric-trend">可追踪 · 可复盘</div>
        </div>
      </section>

      <section class="grid grid-2 mt-20" style="grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr)">
        <div class="card">
          <div class="card-head">
            <div>
              <h2 class="card-title">画像雷达</h2>
              <p class="card-sub">半径 = 该维度的置信度；越靠外，画像越确定</p>
            </div>
            <span class="tag amber">{{ dimensions.length }} 维</span>
          </div>
          <div class="radar-wrap">
            <ProfileRadar :dimensions="dimensions" />
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <h2 class="card-title">智能体运行轨迹</h2>
              <p class="card-sub">规划 → 并行生成 → 审核，全链路可追踪</p>
            </div>
            <button class="btn btn-ghost btn-small" @click="emit('navigate', 'resources')">去生成</button>
          </div>
          <div v-if="recentRuns.length" class="timeline">
            <div v-for="run in recentRuns" :key="run.id" class="agent-run">
              <span class="status-dot" :class="run.status"></span>
              <div style="min-width: 0">
                <div class="flex gap-8 center">
                  <span class="agent-name">{{ run.role || run.agent }}</span>
                  <span class="tag" :class="run.status === 'failed' ? 'coral' : run.status === 'fallback' ? 'amber' : 'green'">
                    {{ statusLabel(run.status) }}
                  </span>
                </div>
                <div class="agent-role">{{ run.agent }} · {{ run.model }}</div>
                <div class="agent-summary">{{ run.output_summary || run.error || run.input_summary }}</div>
              </div>
              <div class="agent-time">{{ run.duration_ms }}ms<br />{{ formatTime(run.created_at) }}</div>
            </div>
          </div>
          <div v-else class="empty" style="padding: 30px 10px">
            <div class="empty-mark">◎</div>
            <strong>还没有智能体运行记录</strong>
            <p>生成一组资源，就能看到规划、生成、审核的完整轨迹。</p>
          </div>
        </div>
      </section>

      <section class="grid grid-2 mt-20" style="grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr)">
        <div class="card">
          <div class="card-head">
            <div>
              <h2 class="card-title">最近生成的资源</h2>
              <p class="card-sub">点击卡片查看完整内容</p>
            </div>
            <button class="btn btn-ghost btn-small" @click="emit('navigate', 'resources')">全部资源</button>
          </div>
          <div v-if="recentResources.length" class="resource-grid">
            <div
              v-for="resource in recentResources"
              :key="resource.id"
              class="resource-card"
              :data-type="resource.type"
              @click="emit('open-resource', resource.id)"
            >
              <div class="resource-top">
                <span class="type-badge">{{ typeLabels[resource.type] || resource.type }}</span>
                <span class="quality">{{ resource.quality_score }}</span>
              </div>
              <h3 class="resource-title">{{ resource.title }}</h3>
              <p class="resource-summary">{{ resource.summary }}</p>
              <div class="resource-foot">
                <span>{{ resource.agent }}</span>
                <span>{{ formatTime(resource.created_at) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty" style="padding: 30px 10px">
            <div class="empty-mark">✦</div>
            <strong>资源工坊还是空的</strong>
            <p>输入一个主题，让 6 个智能体并行产出讲解、导图、练习、阅读、代码和微课。</p>
            <button class="btn btn-accent btn-small" @click="emit('navigate', 'resources')">开始生成</button>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div>
              <h2 class="card-title">学习闭环状态</h2>
              <p class="card-sub">当前运行环境与最近评估</p>
            </div>
            <span class="mode-pill" :class="{ mock: llmMode.mock }">
              <span class="dot"></span>{{ llmMode.label }}
            </span>
          </div>
          <div class="dim-item">
            <div class="dim-top">
              <span class="dim-name">大模型适配层</span>
              <span class="tag">{{ llmMode.model }}</span>
            </div>
            <div class="dim-value">
              {{ llmMode.mock ? '未配置 API Key，使用确定性模板生成；配置 .env 后可切换 Claude。' : '已启用 Claude 结构化输出，失败会自动重试并降级。' }}
            </div>
          </div>
          <div class="dim-item mt-8">
            <div class="dim-top">
              <span class="dim-name">数据库读写分离</span>
              <span class="tag" :class="health?.database?.replica?.ok ? 'green' : 'amber'">
                {{ health?.database?.replica?.ok ? '主从正常' : '已降级主库' }}
              </span>
            </div>
            <div class="dim-value">
              写操作走 3306 主库；读操作走 3307 从库。写后立刻读的接口显式使用主库，避免主从延迟。
            </div>
          </div>
          <div class="dim-item mt-8">
            <div class="dim-top">
              <span class="dim-name">最近一次评估</span>
              <span class="tag blue">{{ dashboard.assessment?.overall_score ?? '—' }} 分</span>
            </div>
            <div class="dim-value">
              {{ dashboard.assessment?.summary || '还没有评估报告。完成几次学习行为后，在学习评估页生成报告。' }}
            </div>
          </div>
          <button class="btn btn-ghost btn-small mt-14" @click="emit('navigate', 'assessment')">
            查看学习评估
          </button>
        </div>
      </section>
    </template>

    <template v-else>
      <div class="grid grid-4">
        <div v-for="i in 4" :key="i" class="skeleton" style="height: 104px"></div>
      </div>
      <div class="grid grid-2 mt-20">
        <div class="skeleton" style="height: 360px"></div>
        <div class="skeleton" style="height: 360px"></div>
      </div>
    </template>
  </div>
</template>
