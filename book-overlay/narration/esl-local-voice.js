(() => {
  'use strict';
  if (window.ESLLocalVoice) return;
  const speech=()=>typeof window.SpeechSynthesisUtterance==='function'?window.speechSynthesis:null;
  const isUS=v=>v&&v.localService===true&&/^en[-_]US$/i.test(String(v.lang||''));
  const preferred=v=>/enhanced|premium|natural|neural|siri/i.test(String(v.name||''));
  const quality=v=>Number(preferred(v))*40+Number(v.default===true)*5;
  const engineVoices=()=>{try{return (speech()?.getVoices?.()||[]).filter(isUS).sort((a,b)=>quality(b)-quality(a));}catch(_){return [];}};
  const publicVoice=v=>({voiceURI:String(v.voiceURI||v.name),name:String(v.name||'US English voice'),lang:'en-US',preferred:preferred(v)});
  const voices=()=>engineVoices().map(publicVoice);
  const listeners=new Set();
  let active=null;
  function call(fn,...args){if(typeof fn==='function')try{fn(...args);}catch(_){}}
  function broadcast(){for(const listener of [...listeners])call(listener,voices());}
  speech()?.addEventListener?.('voiceschanged',broadcast);
  function parts(input){
    const text=String(input||'').trim();
    if(!text||text.length>100000)return [];
    const result=[];
    for(const para of text.split(/\n\s*\n/)){
      let s;
      try{s=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter('en-US',{granularity:'sentence'}).segment(para)].map(x=>x.segment):null;}catch(_){}
      if(!s)s=para.match(/[^.!?]+(?:[.!?]+|$)/g)||[para];
      const joined=[];
      for(const sentence of s){
        const part=sentence.trim();if(!part)continue;
        if(joined.length&&/\b(?:Dr|Mr|Mrs|Ms|Prof|Rev|Gen|Capt|Sgt)\.$/i.test(joined.at(-1)))joined[joined.length-1]+=' '+part;
        else joined.push(part);
      }
      for(const part of joined){
        for(const slice of part.match(/.{1,165}(?:\s|$)|\S+/gs)||[]){
          const str=slice.trim();if(!str)continue;
          const chars=Array.from(str);
          for(let at=0;at<chars.length;at+=170)result.push(chars.slice(at,at+170).join(''));
        }
      }
    }
    return result;
  }
  function clear(current,reason,error){
    if(active!==current)return false;
    active=null;
    if(error)call(current.options.onError,reason);
    else call(current.options.onEnd,reason);
    return true;
  }
  function abort(reason='stopped'){
    if(!active)return false;
    const last=active;active=null;
    try{last.engine.cancel();}catch(_){}
    call(last.options.onAbort||last.options.onEnd,reason);
    return true;
  }
  function start(text,options={}){
    const engine=speech(), own=engineVoices();
    const selected=options.voiceURI?own.find(v=>publicVoice(v).voiceURI===options.voiceURI):own[0];
    if(!engine||!selected){call(options.onError,'unavailable');return false;}
    const chunks=parts(text);
    if(!chunks.length){call(options.onError,'empty');return false;}
    abort('replaced');
    const raw=Number(options.rate);
    const rate=Number.isFinite(raw)?Math.min(1.25,Math.max(.65,raw)):.87;
    const current={engine,voice:selected,options,rate,index:0,started:false,phase:'playing',utterance:null,next:null};
    active=current;
    current.next=()=>{
      if(active!==current||current.phase==='paused')return;
      if(current.index>=chunks.length){clear(current,'finished',false);return;}
      try{
        const utterance=new window.SpeechSynthesisUtterance(chunks[current.index++]);current.utterance=utterance;
        utterance.voice=selected;utterance.lang='en-US';utterance.rate=rate;utterance.pitch=1;
        utterance.onstart=()=>{if(active===current&&!current.started){current.started=true;call(options.onStart,publicVoice(selected));}};
        utterance.onend=()=>{if(active!==current||current.utterance!==utterance)return;current.utterance=null;current.next();};
        utterance.onerror=()=>{if(active===current&&current.utterance===utterance)clear(current,'playback',true);};
        engine.speak(utterance);
      }catch(_){clear(current,'playback',true);}
    };
    try{if(engine.paused)engine.resume();}catch(_){}
    current.next();
    return active===current;
  }
  function pause(){
    if(!active||active.phase==='paused'||typeof active.engine.pause!=='function')return false;
    const current=active;
    try{current.phase='paused';current.engine.pause();return true;}catch(_){current.phase='playing';return false;}
  }
  function resume(){
    if(!active||active.phase!=='paused'||typeof active.engine.resume!=='function')return false;
    const current=active;
    try{current.phase='playing';current.engine.resume();if(!current.utterance)current.next();return true;}catch(_){current.phase='paused';return false;}
  }
  const state=()=>active?.phase||'idle';
  const subscribe=fn=>{if(typeof fn!=='function')return ()=>{};listeners.add(fn);call(fn,voices());return ()=>listeners.delete(fn);};
  window.ESLLocalVoice=Object.freeze({start,abort,pause,resume,state,voices,subscribe});
  window.addEventListener('pagehide',()=>abort());
})();
