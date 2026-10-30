<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ApiError, createApiClient } from './api.js'
import { createChatSession } from './chatSession.js'
import { createEvaluationController } from './evaluation.js'

const sections = [
  { id: 'chat', label: 'Conversation' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'skills', label: 'Skills' },
  { id: 'evaluation', label: 'Evaluation' },
  { id: 'monitor', label: 'Operations' },
  { id: 'connections', label: 'Connections' },
]
const section = ref('chat')
const baseUrl = ref(localStorage.getItem('agentflow.apiUrl') || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')
const draftUrl = ref(baseUrl.value)
const token = ref('')
const draftToken = ref('')
const health = ref({ state: 'checking', message: 'Checking API availability' })
const notices = ref({})
const draftMessage = ref('')
const messages = ref([])
const sending = ref(false)
let chatEpoch = 0
const latest = ref(null)
const trace = ref(null)
const searchQuery = ref('')
const searchResults = ref([])
const knowledgeStats = ref(null)
const documentTitle = ref('')
const documentId = ref('')
const documentContent = ref('')
const selectedFile = ref(null)
const skillsData = ref(null)
const monitorData = ref(null)
const recentTraces = ref([])
const embeddingData = ref(null)
const mcpData = ref(null)
const evaluationJob = ref(null)
const evaluationError = ref('')

const connection = () => ({ baseUrl: baseUrl.value, token: token.value })
const api = () => createApiClient(connection())
const session = createChatSession({ sendChat: (body, snapshot, signal) => createApiClient(snapshot).chat(body, signal) })
const evaluator = createEvaluationController({
  runJob: (cases) => api().runEvaluation(cases),
  getJob: (id, signal) => api().evaluationJob(id, signal),
})
const conversationLabel = computed(() => session.conversationId ? session.conversationId.slice(0, 12) : 'New conversation')

function showError(key, error) {
  notices.value[key] = error instanceof ApiError ? error.message : error?.message || 'The request could not be completed.'
}

async function checkHealth() {
  health.value = { state: 'checking', message: 'Checking API availability' }
  try {
    const data = await api().health()
    health.value = { state: 'online', message: data.status === 'ok' ? 'API available' : 'API needs attention' }
  } catch (error) {
    health.value = { state: 'offline', message: error.message }
  }
}

function saveConnection() {
  const next = draftUrl.value.trim().replace(/\/+$/, '')
  if (!/^https?:\/\/[^/]+/.test(next) && !/^\/[A-Za-z0-9/_-]+$/.test(next)) {
    notices.value.connections = 'Enter an HTTP or HTTPS API URL, or a same-origin path such as /api.'
    return
  }
  baseUrl.value = next
  token.value = draftToken.value
  localStorage.setItem('agentflow.apiUrl', next)
  session.connectionChanged()
  evaluator.stop(true)
  chatEpoch += 1
  sending.value = false
  messages.value = []
  latest.value = null
  trace.value = null
    notices.value.connections = 'Connection settings saved. The token remains in this tab until reload.'
  checkHealth()
}

function newConversation() {
  session.newConversation()
  chatEpoch += 1
  messages.value = []
  latest.value = null
  trace.value = null
  draftMessage.value = ''
  notices.value.chat = ''
  sending.value = false
}

async function sendMessage(existing = null) {
  if (sending.value) return
  const text = existing?.content || draftMessage.value.trim()
  if (!text) return
  notices.value.chat = ''
  const entry = existing || { id: crypto.randomUUID(), role: 'user', content: text, state: 'sending' }
  if (!existing) {
    messages.value.push(entry)
    draftMessage.value = ''
  }
  entry.state = 'sending'
  const epoch = chatEpoch
  sending.value = true
  try {
    const result = await session.send(text, connection())
    if (!result || epoch !== chatEpoch) return
    entry.state = 'sent'
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: result.response, state: result.status })
    latest.value = result
    trace.value = null
    if (result.status !== 'success') notices.value.chat = `The response status is ${result.status}. Review the request details.`
  } catch (error) {
    if (epoch !== chatEpoch) return
    entry.state = 'failed'
    showError('chat', error)
  } finally {
    if (epoch === chatEpoch) sending.value = false
  }
}

