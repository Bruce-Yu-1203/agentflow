<script setup lang="ts">
import { onMounted, ref } from 'vue'

const status = ref('Checking API availability')
const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

onMounted(async () => {
  try {
    const response = await fetch(`${baseUrl}/health`)
    status.value = response.ok ? 'API available' : 'API unavailable'
  } catch {
    status.value = 'API unavailable'
  }
})
</script>

<template>
  <main>
    <h1>AgentFlow Console</h1>
    <p>The support workspace is being prepared.</p>
    <p role="status">{{ status }}</p>
  </main>
</template>

<style scoped>
main { max-width: 48rem; margin: 5rem auto; padding: 2rem; font-family: system-ui, sans-serif; line-height: 1.5; }
h1 { font-size: 2rem; }
</style>
