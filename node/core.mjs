import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const exec = promisify(execFile)
export const STATES = ['blocked','question','waiting','idle','compacting','working','ended']
export const NEEDS_YOU = new Set(['blocked','question','waiting','idle'])
export const STUCK_AFTER = 300, IDLE_AFTER = 1200, STALE_AFTER = 60

export function rootDir(env=process.env) {
  if (env.PI_DECK_HOME) return env.PI_DECK_HOME
  return path.join(env.PI_CODING_AGENT_DIR || path.join(os.homedir(), '.pi', 'agent'), 'pi-stream-deck')
}
export const statusDir = (env=process.env) => path.join(rootDir(env), 'status')
export const configFile = (env=process.env) => path.join(rootDir(env), 'config.json')
export const logFile = (env=process.env) => path.join(rootDir(env), 'pideck.log')
export function ensureDirs(env=process.env) { fs.mkdirSync(statusDir(env), {recursive:true, mode:0o700}) }

export function pidAlive(pid) {
  if (!pid) return false
  try { process.kill(pid, 0); return true } catch (e) { return e?.code === 'EPERM' }
}
export function stateRank(s) { const i=STATES.indexOf(s); return i < 0 ? STATES.length : i }
export function worst(states) { return states.length ? states.reduce((a,b)=>stateRank(a)<=stateRank(b)?a:b) : 'empty' }
export function relativeTime(seconds) {
  seconds=Math.max(0,Math.floor(seconds)); if(seconds<10)return 'now'; if(seconds<60)return `${seconds}s`
  if(seconds<3600)return `${Math.floor(seconds/60)}m`; if(seconds<86400)return `${Math.floor(seconds/3600)}h`; return `${Math.floor(seconds/86400)}d`
}
export class Agent {
  constructor(data={}, source='') {
    this.sessionId=data.sessionId||source; this.pid=data.pid; this.state=data.state||'idle'; this.label=data.label||'?'
    this.branch=data.branch; this.activity=data.activity; this.cwd=data.cwd; this.workspaceId=data.cmux?.workspaceId
    this.surfaceId=data.cmux?.surfaceId; this.updatedAt=Number(data.updatedAt||0); this.stateSince=Number(data.stateSince||data.updatedAt||0)
    this.source=source; this.role=data.role||'main'; this.parentSessionId=data.parentSessionId; this.children=[]
  }
  effectiveState(now=Date.now()/1000) { if(this.state==='ended'||(this.pid&&!pidAlive(this.pid)))return 'ended'; if(this.state==='waiting'&&now-this.stateSince>IDLE_AFTER)return 'idle'; return this.state }
  stuck(now=Date.now()/1000){return NEEDS_YOU.has(this.effectiveState(now))&&now-this.stateSince>STUCK_AFTER}
  ageSeconds(now=Date.now()/1000){return Math.max(0,now-(this.stateSince||this.updatedAt||now))}
  liveChildren(now=Date.now()/1000){return this.children.filter(a=>a.effectiveState(now)!=='ended')}
}
export class Workspace {
  constructor({id,title,windowId,index=0,selected=false,agents=[]}){this.id=id;this.title=title;this.windowId=windowId;this.index=index;this.selected=selected;this.agents=agents}
  liveAgents(now=Date.now()/1000){return this.agents.filter(a=>a.effectiveState(now)!=='ended')}
  state(now=Date.now()/1000){return worst(this.liveAgents(now).map(a=>a.effectiveState(now)))}
  subagentCount(now=Date.now()/1000){return this.liveAgents(now).reduce((n,a)=>n+a.liveChildren(now).length,0)}
  needsYou(now=Date.now()/1000){return this.liveAgents(now).filter(a=>NEEDS_YOU.has(a.effectiveState(now))).length}
  stuck(now=Date.now()/1000){return this.liveAgents(now).some(a=>a.stuck(now))}
  lastChange(now=Date.now()/1000){const xs=this.liveAgents(now).map(a=>a.stateSince||a.updatedAt).filter(Boolean);return xs.length?Math.max(...xs):null}
}

