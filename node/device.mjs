import { listStreamDecks, openStreamDeck } from '@elgato-stream-deck/node'
import { paintKey, overflow, subtitleOverflow, NEEDS_YOU } from './render.mjs'
const FRAME_MS=200,LONG_MS=550
function pulse(frame,stuck){const period=stuck?4:8,floor=stuck?.15:.5;return floor+(1-floor)*(.5+.5*Math.sin(2*Math.PI*(frame%period)/period))}
export class Deck {
  constructor(onPress){this.onPress=onPress;this.deck=null;this.scene=[];this.actions=[];this.animated=new Set();this.anim=new Map();this.down=new Map();this.longFired=new Set();this.frame=0}
  static async devices(){return listStreamDecks()}
  async open(brightness=60){const [info]=await listStreamDecks();if(!info)throw new Error('no Stream Deck found');this.deck=await openStreamDeck(info.path);this.buttons=this.deck.CONTROLS.filter(c=>c.type==='button'&&c.feedbackType==='lcd');this.size=this.buttons[0]?.pixelSize||{width:80,height:80};await this.deck.clearPanel();await this.deck.setBrightness(Math.max(0,Math.min(100,brightness)));this.deck.on('down',c=>{if(c.type==='button')this.down.set(c.index,Date.now())});this.deck.on('up',c=>{if(c.type!=='button')return;const start=this.down.get(c.index);this.down.delete(c.index);if(start==null||this.longFired.delete(c.index))return;this.emit(c.index,Date.now()-start>=LONG_MS)});this.deck.on('error',()=>this.close());return this}
  get keyCount(){return this.buttons?.length||6}
  async serial(){try{return await this.deck.getSerialNumber()}catch{return null}}
  start(){this.timer=setInterval(()=>this.tick(),FRAME_MS);this.timer.unref?.()}
  async close(){if(this.timer)clearInterval(this.timer);this.timer=null;try{await this.deck?.clearPanel()}catch{}try{await this.deck?.close()}catch{}this.deck=null}
  async setScene(specs){const next=Array.from({length:this.keyCount},(_,i)=>specs[i]||{kind:'blank'});for(let i=0;i<next.length;i++){const old=this.scene[i],spec=next[i];if(JSON.stringify(old)===JSON.stringify(spec))continue;const same=old&&['kind','title','subtitle','status'].every(k=>old[k]===spec[k]);if(!same)this.anim.delete(i);this.scene[i]=spec;const [to]=overflow(spec,this.size),[so]=subtitleOverflow(spec,this.size);if(to||so||NEEDS_YOU.has(spec.status)){this.animated.add(i);await this.animate(i,spec)}else{this.animated.delete(i);await this.paint(i,spec)}}}
  async paint(i,spec,opts={}){if(!this.deck)return;if(spec.kind==='blank')return this.deck.clearKey(i);await this.deck.fillKeyBuffer(i,paintKey(spec,this.size,opts),{format:'rgba'})}
  advance(s,w){if(s.hold<3)s.hold++;else{s.scroll+=3;if(s.scroll>=w+16){s.scroll=0;s.hold=0}}return s.scroll}
  async animate(i,spec){const [to,tw]=overflow(spec,this.size),[so,sw]=subtitleOverflow(spec,this.size),state=this.anim.get(i)||{title:{scroll:0,hold:0},sub:{scroll:0,hold:0}};this.anim.set(i,state);await this.paint(i,spec,{scroll:to?this.advance(state.title,tw):0,marquee:to,subScroll:so?this.advance(state.sub,sw):0,subMarquee:so,pulse:NEEDS_YOU.has(spec.status)?pulse(this.frame,spec.stuck):1})}
  async tick(){this.frame++;for(const i of this.animated)await this.animate(i,this.scene[i]);for(const [i,start] of this.down)if(!this.longFired.has(i)&&Date.now()-start>=LONG_MS){this.longFired.add(i);this.emit(i,true)}}
  emit(i,long){try{this.onPress?.(i,long)}catch{}}
}
