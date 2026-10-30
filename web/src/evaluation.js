const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

export function createEvaluationController({ runJob, getJob, storage = sessionStorage, wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), intervalMs = 1500, maxErrors = 3 }) {
  let generation = 0
  let active = null
  const key = 'agentflow.activeEvaluationJob'

  function stop(clearJob = false) {
    generation += 1
    active?.abort()
    active = null
    if (clearJob) storage.removeItem(key)
  }

  async function follow(jobId, onUpdate) {
    stop()
    const epoch = generation
    const controller = new AbortController()
    active = controller
    storage.setItem(key, jobId)
    let errors = 0
    while (epoch === generation) {
      try {
        const job = await getJob(jobId, controller.signal)
        if (epoch !== generation) return null
        onUpdate(job)
        errors = 0
        if (TERMINAL.has(job.status)) {
          storage.removeItem(key)
          active = null
          return job
        }
      } catch (error) {
        if (epoch !== generation || error?.name === 'AbortError') return null
        errors += 1
        if (errors > maxErrors) {
          active = null
          throw new Error('Evaluation polling stopped after repeated API errors.')
        }
      }
      await wait(intervalMs)
    }
    return null
  }

  async function start(cases, onUpdate) {
    stop(true)
    const epoch = generation
    const job = await runJob(cases)
    if (epoch !== generation) return null
    onUpdate(job)
    return follow(job.job_id, onUpdate)
  }

  return {
    start,
    follow,
    stop,
    get activeJobId() { return storage.getItem(key) },
  }
}
