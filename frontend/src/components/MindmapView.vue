<script setup>
defineProps({
  nodes: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="mindmap">
    <ul class="mindmap-root">
      <li v-for="(node, index) in nodes" :key="index">
        <div class="node">
          <strong>{{ node.label }}</strong>
          <small>{{ node.description }}</small>
        </div>
        <ul class="mindmap-branch">
          <li v-for="(child, childIndex) in node.children || []" :key="childIndex">
            <div class="node">
              <strong>{{ child.label }}</strong>
              <small>{{ child.description }}</small>
            </div>
          </li>
        </ul>
      </li>
    </ul>
  </div>
</template>
