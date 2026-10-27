<script setup>
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  questions: { type: Array, default: () => [] },
})
const emit = defineEmits(['submit'])

const selected = reactive({})
const shortAnswers = reactive({})
const submitted = ref(false)

const singleQuestions = computed(() => props.questions.filter((q) => q.type === 'single'))

const score = computed(() => {
  if (!singleQuestions.value.length) return 0
  const correct = singleQuestions.value.filter((q) => selected[q.id] === q.answer).length
  return Math.round((correct / singleQuestions.value.length) * 100)
})

const correctCount = computed(
  () => singleQuestions.value.filter((q) => selected[q.id] === q.answer).length,
)

function optionClass(question, option) {
  if (!submitted.value) {
    return { selected: selected[question.id] === option.key }
  }
  if (option.key === question.answer) return { correct: true }
  if (selected[question.id] === option.key) return { wrong: true }
  return {}
}

function submit() {
  if (submitted.value) return
  submitted.value = true
  emit('submit', {
    score: score.value,
    correct: correctCount.value,
    total: singleQuestions.value.length,
  })
}

function reset() {
  Object.keys(selected).forEach((key) => delete selected[key])
  Object.keys(shortAnswers).forEach((key) => delete shortAnswers[key])
  submitted.value = false
}
</script>

<template>
  <div class="quiz">
    <div v-for="question in questions" :key="question.id" class="question">
      <div class="question-head">
        <span class="question-no">{{ String(question.id).padStart(2, '0') }}</span>
        <div>
          <div class="question-text">{{ question.question }}</div>
          <div class="flex gap-8 mt-8">
            <span class="tag" :class="question.difficulty === '挑战' ? 'coral' : 'blue'">
              {{ question.difficulty }}
            </span>
            <span class="tag">{{ question.type === 'single' ? '单选' : '简答' }}</span>
          </div>
        </div>
      </div>

      <template v-if="question.type === 'single'">
        <label
          v-for="option in question.options"
          :key="option.key"
          class="option"
          :class="optionClass(question, option)"
        >
          <input
            v-model="selected[question.id]"
            type="radio"
            :name="`q-${question.id}`"
            :value="option.key"
            :disabled="submitted"
          />
          <span><strong>{{ option.key }}.</strong> {{ option.text }}</span>
        </label>
      </template>
      <template v-else>
        <textarea
          v-model="shortAnswers[question.id]"
          class="short-input"
          :disabled="submitted"
          placeholder="先写关键词，再补成完整句子……"
        ></textarea>
      </template>

      <div v-if="submitted" class="explanation">
        <strong>参考答案：</strong>{{ question.answer }}<br />
        <strong>解析：</strong>{{ question.explanation }}
      </div>
    </div>

    <div class="quiz-footer">
      <div class="small muted" v-if="submitted">
        单选得分 <strong style="color: var(--green)">{{ score }}</strong> · 答对
        {{ correctCount }}/{{ singleQuestions.length }}
      </div>
      <div class="small muted" v-else>简答题需要自评，系统按单选题计分。</div>
      <div class="flex gap-8">
        <button v-if="submitted" class="btn btn-ghost btn-small" @click="reset">重做</button>
        <button class="btn btn-primary btn-small" :disabled="submitted" @click="submit">
          提交并记录
        </button>
      </div>
    </div>
  </div>
</template>
