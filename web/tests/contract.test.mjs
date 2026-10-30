import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('the console exposes the support workflows in English', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
  const readme = readFileSync(new URL('../../README.md', import.meta.url), 'utf8')
  assert.match(app, /AgentFlow/)
  assert.match(html, /AgentFlow Console/)
  assert.match(readme, /Run the web console/)
  assert.match(app, /type="text" required placeholder="http:\/\/localhost:8000 or \/api"/)
  assert.match(app, /!evaluationError && \(evaluationJob\?\.status === 'running'/)
  for (const label of ['Conversation', 'Knowledge', 'Skills', 'Evaluation', 'Operations', 'Connections']) {
    assert.match(app, new RegExp(label))
  }
  assert.doesNotMatch(app, /[\u3400-\u9fff]/)
})
