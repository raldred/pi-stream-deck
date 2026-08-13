import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { Agent,Workspace,Topology,View,worst,relativeTime,attachSubagents,attachWorkspaces,buildScene,rootDir,readAgents } from '../core.mjs'
import { paintKey, overflow } from '../render.mjs'

test('state priority and relative time',()=>{assert.equal(worst(['working','question','waiting']),'question');assert.equal(worst([]),'empty');assert.equal(relativeTime(9),'now');assert.equal(relativeTime(90),'1m')})
test('waiting decays and children attach',()=>{const now=2000,p=new Agent({sessionId:'p',pid:process.pid,state:'waiting',stateSince:now-1300,label:'main'}),c=new Agent({sessionId:'c',pid:process.pid,state:'working',role:'subagent',parentSessionId:'p',label:'child'});const out=attachSubagents([p,c]);assert.equal(out.length,1);assert.equal(p.children[0],c);assert.equal(p.effectiveState(now),'idle')})
test('topology overrides stale workspace id',()=>{const t=new Topology({windows:[{id:'win',workspaces:[{id:'new',title:'New',panes:[{surfaces:[{id:'s'}]}]}]}]}),a=new Agent({sessionId:'a',pid:process.pid,state:'working',label:'a',cmux:{workspaceId:'old',surfaceId:'s'}});const ws=attachWorkspaces(t,[a]);assert.equal(ws[0].agents[0],a);assert.equal(ws.some(x=>x.title==='elsewhere'),false)})
test('agent scene includes subagent badge and back key',()=>{const a=new Agent({sessionId:'a',pid:process.pid,state:'working',label:'main'});a.children=[new Agent({sessionId:'c',pid:process.pid,state:'working',label:'audit'})];const w=new Workspace({id:'w',title:'Project',agents:[a]});const [keys]=buildScene([w],new View('agents','w'),6,Date.now()/1000);assert.equal(keys[0].spec.subtitle,'⤷ audit');assert.equal(keys[0].spec.subagents,1);assert.equal(keys[5].spec.kind,'back')})
test('paths honour Pi agent directory and explicit override',()=>{assert.equal(rootDir({PI_CODING_AGENT_DIR:'/tmp/pi'}),'/tmp/pi/pi-stream-deck');assert.equal(rootDir({PI_CODING_AGENT_DIR:'/tmp/pi',PI_DECK_HOME:'/tmp/deck'}),'/tmp/deck')})
test('status reader ignores invalid and stale files',()=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'deck-'));fs.writeFileSync(path.join(dir,'bad.json'),'{');fs.writeFileSync(path.join(dir,'ok.json'),JSON.stringify({sessionId:'ok',pid:process.pid,state:'working',updatedAt:1000,label:'ok'}));assert.deepEqual(readAgents(dir,1001).map(x=>x.sessionId),['ok'])})
test('renderer returns rgba and detects overflow',()=>{const spec={kind:'agent',title:'a very long repository name',status:'working'};assert.equal(paintKey(spec).length,80*80*4);assert.equal(overflow(spec)[0],true)})
