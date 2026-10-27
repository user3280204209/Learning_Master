<script setup>
import { reactive, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'created', 'notify'])

const submitting = ref(false)
const form = reactive({
  name: '',
  major: '',
  age: 20,
  goal: '',
  email: '',
})

async function submit() {
  if (!form.name.trim()) {
    emit('notify', '请填写姓名', 'error')
    return
  }
  submitting.value = true
  try {
    const data = await api.createStudent({
      name: form.name.trim(),
      major: form.major.trim(),
      age: Number(form.age) || 0,
      goal: form.goal.trim(),
      email: form.email.trim(),
    })
    emit('created', data)
    emit('notify', `已创建学生画像：${data.student.name}`)
    form.name = ''
    form.major = ''
    form.goal = ''
    form.email = ''
    emit('close')
  } catch (error) {
    emit('notify', error.message, 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="props.open" class="modal-overlay" @click.self="emit('close')">
      <div class="modal" style="width: min(560px, 96vw)">
        <div class="modal-head">
          <div>
            <span class="tag amber">新学生</span>
            <h2 class="modal-title">创建学习画像</h2>
            <p class="modal-sub">先给一个目标，剩下的交给对话式画像构建</p>
          </div>
          <button class="modal-close" @click="emit('close')">×</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="field">
              <label>姓名 *</label>
              <input v-model="form.name" class="input" placeholder="例如：林小满" />
            </div>
            <div class="field">
              <label>年龄</label>
              <input v-model.number="form.age" class="input" type="number" min="0" max="120" />
            </div>
          </div>
          <div class="field">
            <label>专业</label>
            <input v-model="form.major" class="input" placeholder="例如：计算机科学与技术" />
          </div>
          <div class="field">
            <label>学习目标</label>
            <textarea
              v-model="form.goal"
              class="textarea"
              placeholder="例如：掌握 Python 后端与 AI 应用开发，完成一个可演示的多智能体系统"
            ></textarea>
          </div>
          <div class="field">
            <label>邮箱（可选）</label>
            <input v-model="form.email" class="input" placeholder="用于区分学生，不会公开" />
          </div>
          <div class="flex between center gap-12" style="margin-top: 18px">
            <span class="form-hint">创建后会初始化 7 个画像维度，可通过对话补全。</span>
            <button class="btn btn-primary" :disabled="submitting" @click="submit">
              <span v-if="submitting" class="spinner"></span>
              创建并进入
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
