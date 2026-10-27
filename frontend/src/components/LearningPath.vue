<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  studentId: { type: Number, default: null },
  path: { type: Object, default: null },
})
const emit = defineEmits(['updated', 'notify', 'open-resource', 'goto-resources'])

const generating = ref(false)
const updating = ref(null)

const steps = computed(() => props.path?.steps || [])
const progress = computed(() => {
  if (!steps.value.length) return 0
  return Math.round((steps.value.filter((step) => step.completed).length / steps.value.length) * 100)
})
const totalMinutes = computed(() =>
  steps.value.reduce((sum, step) => sum + (Number(step.estimated_minutes) || 0), 0),
)

async function generate() {
  generating.value = true
  try {
    const data = await api.generatePath(props.studentId)
    emit('updated', data)
    emit('notify', '学习路径已生成：按「框架 → 直觉 → 实操 → 练习 → 复盘」排序')
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    generating.value = false
  }
}

async function toggleStep(step) {
  if (updating.value) return
  updating.value = step.no
  try {
    const data = await api.updateStep(props.path.id, step.no, !step.completed)
    emit('updated', data)
    emit('notify', step.completed ? `步骤 ${step.no} 已取消完成` : `步骤 ${step.no} 已完成`)
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    updating.value = null
  }
}
</script>

<template>
  <div class="page">
    <template v-if="path">
      <section class="card">
        <div class="path-head">
          <div>
            <span class="tag amber">个性化学习路径</span>
            <h1 class="path-title" style="margin-top: 10px">{{ path.title }}</h1>
            <p class="path-rationale">{{ path.rationale }}</p>
            <div class="flex gap-8 wrap mt-14">
              <span class="tag">{{ steps.length }} 个步骤</span>
              <span class="tag blue">约 {{ totalMinutes }} 分钟</span>
              <span class="tag green">{{ path.status || 'active' }}</span>
            </div>
          </div>
          <div class="progress-big">
            <strong>{{ progress }}%</strong>
            <span>路径完成度</span>
            <div class="bar" style="margin-top: 10px; width: 150px">
              <div class="bar-fill" :style="{ width: `${progress}%` }"></div>
            </div>
          </div>
        </div>
        <div class="divider"></div>
        <div class="flex between center wrap gap-12">
          <span class="small muted">
            路径会读取你的画像与已有资源；最近一次评估会改变下一次规划的输入。
          </span>
          <div class="flex gap-8">
            <button class="btn btn-ghost btn-small" @click="emit('goto-resources')">补充资源</button>
            <button class="btn btn-primary btn-small" :disabled="generating" @click="generate">
              <span v-if="generating" class="spinner"></span>
              {{ generating ? '规划中…' : '重新规划' }}
            </button>
          </div>
        </div>
      </section>

      <section class="card mt-20">
        <div class="card-head">
          <div>
            <h2 class="card-title">学习步骤</h2>
            <p class="card-sub">点击「标记完成」会写入数据库，并更新练习/评估数据</p>
          </div>
          <span class="tag green">{{ steps.filter((step) => step.completed).length }}/{{ steps.length }} 已完成</span>
        </div>

        <div class="steps">
          <div
            v-for="step in steps"
            :key="step.no"
            class="step"
            :class="{ done: step.completed }"
          >
            <div class="step-no">{{ step.completed ? '✓' : step.no }}</div>
            <div class="step-body">
              <div class="step-top">
                <div>
                  <h3 class="step-title">{{ step.title }}</h3>
                  <p class="step-objective">{{ step.objective }}</p>
                </div>
                <button
                  class="btn btn-small"
                  :class="step.completed ? 'btn-ghost' : 'btn-primary'"
                  :disabled="updating === step.no"
                  @click="toggleStep(step)"
                >
                  <span v-if="updating === step.no" class="spinner"></span>
                  {{ step.completed ? '取消完成' : '标记完成' }}
                </button>
              </div>

              <div class="step-meta">
                <span class="tag">约 {{ step.estimated_minutes }} 分钟</span>
                <span class="tag blue">{{ step.resources?.length || 0 }} 份资源</span>
              </div>

              <div v-if="step.resources?.length" class="step-resources">
                <button
                  v-for="resource in step.resources"
                  :key="resource.id"
                  class="step-resource"
                  @click="emit('open-resource', resource.id)"
                >
                  {{ resource.title }}
                </button>
              </div>

              <div class="step-foot">
                <span class="checkpoint">完成标准：{{ step.checkpoint }}</span>
                <span class="tag" :class="step.completed ? 'green' : ''">
                  {{ step.completed ? '已完成' : '待开始' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <template v-else>
      <div class="card">
        <div class="empty" style="padding: 70px 20px">
          <div class="empty-mark">↗</div>
          <strong>还没有学习路径</strong>
          <p>
            路径依赖已有的个性化资源。先去资源工坊生成一组材料，再由路径规划智能体安排顺序。
          </p>
          <div class="flex gap-8" style="justify-content: center">
            <button class="btn btn-ghost" @click="emit('goto-resources')">去生成资源</button>
            <button class="btn btn-accent" :disabled="generating" @click="generate">
              <span v-if="generating" class="spinner"></span>
              {{ generating ? '规划中…' : '直接尝试规划' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