async function inspectTrace() {
  if (!latest.value?.request_id) return
  notices.value.inspector = ''
  try { trace.value = await api().trace(latest.value.request_id) }
  catch (error) { showError('inspector', error) }
}

async function searchKnowledge() {
  notices.value.knowledge = ''
  if (!searchQuery.value.trim()) return
  try { searchResults.value = (await api().search(searchQuery.value.trim())).results || [] }
  catch (error) { showError('knowledge', error) }
}

async function loadKnowledgeStats() {
  try { knowledgeStats.value = await api().knowledgeStats() }
  catch (error) { showError('knowledge', error) }
}

async function addDocument() {
  notices.value.knowledge = ''
  if (!documentTitle.value.trim() || !documentContent.value.trim()) {
    notices.value.knowledge = 'Enter a title and content before importing.'
    return
  }
  const document = { title: documentTitle.value.trim(), content: documentContent.value.trim() }
  if (documentId.value.trim()) document.document_id = documentId.value.trim()
  try {
    const result = await api().addKnowledge([document])
    notices.value.knowledge = `Imported ${result.added_chunks} chunks.`
    documentTitle.value = ''
    documentId.value = ''
    documentContent.value = ''
    await loadKnowledgeStats()
  } catch (error) { showError('knowledge', error) }
}

async function uploadDocument() {
  if (!selectedFile.value) {
    notices.value.knowledge = 'Choose a .txt, .md, or .json file first.'
    return
  }
  try {
    const result = await api().uploadKnowledge(selectedFile.value)
    notices.value.knowledge = `Imported ${result.added_chunks} chunks from ${selectedFile.value.name}.`
    selectedFile.value = null
    await loadKnowledgeStats()
  } catch (error) { showError('knowledge', error) }
}

async function loadSkills(reload = false) {
  notices.value.skills = ''
  try { skillsData.value = reload ? await api().reloadSkills() : await api().skills() }
  catch (error) { showError('skills', error) }
}

async function loadMonitor() {
  notices.value.monitor = ''
  try {
    const client = api()
    const [summary, recent] = await Promise.all([client.monitor(), client.recentTraces(10)])
    monitorData.value = summary
    recentTraces.value = recent.traces || []
  } catch (error) { showError('monitor', error) }
}

async function loadIntegrations() {
  notices.value.connections = ''
  try {
    const client = api()
    const [embedding, mcp] = await Promise.all([client.embedding(), client.mcp()])
    embeddingData.value = embedding
    mcpData.value = mcp
  } catch (error) { showError('connections', error) }
}

const fixedSuite = {
  intent_cases: [
    { message: 'Hello', expected_intent: 'greeting' },
    { message: 'Sign-in returns 401', expected_intent: 'technical_login' },
    { message: 'I need a refund', expected_intent: 'refund' },
  ],
  dialog_cases: [{ question: 'How can I check my order status?', expected_agent: 'general', expected_intent: 'order_status', reference_answer: 'Ask for an order ID and explain the approved status-check path.' }],
}

async function runEvaluation() {
  evaluationError.value = ''
  evaluationJob.value = null
  try { await evaluator.start(fixedSuite, (job) => { evaluationJob.value = job }) }
  catch (error) { evaluationError.value = error.message || 'Evaluation failed.' }
}

function selectSection(id) {
  section.value = id
  if (id === 'knowledge') loadKnowledgeStats()
  if (id === 'skills') loadSkills()
  if (id === 'monitor') loadMonitor()
  if (id === 'connections') loadIntegrations()
}

onMounted(() => {
  checkHealth()
  if (evaluator.activeJobId) {
    evaluator.follow(evaluator.activeJobId, (job) => { evaluationJob.value = job }).catch((error) => { evaluationError.value = error.message })
  }
})
onUnmounted(() => evaluator.stop())
</script>