export function readAgents(dir=statusDir(), now=Date.now()/1000) {
  if(!fs.existsSync(dir))return []
  const out=[]
  for(const name of fs.readdirSync(dir).filter(x=>x.endsWith('.json')).sort()){
    const file=path.join(dir,name); let a
    try{a=new Agent(JSON.parse(fs.readFileSync(file,'utf8')),file)}catch{continue}
    const stale=now-(a.updatedAt||0)>STALE_AFTER
    if(a.state==='ended'||(stale&&!pidAlive(a.pid))){if(stale)try{fs.unlinkSync(file)}catch{};continue}
    out.push(a)
  }
  return out
}
export function attachSubagents(agents){
  const normal=agents.filter(a=>a.role!=='subagent'), ids=new Set(normal.map(a=>a.sessionId))
  const isMain=a=>a.role!=='subagent'||(a.parentSessionId===a.sessionId&&!ids.has(a.sessionId))
  const mains=agents.filter(isMain), subs=agents.filter(a=>!isMain(a)); mains.forEach(a=>a.children=[])
  const byId=new Map(mains.map(a=>[a.sessionId,a])), bySurface=new Map()
  for(const a of mains)if(a.surfaceId&&!bySurface.has(a.surfaceId))bySurface.set(a.surfaceId,a)
  const promoted=[]
  for(const sub of subs){const parent=byId.get(sub.parentSessionId)||bySurface.get(sub.surfaceId);if(!parent||parent===sub)promoted.push(sub);else parent.children.push(sub)}
  return [...mains,...promoted]
}

export class Topology {
  constructor(raw={}){this.raw=raw;this.workspaces=[];this.surfaces=new Map();for(const win of raw.windows||[])for(const ws of win.workspaces||[]){const surfaces=[];for(const pane of ws.panes||[])for(const s of pane.surfaces||[]){const r={id:s.id,title:s.title,type:s.type,tty:s.tty,workspaceId:ws.id,windowId:win.id,paneId:pane.id};surfaces.push(r);if(r.id)this.surfaces.set(r.id,r)}this.workspaces.push({id:ws.id,title:ws.title||'workspace',index:ws.index||0,selected:!!ws.selected,windowId:win.id,surfaces})}}
  workspace(id){return this.workspaces.find(w=>w.id===id)}
}
export function attachWorkspaces(topology, inputAgents, only=false){
  const agents=attachSubagents(inputAgents), grouped=new Map()
  for(const a of agents){const wid=topology.surfaces.get(a.surfaceId)?.workspaceId||a.workspaceId||'';if(!grouped.has(wid))grouped.set(wid,[]);grouped.get(wid).push(a)}
  const result=[]
  for(const ws of topology.workspaces){const mine=grouped.get(ws.id)||[];grouped.delete(ws.id);const order=new Map(ws.surfaces.map((s,i)=>[s.id,i]));mine.sort((a,b)=>(order.get(a.surfaceId)??999)-(order.get(b.surfaceId)??999)||a.label.localeCompare(b.label));if(!only||mine.length)result.push(new Workspace({...ws,agents:mine}))}
  const orphans=[...grouped.values()].flat().sort((a,b)=>a.label.localeCompare(b.label));if(orphans.length)result.push(new Workspace({id:'__orphans__',title:'elsewhere',agents:orphans}))
  return result
}

