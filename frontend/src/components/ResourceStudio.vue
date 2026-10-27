<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import MarkdownView from './MarkdownView.vue'
import MindmapView from './MindmapView.vue'
import QuizView from './QuizView.vue'

const props = defineProps({
  studentId: { type: Number, default: null },
  resources: { type: Array, default: () => [] },
  meta: { type: Object, default: null },
  openResourceId: { type: Number, default: null },
})
const emit = defineEmits(['generated', 'notify', 'recorded', 'resource-opened', 'goto-path'])

const FALLBACK_TYPES = {
  document: '专业讲解文档',
  mindmap: '知识点思维导图',
  exercise: '分层练习题目',
  reading: '拓展阅读材料',
  code: '代码实操案例',
  video: '微课视频脚本',
}

const topic = ref('')
const requirements = ref('')
const selectedTypes = ref(Object.keys(FALLBACK_TYPES))
const generating = ref(false)
const result = ref(null)
const filter = ref('all')
const detail = ref(null)
const detailLoading = ref(false)
const copied = ref(false)

const typeEntries = computed(() => Object.entries(props.meta?.resource_types || FALLBACK_TYPES))
const filtered = computed(() =>
  filter.value === 'all'
    ? props.resources
    : props.resources.filter((item) => item.type === filter.value),
)
const countByType = computed(() => {
  const counts = {}
  props.resources.forEach((item) => {
    counts[item.type] = (counts[item.type] || 0) + 1
  })
  return counts
})

const pipelineAgents = [
  { name: 'planner', role: '教学规划智能体', note: '拆解目标与顺序' },
  { name: 'document_agent', role: '讲解文档智能体', note: '建立框架' },
  { name: 'mindmap_agent', role: '思维导图智能体', note: '结构化知识' },
  { name: 'exercise_agent', role: '出题智能体', note: '暴露易错点' },
  { name: 'reading_agent', role: '拓展阅读智能体', note: '延伸输入' },
  { name: 'code_agent', role: '代码实操智能体', note: '跑通最小示例' },
  { name: 'video_agent', role: '微课视频智能体', note: '多模态表达' },
  { name: 'reviewer', role: '质量审核智能体', note: '规则打分' },
]

const topicSuggestions = ['Python 异步编程', 'MySQL 索引与执行计划', 'FastAPI 依赖注入', '数据结构 · 二叉树']

function typeLabel(type) {
  return (props.meta?.resource_types || FALLBACK_TYPES)[type] || type
}

function toggleType(type) {
  if (selectedTypes.value.includes(type)) {
    selectedTypes.value = selectedTypes.value.filter((item) => item !== type)
  } else {
    selectedTypes.value = [...selectedTypes.value, type]
  }
}

function useTopic(value) {
  topic.value = value
}

async function generate() {
  if (!props.studentId) return
  if (!topic.value.trim()) {
    emit('notify', '先填一个学习主题，例如「Python 异步编程」', 'error')
    return
  }
  if (!selectedTypes.value.length) {
    emit('notify', '至少选择一种资源类型', 'error')
    return
  }
  generating.value = true
  result.value = null
  try {
    const data = await api.generateResources({
      student_id: props.studentId,
      topic: topic.value.trim(),
      requirements: requirements.value.trim(),
      types: selectedTypes.value,
    })
    result.value = data
    filter.value = 'all'
    emit('generated', data)
    emit('notify', `6 个智能体完成协作：${data.resources.length} 份资源，平均质量 ${data.avg_quality}`)
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    generating.value = false
  }
}

async function openDetail(id) {
  if (!id) return
  detailLoading.value = true
  try {
    detail.value = await api.resource(id)
    api.markView(id, 30).then(() => emit('recorded')).catch(() => {})
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    detailLoading.value = false
    emit('resource-opened')
  }
}

async function onQuizSubmit(payload) {
  if (!detail.value) return
  try {
    await api.addRecord({
      student_id: props.studentId,
      resource_id: detail.value.id,
      action: 'answer',
      score: payload.score,
      duration_sec: 600,
      detail: `完成分层练习，单选答对 ${payload.correct}/${payload.total}`,
    })
    emit('recorded')
    emit('notify', `练习已记录，得分 ${payload.score}`)
  } catch (error) {
    emit('notify', error.message, 'error')
  }
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText(detail.value?.meta?.code || '')
    copied.value = true
    setTimeout(() => (copied.value = false), 1400)
    emit('notify', '代码已复制')
  } catch {
    emit('notify', '浏览器不允许复制，请手动选择代码', 'error')
  }
}

watch(
  () => props.openResourceId,
  (id) => {
    if (id) openDetail(id)
  },
  { immediate: true },
)
</script>

