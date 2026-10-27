<script setup>
import { computed } from 'vue'

const props = defineProps({
  dimensions: { type: Array, default: () => [] },
})

const CX = 160
const CY = 150
const R = 90

function point(index, total, radius) {
  const angle = (-90 + (index * 360) / total) * (Math.PI / 180)
  return {
    x: CX + Math.cos(angle) * radius,
    y: CY + Math.sin(angle) * radius,
    angle,
  }
}

const items = computed(() => {
  const total = props.dimensions.length || 1
  return props.dimensions.map((item, index) => {
    const confidence = Math.max(0.12, Math.min(1, Number(item.confidence) || 0.2))
    const pointAt = point(index, total, R * confidence)
    const labelAt = point(index, total, R + 27)
    return {
      ...item,
      x: pointAt.x,
      y: pointAt.y,
      labelX: labelAt.x,
      labelY: labelAt.y,
      anchor: labelAt.x > CX + 4 ? 'start' : labelAt.x < CX - 4 ? 'end' : 'middle',
    }
  })
})

const polygon = computed(() => items.value.map((item) => `${item.x},${item.y}`).join(' '))

const grids = computed(() =>
  [0.33, 0.66, 1].map((ratio) =>
    props.dimensions
      .map((_, index) => {
        const p = point(index, props.dimensions.length, R * ratio)
        return `${p.x},${p.y}`
      })
      .join(' '),
  ),
)

const axes = computed(() =>
  props.dimensions.map((_, index) => point(index, props.dimensions.length, R)),
)
</script>

<template>
  <svg viewBox="0 0 320 300" width="100%" height="290" role="img" aria-label="学习画像雷达图">
    <polygon v-for="(grid, i) in grids" :key="i" :points="grid" class="radar-grid" />
    <line
      v-for="(axis, i) in axes"
      :key="`axis-${i}`"
      :x1="CX"
      :y1="CY"
      :x2="axis.x"
      :y2="axis.y"
      class="radar-axis"
    />
    <polygon :points="polygon" class="radar-shape" />
    <circle
      v-for="(item, i) in items"
      :key="`point-${i}`"
      :cx="item.x"
      :cy="item.y"
      r="3.4"
      class="radar-point"
    />
    <text
      v-for="(item, i) in items"
      :key="`label-${i}`"
      :x="item.labelX"
      :y="item.labelY"
      :text-anchor="item.anchor"
      class="radar-label"
      dominant-baseline="middle"
    >
      {{ item.dimension }}
    </text>
  </svg>
</template>
