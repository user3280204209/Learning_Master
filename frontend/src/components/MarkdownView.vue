<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  content: { type: String, default: '' },
})

marked.setOptions({ breaks: true, gfm: true })

const html = computed(() => {
  if (!props.content) return ''
  const raw = marked.parse(props.content)
  return DOMPurify.sanitize(raw, { ADD_ATTR: ['target'] })
})
</script>

<template>
  <div class="markdown" v-html="html"></div>
</template>
