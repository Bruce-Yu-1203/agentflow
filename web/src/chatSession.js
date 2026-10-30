export function createChatSession({ sendChat, newId = () => crypto.randomUUID() }) {
  let convId = null
  let generation = 0
  let active = null
  let retryAttempt = null

  function cancelActive() {
    active?.abort()
    active = null
  }

  function newConversation() {
    generation += 1
    cancelActive()
    convId = null
    retryAttempt = null
  }

  function connectionChanged() {
    newConversation()
  }

  async function send(message, connection) {
    const clean = message.trim()
    if (!clean) throw new Error('Enter a message before sending.')
    cancelActive()
    const epoch = ++generation
    const attempt = retryAttempt?.message === clean ? retryAttempt : { message: clean, requestId: newId() }
    retryAttempt = attempt
    const controller = new AbortController()
    active = controller
    const snapshot = { ...connection }
    const body = { message: clean, client_request_id: attempt.requestId }
    if (convId) body.conv_id = convId
    try {
      const response = await sendChat(body, snapshot, controller.signal)
      if (epoch !== generation || controller.signal.aborted) return null
      convId = response.conv_id
      retryAttempt = null
      return response
    } catch (error) {
      if (epoch !== generation || controller.signal.aborted) return null
      if (!error?.retryable) retryAttempt = null
      throw error
    } finally {
      if (active === controller) active = null
    }
  }

  return {
    send,
    newConversation,
    connectionChanged,
    get conversationId() { return convId },
    get retryMessage() { return retryAttempt?.message ?? null },
    get pendingRequestId() { return retryAttempt?.requestId ?? null },
  }
}
