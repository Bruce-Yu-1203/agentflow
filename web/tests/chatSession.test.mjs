import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiError } from '../src/api.js'
import { createChatSession } from '../src/chatSession.js'

test('a retry keeps the request ID and a follow-up uses the conversation ID', async () => {
  const calls = []
  let attempt = 0
  const session = createChatSession({ newId: () => `id-${++attempt}`, sendChat: async (body, connection) => {
    calls.push({ body, connection })
    if (calls.length === 1) throw new ApiError('Temporarily unavailable', 503, 'agent_failed', true)
    return { conv_id: 'conv-1', response: 'Done' }
  } })
  await assert.rejects(session.send('Hello', { baseUrl: 'http://api', token: '' }))
  assert.equal(session.pendingRequestId, 'id-1')
  await session.send('Hello', { baseUrl: 'http://api', token: '' })
  assert.equal(calls[0].body.client_request_id, calls[1].body.client_request_id)
  await session.send('Follow up', { baseUrl: 'http://api', token: '' })
  assert.equal(calls[2].body.conv_id, 'conv-1')
  assert.equal(calls[2].body.client_request_id, 'id-2')
})

test('new conversation ignores a late reply and resets context', async () => {
  let resolveReply
  const session = createChatSession({ newId: () => 'id', sendChat: () => new Promise((resolve) => { resolveReply = resolve }) })
  const sending = session.send('Hello', { baseUrl: 'http://api' })
  session.newConversation()
  resolveReply({ conv_id: 'old-conv', response: 'Late reply' })
  assert.equal(await sending, null)
  assert.equal(session.conversationId, null)
})

test('connection settings are snapshotted for an in-flight send', async () => {
  let captured
  const settings = { baseUrl: 'http://first', token: 'first-token' }
  const session = createChatSession({ newId: () => 'id', sendChat: async (_, connection) => {
    captured = connection
    settings.baseUrl = 'http://second'
    return { conv_id: 'conv', response: 'Done' }
  } })
  await session.send('Hello', settings)
  assert.equal(captured.baseUrl, 'http://first')
  assert.equal(captured.token, 'first-token')
  session.connectionChanged()
  assert.equal(session.conversationId, null)
})
