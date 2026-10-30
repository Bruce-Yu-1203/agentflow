import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiError, createApiClient } from '../src/api.js'

test('chat requests use one base URL and a memory-only bearer token', async () => {
  const calls = []
  const client = createApiClient({ baseUrl: 'http://localhost:8000/', token: 'session-token', fetchImpl: async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ conv_id: 'conv-1', response: 'Hello' }), { status: 200 })
  } })
  await client.chat({ message: 'Hello', client_request_id: 'request-1' })
  assert.equal(calls[0].url, 'http://localhost:8000/chat')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer session-token')
  assert.equal(JSON.parse(calls[0].options.body).client_request_id, 'request-1')
})

test('API errors keep status, retryability, and readable validation text', async () => {
  const invalid = createApiClient({ baseUrl: 'http://api', fetchImpl: async () => new Response(JSON.stringify({ detail: [{ msg: 'Message is required' }] }), { status: 422 }) })
  await assert.rejects(invalid.chat({ message: '' }), (error) => error instanceof ApiError && error.status === 422 && error.message === 'Message is required' && !error.retryable)
  const failed = createApiClient({ baseUrl: 'http://api', fetchImpl: async () => new Response(JSON.stringify({ response: 'The request failed.', error_code: 'agent_failed', retryable: true }), { status: 503 }) })
  await assert.rejects(failed.chat({ message: 'Hello' }), (error) => error.status === 503 && error.code === 'agent_failed' && error.retryable)
})

test('network failures produce a retryable error', async () => {
  const client = createApiClient({ baseUrl: 'http://api', fetchImpl: async () => { throw new Error('offline') } })
  await assert.rejects(client.health(), (error) => error.code === 'network_error' && error.retryable)
})
