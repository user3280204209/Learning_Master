<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  studentId: { type: Number, default: null },
  records: { type: Array, default: () => [] },
  stats: { type: Object, default: () => ({}) },
  report: { type: Object, default: null },
  resources: { type: Array, default: () => [] },
})
const emit = defineEmits(['notify', 'updated', 'recorded'])

const evaluating = ref(false)
const submitting = ref(false)
const localReport = ref(props.report)

const form = reactive({
  action: 'view',
  resource_id: '',
  score: 80,
  minutes: 15,
})

const dimensionEntries = computed(() => Object.entries(localReport.value?.dimensions || {}))
const actionLabels = { view: '浏览', answer: '答题', tutor: '辅导', feedback: '反馈' }

watch(
  () => props.report,
  (value) => {
    localReport.value = value
  },
)

function formatTime(value) {
  return value ? String(value).slice(5, 16) : ''
}

async function evaluate() {
  evaluating.value = true
  try {
    const data = await api.evaluate(props.studentId)
    localReport.value = data.report
    emit('updated', data)
    emit('notify', `评估完成：总分 ${data.report.overall_score}，结果已回写画像`)
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    evaluating.value = false
  }
}

async function addManualRecord() {
  if (submitting.value) return
  submitting.value = true
  try {
    await api.addRecord({
      student_id: props.studentId,
      resource_id: form.resource_id ? Number(form.resource_id) : null,
      action: form.action,
      score: form.action === 'answer' ? Number(form.score) : null,
      duration_sec: Number(form.minutes) * 60,
      detail: '手动补充的学习行为',
    })
    emit('recorded')
    emit('notify', '学习行为已记录')
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <section class="grid grid-4">
      <div class="metric">
        <div class="metric-value">{{ stats.actions || 0 }}<small>次</small></div>
        <div class="metric-label">学习行为</div>
      </div>
      <div class="metric">
        <div class="metric-value">{{ stats.minutes || 0 }}<small>分钟</small></div>
        <div class="metric-label">累计投入</div>
      </div>
      <div class="metric">
        <div class="metric-value">{{ stats.answers || 0 }}<small>次</small></div>
        <div class="metric-label">完成答题</div>
      </div>
      <div class="metric">
        <div class="metric-value">{{ stats.avg_score || 0 }}<small>分</small></div>
        <div class="metric-label">答题平均分</div>
      </div>
    </section>

    <section class="grid grid-2 mt-20" style="grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr)">
      <div class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">学习效果评估</h2>
            <p class="card-sub">评估智能体读取行为记录，输出 7 维评分并回写画像</p>
          </div>
          <button class="btn btn-accent btn-small" :disabled="evaluating" @click="evaluate">
            <span v-if="evaluating" class="spinner"></span>
            {{ evaluating ? '评估中…' : '生成评估报告' }}
          </button>
        </div>

        <template v-if="localReport">
          <div class="report-score">
            <div class="score-circle" :style="{ '--score': `${localReport.overall_score}%` }">
              <div class="score-inner">
                <div>
                  <strong>{{ localReport.overall_score }}</strong>
                  <span>OVERALL</span>
                </div>
              </div>
            </div>
            <div>
              <div class="flex gap-8 center wrap">
                <span class="tag green">已回写画像</span>
                <span class="tag">{{ localReport.source === 'claude' ? 'Claude' : 'Mock' }}</span>
                <span class="tag blue">{{ formatTime(localReport.created_at) }}</span>
              </div>
              <p class="path-rationale">{{ localReport.summary }}</p>
            </div>
          </div>

          <div class="divider"></div>

          <div v-for="[name, score] in dimensionEntries" :key="name" class="score-bar">
            <span>{{ name }}</span>
            <span class="score-track"><i :style="{ width: `${score}%` }"></i></span>
            <strong>{{ score }}</strong>
          </div>

          <div class="report-grid mt-20">
            <div>
              <h3 class="card-title" style="color: var(--green)">优势</h3>
              <div v-for="item in localReport.strengths || []" :key="item" class="key-point mt-8">{{ item }}</div>
            </div>
            <div>
              <h3 class="card-title" style="color: var(--coral)">待改进</h3>
              <div v-for="item in localReport.weaknesses || []" :key="item" class="key-point mt-8">{{ item }}</div>
            </div>
          </div>

          <div class="card mt-20" style="background: #fffaf0; border-color: #f4e3c5; box-shadow: none">
            <h3 class="card-title">下一步建议</h3>
            <div v-for="item in localReport.suggestions || []" :key="item" class="key-point mt-8">{{ item }}</div>
          </div>
        </template>

        <div v-else class="empty" style="padding: 38px 20px">
          <div class="empty-mark">◷</div>
          <strong>还没有评估报告</strong>
          <p>先浏览资源、完成一次练习，或者手动补充一条学习行为，然后生成报告。</p>
          <button class="btn btn-accent btn-small" :disabled="evaluating" @click="evaluate">直接评估当前数据</button>
        </div>
      </div>

      <div>
        <div class="card">
          <div class="card-head">
            <div>
              <h3 class="card-title">补充一条学习行为</h3>
              <p class="card-sub">用于演示或补录线下学习</p>
            </div>
          </div>
          <div class="form-row">
            <div class="field">
              <label>行为类型</label>
              <select v-model="form.action" class="select">
                <option value="view">浏览资源</option>
                <option value="answer">完成答题</option>
                <option value="tutor">发起辅导</option>
                <option value="feedback">提交反馈</option>
              </select>
            </div>
            <div class="field">
              <label>用时（分钟）</label>
              <input v-model.number="form.minutes" class="input" type="number" min="0" max="600" />
            </div>
          </div>
          <div class="field">
            <label>关联资源（可选）</label>
            <select v-model="form.resource_id" class="select">
              <option value="">不关联</option>
              <option v-for="resource in resources" :key="resource.id" :value="resource.id">
                {{ resource.title }}
              </option>
            </select>
          </div>
          <div v-if="form.action === 'answer'" class="field">
            <label>得分</label>
            <input v-model.number="form.score" class="input" type="number" min="0" max="100" />
          </div>
          <button class="btn btn-ghost w-100" :disabled="submitting" @click="addManualRecord">
            <span v-if="submitting" class="spinner"></span>
            记录行为
          </button>
        </div>

        <div class="card mt-14">
          <div class="card-head">
            <div>
              <h3 class="card-title">最近学习行为</h3>
              <p class="card-sub">评估的原始数据来源</p>
            </div>
            <span class="tag">{{ records.length }} 条</span>
          </div>
          <div v-if="records.length" class="record-list">
            <div v-for="record in records" :key="record.id" class="record-row">
              <span class="record-action" :class="record.action">{{ actionLabels[record.action] || record.action }}</span>
              <span class="record-title">{{ record.resource_title || record.detail || '—' }}</span>
              <span class="record-time">
                {{ record.score != null ? `${record.score} 分 · ` : '' }}{{ formatTime(record.created_at) }}
              </span>
            </div>
          </div>
          <div v-else class="empty" style="padding: 26px 10px">
            <strong>还没有行为记录</strong>
            <p>打开一份资源、完成一次练习，或使用上方表单补录。</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
