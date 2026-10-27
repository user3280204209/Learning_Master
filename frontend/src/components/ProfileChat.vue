<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  studentId: { type: Number, default: null },
  profile: { type: Object, default: null },
})
const emit = defineEmits(['updated', 'notify'])

const messages = ref([])
const input = ref('')
const sending = ref(false)
const chatList = ref(null)
const lastChanges = ref([])

const dimensions = computed(() => props.profile?.dimensions || [])
const completeness = computed(() => props.profile?.completeness || 0)

const quickPrompts = [
  '我喜欢先看整体框架，再看代码例子。',
  '我每周大概能投入 8 小时，晚上学习效率最高。',
  '我总把同步和异步搞混，做算法题也容易错边界条件。',
]

const sourceLabels = {
  seed: '初始',
  dialogue: '对话',
  assessment: '评估',
  system: '系统',
  inferred: '推断',
}

function formatTime(value) {
  if (!value) return ''
  return String(value).slice(5, 16)
}

function scrollToBottom() {
  nextTick(() => {
    if (chatList.value) chatList.value.scrollTop = chatList.value.scrollHeight
  })
}

async function load() {
  if (!props.studentId) return
  messages.value = []
  lastChanges.value = []
  try {
    const data = await api.dialogues(props.studentId)
    messages.value = (data.dialogues || []).map((message) => ({
      ...message,
      changes: message.meta?.changes || [],
    }))
    scrollToBottom()
  } catch (error) {
    emit('notify', error.message, 'error')
  }
}

async function send(text) {
  const message = (text ?? input.value).trim()
  if (!message || sending.value) return
  input.value = ''
  sending.value = true
  messages.value.push({
    id: `local-${Date.now()}`,
    role: 'user',
    content: message,
    created_at: new Date().toISOString(),
  })
  scrollToBottom()

  try {
    const data = await api.chat(props.studentId, message)
    messages.value.push({
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: [data.reply, data.follow_up].filter(Boolean).join('\n\n'),
      created_at: new Date().toISOString(),
      meta: { provider: data.provider },
      changes: data.changes || [],
    })
    lastChanges.value = data.changes || []
    if (data.profile) emit('updated', data.profile)
    emit('notify', data.changes?.length ? `画像已更新 ${data.changes.length} 个维度` : '已回复并追问')
  } catch (error) {
    messages.value.push({
      id: `error-${Date.now()}`,
      role: 'assistant',
      content: `这次没有成功更新画像：${error.message}`,
      created_at: new Date().toISOString(),
    })
    emit('notify', error.message, 'error')
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function usePrompt(prompt) {
  input.value = prompt
}

watch(() => props.studentId, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="chat-shell">
      <section class="card chat-card">
        <div class="chat-head">
          <div>
            <h2 class="card-title">对话式画像构建</h2>
            <p class="card-sub">自然语言输入，画像抽取智能体自动识别线索并追问</p>
          </div>
          <span class="tag amber">随学随新</span>
        </div>

        <div ref="chatList" class="chat-list">
          <div v-if="!messages.length" class="bubble assistant">
            你好，我是画像构建助手。你可以直接说自己学过什么、喜欢怎样的学习方式、最近卡在哪里，
            我会把这些线索写进画像，并继续追问信息最少的维度。
          </div>

          <div v-for="(message, index) in messages" :key="message.id || index">
            <div class="bubble" :class="message.role">
              {{ message.content }}
              <div v-if="message.changes?.length" class="change-tags">
                <span v-for="change in message.changes" :key="change.dimension" class="tag green">
                  {{ change.dimension }} 已更新
                </span>
              </div>
              <div class="bubble-meta">
                {{ message.role === 'user' ? '我' : '画像智能体' }}
                · {{ formatTime(message.created_at) }}
              </div>
            </div>
          </div>

          <div v-if="sending" class="bubble assistant">
            <span class="spinner"></span>
            画像抽取智能体正在阅读这句话，识别稳定特征……
          </div>
        </div>

        <div class="chat-input">
          <div class="chips" style="margin-bottom: 10px">
            <button v-for="prompt in quickPrompts" :key="prompt" class="chip" @click="usePrompt(prompt)">
              {{ prompt }}
            </button>
          </div>
          <textarea
            v-model="input"
            placeholder="例如：我先看整体框架，再通过代码例子理解；每周大概 8 小时，数据结构比较薄弱……"
            @keydown.enter.exact.prevent="send()"
          ></textarea>
          <div class="chat-actions">
            <span class="small muted">Enter 发送 · Shift + Enter 换行</span>
            <button class="btn btn-primary btn-small" :disabled="sending || !input.trim()" @click="send()">
              <span v-if="sending" class="spinner"></span>
              发送
            </button>
          </div>
        </div>
      </section>

      <aside>
        <div class="card">
          <div class="card-head">
            <div>
              <h3 class="card-title">当前画像</h3>
              <p class="card-sub">{{ dimensions.length }} 个维度 · 随对话持续修正</p>
            </div>
            <span class="tag green">{{ completeness }}%</span>
          </div>

          <div class="dim-list">
            <div v-for="dimension in dimensions" :key="dimension.dimension" class="dim-item">
              <div class="dim-top">
                <span class="dim-name">{{ dimension.dimension }}</span>
                <span class="dim-source">{{ sourceLabels[dimension.source] || dimension.source }}</span>
              </div>
              <div class="dim-value">{{ dimension.value }}</div>
              <div class="bar">
                <div class="bar-fill" :style="{ width: `${Math.round((dimension.confidence || 0) * 100)}%` }"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="card mt-14">
          <h3 class="card-title">这次更新了什么？</h3>
          <p v-if="!lastChanges.length" class="card-sub" style="margin-top: 6px">
            发送一句话后，这里会显示本次被修改的维度。没有线索时，智能体会明确说「不更新」，避免过拟合。
          </p>
          <div v-else class="mt-8">
            <div v-for="change in lastChanges" :key="change.dimension" class="dim-item" style="margin-bottom: 8px">
              <div class="dim-top">
                <span class="dim-name">{{ change.dimension }}</span>
                <span class="tag green">置信度 {{ Math.round(change.confidence * 100) }}%</span>
              </div>
              <div class="dim-value">{{ change.new }}</div>
            </div>
          </div>
        </div>

        <div class="card mt-14" style="background: #fffaf0; border-color: #f4e3c5">
          <h3 class="card-title">设计原则</h3>
          <p class="card-sub" style="margin-top: 6px; line-height: 1.8">
            画像维度用「行」存储，而不是固定列；新增维度不需要改表结构。
            每次对话只更新有证据的维度，并保留置信度，方便后续评估修正。
          </p>
        </div>
      </aside>
    </div>
  </div>
</template>
