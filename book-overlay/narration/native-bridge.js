/* Optional local US narration; original MP3s and exercises remain available. */
let eslVoiceChoice = "";
function eslVoice() { return window.ESLLocalVoice || null; }
function eslStartVoice(text, opts={}) {
  const voice=eslVoice();
  if (!voice?.voices().length) return false;
  const selected=opts.voiceURI || eslVoiceChoice;
  if (selected && !voice.voices().some(v=>v.voiceURI===selected) && opts.voiceURI) return false;
  document.querySelectorAll("audio").forEach(a=>a.pause());
  return voice.start(text,{...opts,voiceURI:voice.voices().some(v=>v.voiceURI===selected)?selected:""});
}
function ESLVoicePicker() {
  const [available,setVoices]=(0,h.useState)(()=>eslVoice()?.voices()||[]);
  const [selected,setSelected]=(0,h.useState)(()=>eslVoiceChoice);
  (0,h.useEffect)(()=>{
    const voice=eslVoice();
    if(!voice)return;
    return voice.subscribe(()=>setVoices(voice.voices()));
  },[]);
  return (0,Z.jsxs)("label",{children:["On-device US English voice ",(0,Z.jsxs)("select",{
    value:available.some(v=>v.voiceURI===selected)?selected:"",
    "aria-label":"On-device US English voice",
    onChange:e=>{eslVoiceChoice=e.currentTarget.value;setSelected(eslVoiceChoice)},
    children:[(0,Z.jsx)("option",{value:"",children:available.length?"Recommended installed voice":"No eligible on-device voice detected"}),...available.map(v=>(0,Z.jsx)("option",{value:v.voiceURI,children:v.name},v.voiceURI))]
  })]});
}
function AcUsSpeech({text,element="p",role,blockClass="",rate=.87,showPicker=false,buttonLabel="",onUnavailable=""}) {
  const [status,set]=(0,h.useState)("idle"),[word,W]=(0,h.useState)(""),ref=(0,h.useRef)(null),mounted=(0,h.useRef)(false),generation=(0,h.useRef)(0),owns=(0,h.useRef)(false);
  (0,h.useEffect)(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;if(owns.current)eslVoice()?.abort()}},[]);
  (0,h.useEffect)(()=>{
    if(text)return;
    const cb=()=>{
      const selection=window.getSelection(), selected=selection?.toString().trim();
      if(selected&&selected.length<=500&&ref.current?.closest(".ac-lesson-page,.ac-site")?.contains(selection.anchorNode))W(selected);
    };
    document.addEventListener("selectionchange",cb);
    return()=>document.removeEventListener("selectionchange",cb);
  },[text]);
  function play(){
    if(!(text||word))return;
    const id=++generation.current;
    const finish=label=>{if(mounted.current&&id===generation.current){owns.current=false;set(label)}};
    owns.current=true;set("starting");
    const requested=eslStartVoice(text||word,{rate,onStart:()=>{if(mounted.current&&id===generation.current){owns.current=true;set("playing")}},onEnd:()=>finish("idle"),onAbort:()=>finish("idle"),onError:()=>finish("error")});
    if(!requested){owns.current=false;set("unavailable")}
  }
  function pause(){
    if(!owns.current)return;
    if(status==="paused"){if(eslVoice()?.resume()!==false)set("playing")}
    else if(status==="playing"){if(eslVoice()?.pause()!==false)set("paused")}
  }
  function abort(){if(owns.current)eslVoice()?.abort();owns.current=false;generation.current++;set("idle")}
  const controls=(0,Z.jsxs)("span",{ref,className:"ac-us-controls",children:[
    (0,Z.jsx)("button",{type:"button",className:"ac-us-play",onMouseDown:e=>{if(!text)e.preventDefault()},onClick:play,disabled:!(text||word),
      "aria-label":role||(text?"Hear this text with an on-device US English voice":"Hear selected text with an on-device US English voice"),
      children:buttonLabel||(text?"🔊 US":"🔊 Play selection")}),
    (0,Z.jsx)("button",{type:"button",className:"ac-us-pause",onClick:pause,hidden:status!=="playing"&&status!=="paused",children:status==="paused"?"Resume":"Pause"}),
    (0,Z.jsx)("button",{type:"button",className:"ac-us-stop",onClick:abort,disabled:!["starting","playing","paused"].includes(status),children:"Stop"}),
    status==="unavailable"||status==="error"?(0,Z.jsx)("span",{role:"status",className:"ac-us-status",children:status==="error"?"The device voice stopped. Try another installed voice.":onUnavailable||"No on-device US English voice is available. You can still read the text."}):null
  ]});
  if(text) return (0,Z.jsxs)(element,{className:blockClass,children:[showPicker&&(0,Z.jsx)(ESLVoicePicker,{}),buttonLabel?null:text," ",controls]});
  return (0,Z.jsxs)("div",{className:"ac-us-selection",children:[(0,Z.jsx)("strong",{children:"Optional on-device US English pronunciation"}),(0,Z.jsx)(ESLVoicePicker,{}),(0,Z.jsx)("p",{children:"Use the US button by a paragraph or key term, or select a short phrase and choose Play selection."}),controls]});
}
if(typeof document!=="undefined")document.addEventListener("play",e=>{if(e.target?.tagName==="AUDIO")eslVoice()?.abort()},true);
