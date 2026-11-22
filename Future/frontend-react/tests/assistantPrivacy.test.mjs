import assert from 'node:assert/strict'
import test from 'node:test'
import {
  AI_CONVERSATIONS_KEY, AI_MEMORY_KEY, AI_PREFERENCES_KEY,
  loadAssistantConversations, saveAssistantConversations,
  loadAssistantMemory, saveAssistantMemory,
  loadAssistantPreferences, saveAssistantPreferences,
} from '../src/lib/aiAssistant.js'

test('assistant conversations, memory and microphone preferences stay within the verified account', () => {
  const data = new Map()
  const previous = globalThis.localStorage
  globalThis.localStorage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) }
  try {
    const history = [{ id: 'conversation-a', title: 'Account A secret', messages: [{ role: 'user', text: 'Private shipment details' }] }]
    data.set(AI_CONVERSATIONS_KEY, JSON.stringify(history))
    data.set(AI_MEMORY_KEY, JSON.stringify({ lastQuestion: 'Unowned legacy secret' }))
    data.set(AI_PREFERENCES_KEY, JSON.stringify({ backgroundListening: true }))
    assert.deepEqual(loadAssistantConversations('B'), [])
    assert.equal(loadAssistantMemory('/ai-chat', 'client', 'B').lastQuestion, '')
    assert.equal(loadAssistantPreferences('B').backgroundListening, false)
    saveAssistantConversations(history, 'A')
    saveAssistantMemory({ ...loadAssistantMemory('/ai-chat', 'client', 'A'), lastQuestion: 'A private question' }, 'A')
    saveAssistantPreferences({ mode: 'hidden', backgroundListening: true }, 'A')
    assert.equal(loadAssistantConversations('A')[0].messages[0].text, 'Private shipment details')
    assert.equal(loadAssistantMemory('/ai-chat', 'client', 'A').lastQuestion, 'A private question')
    assert.equal(loadAssistantPreferences('A').backgroundListening, true)
    assert.deepEqual(loadAssistantConversations('B'), [])
    assert.deepEqual(loadAssistantConversations(), [])
    assert.equal(loadAssistantMemory('/ai-chat', 'client', 'B').lastQuestion, '')
    assert.equal(loadAssistantPreferences('B').backgroundListening, false)
    const before = data.size
    saveAssistantConversations(history)
    saveAssistantMemory({ lastQuestion: 'Anonymous write' })
    saveAssistantPreferences({ backgroundListening: true })
    assert.equal(data.size, before)
  } finally {
    if (previous === undefined) delete globalThis.localStorage
    else globalThis.localStorage = previous
  }
})