export class View { constructor(mode='workspaces',workspaceId=null,page=0){this.mode=mode;this.workspaceId=workspaceId;this.page=page} withPage(p){return new View(this.mode,this.workspaceId,p)} }
const blank=()=>({spec:{kind:'blank'},action:null})
export function paginate(items,slots,page){if(slots<=0)return [[],0,1,items.length];const pages=Math.max(1,Math.ceil(items.length/slots)),p=((page%pages)+pages)%pages,start=p*slots,v=items.slice(start,start+slots);return[v,p,pages,items.length-start-v.length]}
export function buildScene(workspaces,view=new View(),keyCount=6,now=Date.now()/1000){
  if(view.mode==='agents'){const ws=workspaces.find(w=>w.id===view.workspaceId);if(ws)return agentsScene(ws,view,keyCount,now);view=new View()}
  if(!workspaces.length){const keys=Array.from({length:keyCount},blank);keys[0]={spec:{kind:'message',text:'no cmux'},action:null};return[keys,new View()]}
  const pager=workspaces.length>keyCount,slots=pager?keyCount-1:keyCount,[visible,p,pages,remaining]=paginate(workspaces,slots,view.page),keys=Array.from({length:keyCount},blank)
  visible.forEach((w,i)=>keys[i]={spec:workspaceSpec(w,now),action:{type:'drill',workspaceId:w.id,windowId:w.windowId}})
  if(pager)keys[keyCount-1]={spec:{kind:'more',remaining:remaining>0?remaining:workspaces.length-visible.length},action:{type:'page',page:(p+1)%pages}}
  return[keys,new View('workspaces',null,p)]
}
function workspaceSpec(w,now){const a=w.liveAgents(now),last=w.lastChange(now);return{kind:'workspace',title:w.title,status:w.state(now),dots:a.map(x=>x.effectiveState(now)),count:a.length,subagents:w.subagentCount(now),age:last?relativeTime(now-last):null,selected:w.selected,stuck:w.stuck(now)}}
function agentsScene(w,view,n,now){const agents=w.liveAgents(now),pager=agents.length>n-1,slots=pager?n-2:n-1,[visible,p,pages,remaining]=paginate(agents,slots,view.page),keys=Array.from({length:n},blank);visible.forEach((a,i)=>keys[i]={spec:agentSpec(a,now),action:{type:'focus_agent',surfaceId:a.surfaceId,workspaceId:w.id,windowId:w.windowId,sessionId:a.sessionId}});if(!agents.length)keys[0]={spec:{kind:'message',text:'no agents'},action:null};if(pager)keys[slots]={spec:{kind:'more',remaining:Math.max(0,remaining)},action:{type:'page',page:(p+1)%pages}};keys[n-1]={spec:{kind:'back',title:w.title},action:{type:'back'}};return[keys,new View('agents',w.id,p)]}
function agentSpec(a,now){const c=a.liveChildren(now);return{kind:'agent',title:a.label,subtitle:c.length?(c.length===1?`⤷ ${c[0].label}`:`⤷ ${c.length} subagents`):(a.activity||a.branch),status:a.effectiveState(now),subagents:c.length,age:relativeTime(a.ageSeconds(now)),stuck:a.stuck(now)}}

export const DEFAULTS={brightness:60,poll_interval:1,topology_interval:3,topology_grace:20,agents_view_timeout:25,only_with_agents:false,focus_single_agent_directly:true,reconnect_interval:3}
export function loadConfig(env=process.env){let c={...DEFAULTS};try{c={...c,...JSON.parse(fs.readFileSync(configFile(env),'utf8'))}}catch{}return c}
export function cmuxBin(env=process.env){if(env.PI_DECK_CMUX_BIN)return env.PI_DECK_CMUX_BIN;for(const candidate of ['/opt/homebrew/bin/cmux','/usr/local/bin/cmux','/Applications/cmux.app/Contents/Resources/bin/cmux'])if(fs.existsSync(candidate))return candidate;return 'cmux'}
export async function cmuxRun(args,timeout=5000,env=process.env){try{return(await exec(cmuxBin(env),args,{timeout,env:{...env,CMUX_QUIET:'1'}})).stdout}catch(e){throw new Error((e.stderr||e.stdout||e.message||'cmux failed').trim())}}
export async function getTopology(){return new Topology(JSON.parse(await cmuxRun(['tree','--all','--json','--id-format','both'])))}
export async function rpc(method,params){const out=await cmuxRun(['rpc',method,JSON.stringify(params)]);return out.trim()?JSON.parse(out):{}}
export async function focusWorkspace(wid,windowId){if(windowId)try{await rpc('window.focus',{window_id:windowId})}catch{};await rpc('workspace.select',{workspace_id:wid});execFile('open',['-b','com.cmuxterm.app'],()=>{})}
export async function focusSurface(sid,wid,windowId){if(windowId)try{await rpc('window.focus',{window_id:windowId})}catch{};if(wid)try{await rpc('workspace.select',{workspace_id:wid})}catch{};await rpc('surface.focus',{surface_id:sid});execFile('open',['-b','com.cmuxterm.app'],()=>{})}