<template>
  <div class="console-shell">
    <aside class="rail" aria-label="Main navigation">
      <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="brand-copy"><strong>AgentFlow</strong><small>Support console</small></div>
      <nav class="nav-list" aria-label="Workspace sections">
        <button v-for="item in sections" :key="item.id" type="button" :class="['nav-item', { active: section === item.id }]" :aria-current="section === item.id ? 'page' : undefined" @click="selectSection(item.id)">{{ item.label }}</button>
      </nav>
      <div class="rail-foot"><span class="status-light" :class="health.state"></span><span>{{ health.message }}</span></div>
    </aside>

    <div class="page">
      <header class="topbar">
        <div><p class="workspace-label">Customer support workspace</p><h1>{{ sections.find((item) => item.id === section)?.label }}</h1></div>
        <div class="top-actions"><span class="endpoint">{{ baseUrl }}</span><button class="quiet-button" type="button" @click="checkHealth">Check connection</button></div>
      </header>

      <main v-if="section === 'chat'" class="chat-layout">
        <section class="conversation-pane" aria-label="Conversation">
          <div class="pane-heading"><div><h2>Conversation</h2><p>{{ conversationLabel }}</p></div><button class="quiet-button" type="button" @click="newConversation">New conversation</button></div>
          <div class="conversation-stream" role="log" aria-live="polite">
            <div v-if="messages.length === 0" class="empty-state"><div class="empty-symbol" aria-hidden="true">↗</div><h3>Start with a customer question</h3><p>Ask about an order, a technical issue, or a billing concern. Routing details appear beside the reply.</p><button class="sample-button" type="button" @click="draftMessage = 'Sign-in returns 401 and I may have been charged twice'">Use a mixed issue example</button></div>
            <article v-for="item in messages" :key="item.id" :class="['message', item.role]"><div class="message-meta"><span>{{ item.role === 'user' ? 'You' : 'AgentFlow' }}</span><span v-if="item.state === 'sending'">Sending</span><span v-else-if="item.state === 'failed'">Delivery failed</span><span v-else-if="item.role === 'assistant' && item.state !== 'success'">{{ item.state }}</span></div><p>{{ item.content }}</p><button v-if="item.role === 'user' && item.state === 'failed'" class="inline-action" type="button" @click="sendMessage(item)">Retry this message</button></article>
          </div>
          <form class="composer" @submit.prevent="sendMessage()"><label for="chat-message">Message</label><textarea id="chat-message" v-model="draftMessage" rows="3" maxlength="12000" placeholder="Describe the issue and include any relevant reference or error code" @keydown.meta.enter.prevent="sendMessage()"></textarea><div class="composer-foot"><span>Press ⌘ Enter to send</span><button class="primary-button" type="submit" :disabled="sending || !draftMessage.trim()">{{ sending ? 'Sending…' : 'Send message' }}</button></div><p v-if="notices.chat" class="notice error" role="alert">{{ notices.chat }}</p></form>
        </section>
        <aside class="inspector" aria-label="Request details"><div class="pane-heading"><div><h2>Request details</h2><p>Routing and evidence</p></div></div><div v-if="!latest" class="inspector-empty">Send a message to inspect its intent, selected role, and tool use.</div><template v-else><div class="signal-block"><span class="signal-title">Outcome</span><strong :class="['outcome', latest.status]">{{ latest.status }}</strong><small>{{ latest.latency_ms?.toFixed(0) }} ms</small></div><dl class="detail-list"><div><dt>Intent</dt><dd>{{ latest.intent }} <small>{{ Math.round((latest.intent_confidence || 0) * 100) }}% confidence</small></dd></div><div><dt>Primary role</dt><dd>{{ latest.primary_agent }}</dd></div><div><dt>Supporting roles</dt><dd>{{ latest.supporting_agents?.join(', ') || 'None' }}</dd></div><div><dt>Route reason</dt><dd>{{ latest.routing_reason || 'No route reason provided' }}</dd></div><div><dt>Embedding source</dt><dd>{{ latest.intent_embedding_source || 'Unavailable' }}</dd></div><div><dt>Tools used</dt><dd>{{ latest.tools_used?.join(', ') || 'None' }}</dd></div><div><dt>Knowledge used</dt><dd>{{ latest.knowledge_used ? 'Yes' : 'No' }}</dd></div><div><dt>Request ID</dt><dd class="mono wrap">{{ latest.request_id }}</dd></div></dl><button class="quiet-button full" type="button" @click="inspectTrace">Load tool trace</button><p v-if="notices.inspector" class="notice error" role="alert">{{ notices.inspector }}</p><div v-if="trace" class="trace-box"><h3>Tool trace</h3><p v-if="!trace.found">No trace was retained for this request.</p><pre v-else>{{ JSON.stringify(trace.trace?.tools || [], null, 2) }}</pre></div></template></aside>
      </main>

      <main v-else-if="section === 'knowledge'" class="content-grid"><section class="workspace-card wide"><div class="section-heading"><div><h2>Search knowledge</h2><p>Inspect passages and source versions before using them in an answer.</p></div><span class="count-badge">{{ knowledgeStats?.total_chunks ?? '—' }} chunks</span></div><form class="inline-form" @submit.prevent="searchKnowledge"><label class="sr-only" for="knowledge-query">Search query</label><input id="knowledge-query" v-model="searchQuery" placeholder="Search approved guidance" /><button class="primary-button" type="submit">Search</button></form><p v-if="searchResults.length === 0" class="empty-line">No passages to show. Search for a topic after importing approved content.</p><article v-for="hit in searchResults" :key="hit.document_id + ':' + hit.chunk" class="search-hit"><div><strong>{{ hit.title }}</strong><span class="mono">{{ hit.document_id }} · chunk {{ hit.chunk + 1 }} · score {{ hit.score?.toFixed(2) }}</span></div><p>{{ hit.content }}</p><small class="mono">Version {{ hit.version?.slice(0, 12) }}</small></article></section><section class="workspace-card"><h2>Import a document</h2><p>Add approved content with a stable ID so later imports replace earlier chunks.</p><form class="stack-form" @submit.prevent="addDocument"><label for="doc-title">Title</label><input id="doc-title" v-model="documentTitle" required placeholder="Shipping policy" /><label for="doc-id">Document ID <span>Optional</span></label><input id="doc-id" v-model="documentId" placeholder="shipping-policy" /><label for="doc-content">Content</label><textarea id="doc-content" v-model="documentContent" rows="8" required placeholder="Paste approved English guidance"></textarea><button class="primary-button" type="submit">Import document</button></form><div class="upload-zone"><label for="knowledge-file">Upload .txt, .md, or .json</label><input id="knowledge-file" type="file" accept=".txt,.md,.json" @change="selectedFile = $event.target.files?.[0] || null" /><button class="quiet-button" type="button" @click="uploadDocument">Upload file</button></div></section><p v-if="notices.knowledge" class="notice" role="status">{{ notices.knowledge }}</p></main>

      <main v-else-if="section === 'skills'" class="single-column"><section class="workspace-card"><div class="section-heading"><div><h2>Business Skills</h2><p>Review the English guidance currently available to each role.</p></div><button class="quiet-button" type="button" @click="loadSkills(true)">Reload Skills</button></div><p v-if="notices.skills" class="notice error" role="alert">{{ notices.skills }}</p><p v-if="skillsData?.errors?.length" class="notice error" role="alert">{{ skillsData.errors.join('; ') }}</p><p v-if="!skillsData?.skills?.length" class="empty-line">No Skills are loaded. Check the configured Skills directory.</p><div class="skill-list"><article v-for="skill in skillsData?.skills || []" :key="skill.path" class="skill-row"><div><h3>{{ skill.name }}</h3><p>{{ skill.description }}</p><small>Applies to {{ skill.agents.join(', ') || 'all roles' }}</small></div><span :class="['pill', { muted: !skill.enabled }]">{{ skill.enabled ? 'Enabled' : 'Disabled' }}</span></article></div></section></main>

      <main v-else-if="section === 'evaluation'" class="single-column"><section class="workspace-card"><div class="section-heading"><div><h2>Fixed suite</h2><p>Run intent and conversation checks against the current model configuration.</p></div><button class="primary-button" type="button" :disabled="!evaluationError && (evaluationJob?.status === 'running' || evaluationJob?.status === 'queued')" @click="runEvaluation">Run evaluation</button></div><div class="suite-details"><span>3 intent cases</span><span>1 dialog case</span><span>Pass threshold 0.75</span></div><p v-if="evaluationError" class="notice error" role="alert">{{ evaluationError }}</p><div v-if="evaluationJob" class="evaluation-state"><div class="section-heading"><h3>{{ evaluationJob.status }}</h3><span>{{ evaluationJob.completed }} / {{ evaluationJob.total }} cases</span></div><progress :value="evaluationJob.completed" :max="evaluationJob.total || 1"></progress><p v-if="evaluationJob.error" class="notice error">{{ evaluationJob.error }}</p><pre v-if="evaluationJob.result">{{ JSON.stringify(evaluationJob.result, null, 2) }}</pre></div><p v-else class="empty-line">No evaluation is running in this browser session.</p></section></main>

      <main v-else-if="section === 'monitor'" class="single-column"><section class="workspace-card"><div class="section-heading"><div><h2>Runtime monitor</h2><p>Recent request volume and specialist health.</p></div><button class="quiet-button" type="button" @click="loadMonitor">Refresh</button></div><p v-if="notices.monitor" class="notice error" role="alert">{{ notices.monitor }}</p><div class="metric-strip"><div><strong>{{ monitorData?.recent_requests ?? '—' }}</strong><span>Recent requests</span></div><div><strong>{{ Object.keys(monitorData?.agents || {}).length }}</strong><span>Specialist roles observed</span></div></div><div class="monitor-list"><article v-for="(agent, role) in monitorData?.agents || {}" :key="role" class="monitor-row"><h3>{{ role }}</h3><span>{{ agent.samples }} samples</span><span>{{ agent.success_rate == null ? 'No rate yet' : Math.round(agent.success_rate * 100) + '% success' }}</span><span>{{ agent.cooldown_seconds ? agent.cooldown_seconds + 's cooldown' : 'Available' }}</span></article></div><h3 class="subheading">Recent traces</h3><p v-if="!recentTraces.length" class="empty-line">No requests have been recorded in this process.</p><article v-for="item in recentTraces" :key="item.request_id" class="recent-trace"><span class="mono">{{ item.request_id }}</span><span>{{ item.primary_agent }}</span><span :class="['outcome', item.status]">{{ item.status }}</span></article></section></main>

      <main v-else class="content-grid"><section class="workspace-card"><h2>API connection</h2><p>Choose the service used by this browser tab. The access token stays in memory and clears on reload.</p><form class="stack-form" @submit.prevent="saveConnection"><label for="api-base">API URL or path</label><input id="api-base" v-model="draftUrl" type="text" required placeholder="http://localhost:8000 or /api" /><label for="api-token">Bearer token <span>Optional in development</span></label><input id="api-token" v-model="draftToken" type="password" autocomplete="off" placeholder="Enter an access token" /><button class="primary-button" type="submit">Save connection</button></form><p v-if="notices.connections" class="notice" role="status">{{ notices.connections }}</p><div class="connection-state"><span class="status-light" :class="health.state"></span>{{ health.message }}</div></section><section class="workspace-card"><div class="section-heading"><div><h2>Integrations</h2><p>Read-only diagnostics for the configured vector and MCP services.</p></div><button class="quiet-button" type="button" @click="loadIntegrations">Refresh</button></div><h3 class="subheading">Intent embeddings</h3><p>{{ embeddingData?.last_source || embeddingData?.source || 'No embedding status loaded' }}</p><h3 class="subheading">MCP servers</h3><p v-if="!mcpData?.servers?.length">No external MCP servers configured.</p><article v-for="server in mcpData?.servers || []" :key="server.name" class="monitor-row"><strong>{{ server.name }}</strong><span>{{ server.transport }}</span><span>{{ server.status }}</span></article></section></main>
    </div>
  </div>
