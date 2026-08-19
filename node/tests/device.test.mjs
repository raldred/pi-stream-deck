import test from 'node:test'
import assert from 'node:assert/strict'
process.env.PI_DECK_HID_TIMEOUT_MS='25'
const { Deck, timed } = await import('../device.mjs')

test('timed passes through fast results and rejections',async()=>{assert.equal(await timed(Promise.resolve('ok'),50),'ok');await assert.rejects(timed(Promise.reject(new Error('boom')),50),/boom/)})
test('timed rejects when the operation hangs',async()=>{await assert.rejects(timed(new Promise(()=>{}),20),/hid operation timed out/)})
test('timed swallows late rejection after timing out',async()=>{let reject;const p=new Promise((_,r)=>{reject=r});await assert.rejects(timed(p,10));reject(new Error('late'));await new Promise(r=>setTimeout(r,10))})
test('tick closes the deck when a paint fails',async()=>{const d=new Deck();d.deck={clearPanel:async()=>{},close:async()=>{}};d.animated=new Set([0]);d.scene=[{kind:'agent',title:'x',status:'working'}];d.animate=async()=>{throw new Error('device not responding')};await d.tick();assert.equal(d.deck,null)})
test('close is safe on an unresponsive device',async()=>{const d=new Deck();d.deck={clearPanel:()=>new Promise(()=>{}),close:()=>new Promise(()=>{})};await d.close();assert.equal(d.deck,null)})
