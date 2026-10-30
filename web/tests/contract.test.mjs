import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('the console shell identifies AgentFlow and checks API health', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  assert.match(app, /AgentFlow Console/)
  assert.match(app, /\/health/)
  assert.doesNotMatch(app, /[\u3400-\u9fff]/)
})