</template>

<style>
:root { font-family: 'Avenir Next', Avenir, 'Segoe UI', sans-serif; color: #173540; background: #edf2f2; font-synthesis: none; text-rendering: optimizeLegibility; }
* { box-sizing: border-box; }
body { margin: 0; }
button, input, textarea { font: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .55; }
button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 3px solid #e6ad57; outline-offset: 2px; }
.console-shell { display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: 100vh; }
.rail { display: flex; flex-direction: column; gap: 1.2rem; min-height: 100vh; padding: 2rem 1.2rem 1.5rem; color: #e8f4f3; background: #123744; }
.brand-mark { display: flex; align-items: end; gap: 4px; height: 30px; padding-left: 4px; }
.brand-mark span { width: 7px; background: #91d4c8; border-radius: 4px 4px 0 0; transform: skew(-14deg); }
.brand-mark span:nth-child(1) { height: 15px; }.brand-mark span:nth-child(2) { height: 27px; background: #edb35a; }.brand-mark span:nth-child(3) { height: 20px; }
.brand-copy { display: grid; gap: .15rem; padding: .2rem .5rem 1.4rem; border-bottom: 1px solid #42616b; }.brand-copy strong { font-size: 1.25rem; letter-spacing: -.03em; }.brand-copy small { color: #a9c5ca; }
.nav-list { display: grid; gap: .25rem; margin-top: .3rem; }.nav-item { width: 100%; border: 0; border-radius: 8px; background: transparent; color: #bbd0d4; padding: .8rem .9rem; text-align: left; font-weight: 600; }.nav-item.active { background: #285363; color: #fff; box-shadow: inset 3px 0 #edb35a; }.nav-item:hover:not(.active) { background: #204855; color: #fff; }
.rail-foot { display: flex; gap: .65rem; align-items: start; margin-top: auto; padding: 1rem .5rem 0; border-top: 1px solid #42616b; font-size: .78rem; line-height: 1.45; color: #bdd0d2; }
.status-light { flex: 0 0 auto; width: 9px; height: 9px; border-radius: 50%; background: #e6ad57; margin-top: .2rem; }.status-light.online { background: #82d4bb; }.status-light.offline { background: #df8892; }
.page { min-width: 0; }.topbar { display: flex; justify-content: space-between; gap: 1rem; align-items: end; min-height: 115px; padding: 1.6rem 2.2rem 1.45rem; background: #fff; border-bottom: 1px solid #d8e2e3; }.workspace-label { margin: 0 0 .35rem; font-size: .78rem; color: #50737d; }.topbar h1 { margin: 0; font-size: 2rem; letter-spacing: -.045em; line-height: 1; }.top-actions { display: flex; align-items: center; gap: 1rem; }.endpoint, .mono { font-family: 'SFMono-Regular', Consolas, monospace; font-size: .75rem; }.endpoint { color: #56727a; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.primary-button, .quiet-button, .sample-button { border-radius: 7px; padding: .7rem .9rem; font-size: .85rem; font-weight: 650; }.primary-button { border: 1px solid #0b6b69; background: #0b7471; color: #fff; }.primary-button:hover:not(:disabled) { background: #075e5c; }.quiet-button { border: 1px solid #cad9dc; background: #fff; color: #245462; }.quiet-button:hover { background: #eaf3f3; }.sample-button { border: 1px solid #bdd3d5; background: transparent; color: #1a6570; }.inline-action { border: 0; background: transparent; color: #086c6a; text-decoration: underline; padding: 0; font-weight: 700; }.full { width: 100%; }
.chat-layout { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(290px, .82fr); gap: 1.1rem; padding: 1.15rem; min-height: calc(100vh - 115px); }.conversation-pane, .inspector, .workspace-card { background: #fff; border: 1px solid #dbe5e6; border-radius: 12px; }.conversation-pane { display: flex; flex-direction: column; min-height: 610px; }.pane-heading, .section-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: start; }.pane-heading { padding: 1.4rem 1.6rem; border-bottom: 1px solid #e5eded; }.pane-heading h2, .workspace-card h2 { margin: 0; font-size: 1.12rem; letter-spacing: -.02em; }.pane-heading p, .section-heading p, .workspace-card > p { margin: .35rem 0 0; color: #668087; font-size: .86rem; line-height: 1.5; }
.conversation-stream { flex: 1; display: flex; flex-direction: column; gap: 1.2rem; overflow-y: auto; max-height: calc(100vh - 355px); min-height: 320px; padding: 1.7rem; }.empty-state { margin: auto; max-width: 330px; text-align: center; }.empty-symbol { display: grid; place-items: center; margin: 0 auto 1.1rem; width: 58px; height: 58px; border: 1px solid #b9d4d5; border-radius: 17px; color: #0f7773; font-size: 2.2rem; line-height: 1; }.empty-state h3 { margin: 0 0 .6rem; font-size: 1.3rem; }.empty-state p { margin: 0 0 1.2rem; line-height: 1.55; color: #617b82; }.message { max-width: 83%; padding: .95rem 1.05rem; border-radius: 10px; background: #ecf3f3; align-self: start; white-space: pre-wrap; }.message.user { align-self: end; background: #dcefed; }.message p { margin: .4rem 0 0; line-height: 1.55; overflow-wrap: anywhere; }.message-meta { display: flex; justify-content: space-between; gap: 1rem; font-size: .72rem; font-weight: 700; color: #3d666e; }.message .inline-action { margin-top: .75rem; }
.composer { padding: 1.25rem 1.5rem 1.4rem; border-top: 1px solid #e2eaea; }.composer label, .stack-form label { display: block; font-size: .82rem; font-weight: 700; color: #274650; margin-bottom: .45rem; }.composer textarea, .stack-form textarea, .stack-form input, .inline-form input { display: block; width: 100%; border: 1px solid #c9d9db; border-radius: 7px; color: #173540; background: #fff; padding: .75rem .85rem; resize: vertical; }.composer-foot { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: .7rem; }.composer-foot span { color: #71888d; font-size: .72rem; }.notice { margin: 1rem 0 0; color: #195e61; font-size: .85rem; line-height: 1.5; }.notice.error { color: #af3e4b; }
.inspector { padding-bottom: 1.4rem; align-self: stretch; }.inspector .pane-heading { margin-bottom: 1rem; }.inspector-empty { padding: 1.4rem 1.6rem; color: #667f85; line-height: 1.5; }.signal-block { display: flex; align-items: baseline; justify-content: space-between; gap: .6rem; margin: 0 1.4rem 1rem; padding: .9rem 1rem; border-radius: 8px; background: #edf4f4; }.signal-title, .signal-block small { color: #597780; font-size: .75rem; }.outcome { text-transform: capitalize; color: #0b7770; }.outcome.partial { color: #ae711f; }.outcome.failed { color: #ba4653; }.detail-list { margin: 0 1.4rem 1rem; }.detail-list div { padding: .75rem 0; border-bottom: 1px solid #e7eeee; }.detail-list dt { color: #668089; font-size: .72rem; margin-bottom: .28rem; }.detail-list dd { margin: 0; font-size: .86rem; font-weight: 600; overflow-wrap: anywhere; }.detail-list dd small { color: #668089; font-weight: 400; }.inspector .full, .inspector .notice, .trace-box { width: calc(100% - 2.8rem); margin-left: 1.4rem; }.trace-box { margin-top: 1rem; }.trace-box h3 { font-size: .9rem; }.trace-box pre, .evaluation-state pre { max-height: 260px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; background: #ecf2f2; padding: .8rem; border-radius: 6px; font-size: .75rem; }
.content-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(280px, .8fr); align-items: start; gap: 1.1rem; padding: 1.15rem; }.single-column { max-width: 1150px; padding: 1.15rem; }.workspace-card { padding: 1.55rem; }.workspace-card h3 { font-size: .95rem; }.count-badge, .pill { border-radius: 30px; background: #e6f1ee; color: #11685f; padding: .35rem .6rem; white-space: nowrap; font-size: .75rem; font-weight: 700; }.pill.muted { background: #eef0f0; color: #718286; }.inline-form { display: flex; gap: .6rem; margin-top: 1.4rem; }.inline-form input { flex: 1; }.empty-line { padding: 1.1rem 0; color: #6d8288; font-size: .86rem; }.search-hit { padding: 1.1rem 0; border-top: 1px solid #e3ebeb; }.search-hit:first-of-type { margin-top: 1rem; }.search-hit > div { display: flex; justify-content: space-between; gap: 1rem; }.search-hit .mono, .search-hit small { color: #698088; }.search-hit p { line-height: 1.55; margin: .65rem 0; }.stack-form { display: grid; gap: .5rem; margin-top: 1.3rem; }.stack-form label:not(:first-child) { margin-top: .6rem; }.stack-form label span { color: #72898e; font-weight: 400; }.stack-form .primary-button { justify-self: start; margin-top: .5rem; }.upload-zone { margin-top: 1.6rem; padding-top: 1.4rem; border-top: 1px solid #e0eaea; }.upload-zone label { display: block; font-size: .82rem; font-weight: 700; margin-bottom: .7rem; }.upload-zone input { width: 100%; font-size: .8rem; margin-bottom: .8rem; }
.skill-list { margin-top: 1.3rem; }.skill-row { display: flex; justify-content: space-between; gap: 1rem; padding: 1.2rem 0; border-top: 1px solid #e5eded; }.skill-row h3, .skill-row p { margin: 0 0 .35rem; }.skill-row p { color: #5e7a80; line-height: 1.5; }.skill-row small { color: #69848a; }.suite-details { display: flex; flex-wrap: wrap; gap: .6rem; margin: 1.4rem 0; }.suite-details span { background: #eaf2f3; border-radius: 6px; padding: .55rem .7rem; font-size: .78rem; color: #3d6872; }.evaluation-state { border-top: 1px solid #e4eded; padding-top: 1rem; }.evaluation-state h3 { margin: 0; text-transform: capitalize; }.evaluation-state progress { width: 100%; height: 10px; margin: 1rem 0; accent-color: #0b7770; }
.metric-strip { display: flex; gap: 2.5rem; margin: 1.5rem 0; padding: 1.3rem; background: #edf4f4; border-radius: 8px; }.metric-strip div { display: grid; gap: .2rem; }.metric-strip strong { font-size: 1.6rem; }.metric-strip span { color: #658088; font-size: .75rem; }.monitor-row, .recent-trace { display: flex; align-items: center; flex-wrap: wrap; gap: 1rem; padding: .9rem 0; border-top: 1px solid #e6eeee; }.monitor-row h3 { min-width: 110px; margin: 0; text-transform: capitalize; }.monitor-row span, .recent-trace span { color: #5c7a81; font-size: .82rem; }.recent-trace .outcome { margin-left: auto; }.subheading { margin: 1.6rem 0 .75rem; }.connection-state { display: flex; align-items: center; gap: .6rem; margin-top: 1.2rem; color: #54747b; font-size: .82rem; }.connection-state .status-light { margin-top: 0; }.wrap { overflow-wrap: anywhere; }.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
@media (max-width: 1100px) { .console-shell { grid-template-columns: 180px minmax(0, 1fr); }.chat-layout { grid-template-columns: minmax(0, 1fr); }.inspector { align-self: auto; }.content-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 700px) { .console-shell { display: block; }.rail { min-height: 0; padding: .7rem 1rem; gap: .5rem; }.brand-mark, .brand-copy small, .rail-foot { display: none; }.brand-copy { padding: .3rem; border: 0; }.nav-list { display: flex; overflow-x: auto; gap: .2rem; margin: 0; }.nav-item { width: auto; flex: 0 0 auto; white-space: nowrap; padding: .55rem .7rem; font-size: .78rem; }.topbar { min-height: 90px; padding: 1rem; align-items: center; }.topbar h1 { font-size: 1.45rem; }.top-actions { display: none; }.chat-layout, .content-grid, .single-column { padding: .6rem; }.conversation-pane { min-height: calc(100vh - 170px); }.conversation-stream { max-height: 55vh; }.pane-heading, .workspace-card { padding: 1rem; }.pane-heading { gap: .5rem; }.pane-heading .quiet-button { font-size: .7rem; }.message { max-width: 95%; }.inline-form { flex-direction: column; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; } }
</style>
