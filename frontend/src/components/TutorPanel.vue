<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import MarkdownView from './MarkdownView.vue'

const props = defineProps({
  studentId: { type: Number, default: null },
  resources: { type: Array, default: () => [] },
})
const emit = defineEmits(['notify', 'recorded'])

const question = ref('')
const asking = ref(false)
const selectedResource = ref('')
const history = ref([])
const chatList = ref(null)

const suggestions = [
  '同步和异步到底有什么区别？我总是搞混。',
  '为什么索引能加速查询？什么情况下反而不生效？',
  '学习一个新主题时，怎么判断自己是真的懂了？',
]

const resourceOptions = computed(() =>
  props.resources.map((item) => ({ id: item.id, title: item.title, type: item.type })),
)

function scrollToBottom() {
  nextTick(() => {
    if (chatList.value) chatList.value.scrollTop = chatList.value.scrollHeight
  })
}

function useSuggestion(text) {
  question.value = text
}

async function ask(text) {
  const content = (text ?? question.value).trim()
  if (!content || asking.value) return
  question.value = ''
  history.value.push({ role: 'user', content, created_at: new Date().toISOString() })
  scrollToBottom()
  asking.value = true
  try {
    const data = await api.askTutor({
      student_id: props.studentId,
      question: content,
      resource_id: selectedResource.value ? Number(selectedResource.value) : null,
    })
    history.value.push({
      role: 'assistant',
      content: data.answer,
      data,
      created_at: new Date().toISOString(),
    })
    emit('recorded')
    emit('notify', '辅导回答已生成，并记录为一次学习行为')
  } catch (error) {
    history.value.push({
      role: 'assistant',
      content: `这次答疑失败了：${error.message}`,
      created_at: new Date().toISOString(),
    })
    emit('notify', error.message, 'error')
  } finally {
    asking.value = false
    scrollToBottom()
  }
}

function formatTime(value) {
  return value ? new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''
}

async function loadHistory() {
  if (!props.studentId) return
  history.value = []
  try {
    const data = await api.tutorHistory(props.studentId)
    history.value = (data.dialogues || []).map((message) => ({
      role: message.role,
      content: message.content,
      created_at: message.created_at,
      data: message.role === 'assistant' ? message.meta : null,
    }))
    scrollToBottom()
  } catch (error) {
    emit('notify', error.message, 'error')
  }
}

watch(() => props.studentId, loadHistory)
onMounted(loadHistory)
</script>

<template>
  <div class="page">
    <div class="chat-shell" style="grid-template-columns: minmax(0, 1.4fr) minmax(270px, 0.6fr)">
      <section class="card chat-card" style="min-height: 660px">
        <div class="chat-head">
          <div>
            <h2 class="card-title">智能辅导</h2>
            <p class="card-sub">结合画像与资源上下文，先给结论，再拆解、类比、给下一步</p>
          </div>
          <span class="tag green">即时答疑</span>
        </div>

        <div ref="chatList" class="chat-list" style="max-height: 570px">
          <div v-if="!history.length" class="bubble assistant">
            把卡住的地方直接发给我。可以是一句概念疑问、一段报错，或者「我知道答案但讲不出来」。
            我会结合你的画像解释，并给出可执行的下一步。
          </div>

          <div v-for="(item, index) in history" :key="index">
            <div class="bubble" :class="item.role">
              <template v-if="item.role === 'user'">{{ item.content }}</template>
              <template v-else>
                <MarkdownView :content="item.content" />
                <template v-if="item.data">
                  <div class="divider"></div>
                  <div class="flex gap-8 center wrap">
                    <span class="tag amber">{{ item.data.provider === 'claude' ? 'Claude' : 'Mock' }}</span>
                    <span class="tag">{{ item.data.key_points?.length || 0 }} 个要点</span>
                    <span v-if="item.data.resource" class="tag blue">关联：{{ item.data.resource.title }}</span>
                  </div>
                  <div class="key-points">
                    <div v-for="point in item.data.key_points" :key="point" class="key-point">{{ point }}</div>
                  </div>
                  <div v-if="item.data.analogy" class="analogy">
                    <strong>类比：</strong>{{ item.data.analogy }}
                  </div>
                  <details v-if="item.data.diagram">
                    <summary class="small muted" style="cursor: pointer">查看结构图（Mermaid）</summary>
                    <pre class="diagram">{{ item.data.diagram }}</pre>
                  </details>
                  <div v-if="item.data.next_actions?.length" class="mt-14">
                    <div class="small" style="font-weight: 800; color: var(--ink); margin-bottom: 6px">下一步</div>
                    <div v-for="action in item.data.next_actions" :key="action" class="key-point">{{ action }}</div>
                  </div>
                </template>
              </template>
              <div class="bubble-meta">
                {{ item.role === 'user' ? '我' : '辅导智能体' }} · {{ formatTime(item.created_at) }}
              </div>
            </div>
          </div>

          <div v-if="asking" class="bubble assistant">
            <span class="spinner"></span>
            辅导智能体正在结合画像组织回答……
          </div>
        </div>

        <div class="chat-input">
          <div class="chips" style="margin-bottom: 9px">
            <button v-for="item in suggestions" :key="item" class="chip" @click="useSuggestion(item)">
              {{ item }}
            </button>
          </div>
          <textarea
            v-model="question"
            placeholder="例如：为什么 FastAPI 的依赖注入既能做参数校验又能做权限？"
            @keydown.enter.exact.prevent="ask()"
          ></textarea>
          <div class="chat-actions">
            <span class="small muted">Enter 发送 · 回答会写入对话与学习行为</span>
            <button class="btn btn-primary btn-small" :disabled="asking || !question.trim()" @click="ask()">
              <span v-if="asking" class="spinner"></span>
              提问
            </button>
          </div>
        </div>
      </section>

      <aside>
        <div class="card">
          <div class="card-head">
            <div>
              <h3 class="card-title">关联资源</h3>
              <p class="card-sub">可选，让回答围绕某份材料展开</p>
            </div>
          </div>
          <select v-model="selectedResource" class="select">
            <option value="">不关联具体资源</option>
            <option v-for="item in resourceOptions" :key="item.id" :value="item.id">
              {{ item.title }}
            </option>
          </select>
          <p class="form-hint mt-8">关联后，辅导智能体会读取资源摘要作为上下文。</p>
        </div>

        <div class="card mt-14" style="background: #f2faf8; border-color: #d8eee8">
          <h3 class="card-title">回答结构</h3>
          <div class="mt-8">
            <div class="key-point">一句话回答</div>
            <div class="key-point">拆开看：定位问题类型</div>
            <div class="key-point">结合画像：提醒你的易错点</div>
            <div class="key-point">类比 + 下一步动作</div>
          </div>
        </div>

        <div class="card mt-14">
          <h3 class="card-title">为什么不是直接给答案？</h3>
          <p class="card-sub" style="margin-top: 6px; line-height: 1.8">
            辅导的目标是让你下一次能独立解决同类问题。所以回答会刻意暴露判断路径，
            并把「下一步」写成可以立刻执行的动作。
          </p>
        </div>
      </aside>
    </div>
  </div>
</template>
