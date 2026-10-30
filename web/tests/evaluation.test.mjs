import assert from 'node:assert/strict'
import test from 'node:test'
import { createEvaluationController } from '../src/evaluation.js'

function memoryStorage() {
  const values = new Map()
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) }
}

test('evaluation polling reports progress and clears a completed job', async () => {
  const storage = memoryStorage()
  const states = ['queued', 'running', 'completed']
  const updates = []
  const controller = createEvaluationController({ storage, wait: async () => {}, runJob: async () => ({ job_id: 'job-1', status: 'queued', completed: 0, total: 2 }), getJob: async () => ({ job_id: 'job-1', status: states.shift(), completed: states.length === 0 ? 2 : 1, total: 2 }) })
  const result = await controller.start({ intent_cases: [] }, (job) => updates.push(job.status))
  assert.equal(result.status, 'completed')
  assert.deepEqual(updates, ['queued', 'queued', 'running', 'completed'])
  assert.equal(controller.activeJobId, null)
})

test('polling stops after bounded transient errors', async () => {
  const controller = createEvaluationController({ storage: memoryStorage(), wait: async () => {}, maxErrors: 2, runJob: async () => ({ job_id: 'job-2' }), getJob: async () => { throw new Error('temporary') } })
  await assert.rejects(controller.follow('job-2', () => {}), /repeated API errors/)
})

test('stopping a pending evaluation prevents a late job from being followed', async () => {
  const storage = memoryStorage()
  let release
  const controller = createEvaluationController({ storage, runJob: () => new Promise((resolve) => { release = resolve }), getJob: async () => { throw new Error('Should not poll') } })
  const pending = controller.start({}, () => {})
  controller.stop(true)
  release({ job_id: 'late-job', status: 'queued' })
  assert.equal(await pending, null)
  assert.equal(controller.activeJobId, null)
})