<template>
  <div class="page">
    <section class="grid grid-2" style="grid-template-columns: minmax(0, 1.25fr) minmax(0, 0.75fr)">
      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">个性化资源生成台</h2>
            <p class="card-sub">一次任务，6 个专职智能体并行产出，1 个审核智能体打分</p>
          </div>
          <span class="tag amber">多智能体协作</span>
        </div>

        <div class="field">
          <label>学习主题</label>
          <input v-model="topic" class="input" placeholder="例如：Python 异步编程 / MySQL 索引 / 二叉树遍历" />
          <div class="chips" style="margin-top: 7px">
            <button v-for="item in topicSuggestions" :key="item" class="chip" @click="useTopic(item)">
              {{ item }}
            </button>
          </div>
        </div>

        <div class="field">
          <label>额外要求（可选）</label>
          <textarea
            v-model="requirements"
            class="textarea"
            placeholder="例如：面向后端实习，多给可运行示例；我容易混淆概念边界；希望每份材料都能在 30 分钟内完成。"
          ></textarea>
        </div>

        <div class="field">
          <label>资源类型</label>
          <div class="checkbox-grid">
            <label
              v-for="[type, label] in typeEntries"
              :key="type"
              class="check-item"
              :class="{ on: selectedTypes.includes(type) }"
            >
              <input
                type="checkbox"
                :checked="selectedTypes.includes(type)"
                @change="toggleType(type)"
              />
              <span>{{ label }}</span>
            </label>
          </div>
        </div>

        <div class="flex between center wrap gap-12" style="margin-top: 16px">
          <span class="form-hint">生成结果会落库，并记录每个 Agent 的状态与耗时。</span>
          <button class="btn btn-accent" :disabled="generating" @click="generate">
            <span v-if="generating" class="spinner"></span>
            {{ generating ? '智能体协作中…' : '启动多智能体生成' }}
          </button>
        </div>
      </div>

      <div class="card" style="background: #101c33; color: #e8eefc; border-color: #1b2d4d">
        <div class="card-head">
          <div>
            <h2 class="card-title" style="color: #fff">协作流水线</h2>
            <p class="card-sub" style="color: #91a4c5">规划串行 → 生成并行 → 审核收口</p>
          </div>
          <span v-if="generating" class="spinner"></span>
        </div>
        <div class="pipeline">
          <span
            v-for="agent in pipelineAgents"
            :key="agent.name"
            class="agent-chip"
            :class="{ active: generating }"
            style="background: rgba(255,255,255,.055); border-color: rgba(255,255,255,.1); color: #c9d6eb"
          >
            <span class="dot" :style="{ background: agent.name === 'reviewer' ? '#eaa63c' : '#6fa0e8' }"></span>
            {{ agent.role }}
          </span>
        </div>
        <div class="divider" style="background: rgba(255,255,255,.1)"></div>
        <div v-if="generating" class="loading-line" style="color: #a9b8d3">
          <span class="spinner"></span>
          6 个生成智能体正在并行工作，通常需要 2-10 秒…
        </div>
        <div v-else-if="result" class="small" style="color: #a9b8d3; line-height: 1.8">
          本次任务 <strong style="color: #f3c979">{{ result.task_id }}</strong><br />
          产出 {{ result.resources.length }} 份资源，平均质量
          <strong style="color: #7ddfb4">{{ result.avg_quality }}</strong> 分。<br />
          画像中的「{{ result.plan?.level || '当前水平' }}」已作为规划输入。
        </div>
        <div v-else class="small" style="color: #8697b5; line-height: 1.8">
          流水线会读取学生画像，为每类资源决定不同的切入点；生成后由规则审核智能体统一打分。
          没有 API Key 时使用 Mock 模板，流程完全一致。
        </div>
        <div v-if="result" class="chips" style="margin-top: 14px">
          <button class="btn btn-ghost btn-small" style="background: rgba(255,255,255,.08); color: #e8eefc; border-color: rgba(255,255,255,.15)" @click="emit('goto-path')">
            去看学习路径
          </button>
        </div>
      </div>
    </section>

    <section class="card mt-20">
      <div class="resource-toolbar">
        <div>
          <h2 class="card-title">资源库</h2>
          <p class="card-sub">{{ resources.length }} 份资源 · 点击卡片查看完整内容 / 做题 / 看微课</p>
        </div>
        <div class="type-filter">
          <button class="type-chip" :class="{ active: filter === 'all' }" @click="filter = 'all'">
            全部 {{ resources.length }}
          </button>
          <button
            v-for="[type, label] in typeEntries"
            :key="type"
            class="type-chip"
            :class="{ active: filter === type }"
            @click="filter = type"
          >
            {{ label }} {{ countByType[type] || 0 }}
          </button>
        </div>
      </div>

      <div v-if="generating" class="empty" style="padding: 36px 20px">
        <span class="spinner" style="width: 26px; height: 26px; border-width: 3px"></span>
        <strong style="margin-top: 12px">正在生成，请稍等</strong>
        <p>规划智能体先确定每类资源的切入点，然后 6 个生成智能体并行开工。</p>
      </div>

      <div v-else-if="filtered.length" class="resource-grid">
        <div
          v-for="resource in filtered"
          :key="resource.id"
          class="resource-card"
          :data-type="resource.type"
          @click="openDetail(resource.id)"
        >
          <div class="resource-top">
            <span class="type-badge">{{ typeLabel(resource.type) }}</span>
            <span class="quality">{{ resource.quality_score }}</span>
          </div>
          <h3 class="resource-title">{{ resource.title }}</h3>
          <p class="resource-summary">{{ resource.summary }}</p>
          <div class="resource-foot">
            <span>{{ resource.agent }}</span>
            <span>{{ resource.provider === 'claude' ? 'Claude' : 'Mock' }}</span>
          </div>
        </div>
      </div>

      <div v-else class="empty">
        <div class="empty-mark">✦</div>
        <strong>这个分类还没有资源</strong>
        <p>换一个主题生成一组，或切换到「全部」看看已有资源。</p>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="detail" class="modal-overlay" @click.self="detail = null">
        <div class="modal">
          <div class="modal-head">
            <div>
              <span class="type-badge">{{ typeLabel(detail.type) }}</span>
              <h2 class="modal-title">{{ detail.title }}</h2>
              <p class="modal-sub">{{ detail.summary }}</p>
              <div class="modal-meta">
                <span class="tag green">质量分 {{ detail.quality_score }}</span>
                <span class="tag">{{ detail.agent }}</span>
                <span class="tag blue">{{ detail.meta?.provider === 'claude' ? 'Claude' : 'Mock' }}</span>
                <span class="tag">耗时 {{ detail.meta?.duration_ms || 0 }}ms</span>
              </div>
            </div>
            <button class="modal-close" aria-label="关闭" @click="detail = null">×</button>
          </div>
          <div class="modal-body">
            <div v-if="detailLoading" class="loading-line"><span class="spinner"></span> 加载资源…</div>

            <template v-else-if="detail.type === 'document'">
              <MarkdownView :content="detail.content" />
            </template>

            <template v-else-if="detail.type === 'mindmap'">
              <MindmapView :nodes="detail.meta?.nodes || []" />
              <details class="mt-20">
                <summary class="small muted" style="cursor: pointer">查看 Mermaid 源码</summary>
                <pre class="diagram mt-8">{{ detail.meta?.markdown }}</pre>
              </details>
            </template>

            <template v-else-if="detail.type === 'exercise'">
              <div class="tag coral" style="margin-bottom: 14px">提交后自动记录学习行为</div>
              <QuizView :questions="detail.meta?.questions || []" @submit="onQuizSubmit" />
            </template>

            <template v-else-if="detail.type === 'reading'">
              <MarkdownView :content="detail.content" />
              <div class="mt-20">
                <h3 class="card-title">四条阅读路线</h3>
                <div v-for="item in detail.meta?.items || []" :key="item.title" class="dim-item mt-8">
                  <div class="dim-top">
                    <span class="dim-name">{{ item.title }}</span>
                    <span class="dim-source">{{ item.keywords?.join(' · ') }}</span>
                  </div>
                  <div class="dim-value">{{ item.reason }}</div>
                  <div class="small muted mt-8">检索提示：{{ item.search_hint }}</div>
                </div>
              </div>
            </template>

            <template v-else-if="detail.type === 'code'">
              <div class="flex between center gap-12" style="margin-bottom: 10px">
                <span class="tag amber">{{ detail.meta?.language || 'python' }}</span>
                <button class="btn btn-ghost btn-small" @click="copyCode">{{ copied ? '已复制' : '复制代码' }}</button>
              </div>
              <pre class="diagram">{{ detail.meta?.code }}</pre>
              <div class="mt-20">
                <h3 class="card-title">三个递进任务</h3>
                <ol class="small" style="line-height: 1.9; color: var(--ink-soft)">
                  <li v-for="task in detail.meta?.tasks || []" :key="task">{{ task }}</li>
                </ol>
              </div>
              <MarkdownView :content="detail.content" class="mt-20" />
            </template>

            <template v-else-if="detail.type === 'video'">
              <div v-if="detail.file_path" style="border-radius: 16px; overflow: hidden; border: 1px solid var(--line)">
                <iframe
                  :src="`/uploads/${detail.file_path}`"
                  title="微课视频"
                  style="width: 100%; height: 520px; border: 0; display: block; background: #0f1a2e"
                ></iframe>
              </div>
              <div class="mt-20">
                <h3 class="card-title">分镜脚本</h3>
                <div v-for="scene in detail.meta?.scenes || []" :key="scene.no" class="dim-item mt-8">
                  <div class="dim-top">
                    <span class="dim-name">镜头 {{ scene.no }} · {{ scene.title }}</span>
                    <span class="dim-source">{{ scene.duration }}s</span>
                  </div>
                  <div class="dim-value">画面：{{ scene.visual }}</div>
                  <div class="small muted mt-8">旁白：{{ scene.narration }}</div>
                </div>
              </div>
              <MarkdownView :content="detail.content" class="mt-20" />
            </template>

            <template v-else>
              <MarkdownView :content="detail.content" />
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
