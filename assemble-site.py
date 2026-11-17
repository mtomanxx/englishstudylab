#!/usr/bin/env python3
"""Restore a complete Pages artifact; verify every file before publication."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ALLOWED_ORIGIN = "https://mtomanxx.github.io"
ALLOWED_SITE_PATH = "/englishstudylab/"
SOURCE_BASE = ALLOWED_ORIGIN + ALLOWED_SITE_PATH.rstrip("/")


def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "?" in value or "#" in value or path.as_posix() != value:
        raise ValueError(f"Unsafe artifact path: {value!r}")
    return path


def verified_bytes(data, spec):
    if len(data) != spec["size"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError(f"Size/hash mismatch: {spec.get('path', spec.get('filename'))}")
    return data


def write_verified(output, data, spec):
    target = output / safe_path(spec["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(verified_bytes(data, spec))


def apply_textbook_overlay(root, output):
    """Layer readable, versioned presentation files onto the verified course."""
    entry = output / "index.html"
    template = entry.read_text(encoding="utf-8")
    marker = "  </head>"
    if template.count(marker) != 1 or 'id="root"' not in template:
        raise ValueError("Unexpected entry point for the textbook overlay")
    tags = []
    for name, element in (
        ("textbook.css", '<link rel="stylesheet" href="{path}">'),
        ("textbook.js", '<script defer src="{path}"></script>'),
    ):
        artifact = output / "assets" / name
        if artifact.exists():
            raise ValueError(f"Textbook asset already exists: {name}")
        data = (root / "book-overlay" / name).read_bytes()
        version = hashlib.sha256(data).hexdigest()[:12]
        artifact.write_bytes(data)
        tags.append("    " + element.format(path=f"assets/{name}?v={version}"))
    membership = output / "membership"
    membership.mkdir(exist_ok=False)
    for name in ("index.html", "membership.css", "membership.js", "config.js", "enabled.js"):
        (membership / name).write_bytes((root / "book-overlay" / "membership" / name).read_bytes())
    practice = output / "practice"
    practice.mkdir(exist_ok=False)
    for name in ("index.html", "practice.css", "practice.js", "exams.json"):
        (practice / name).write_bytes((root / "book-overlay" / "practice" / name).read_bytes())
    flag_hash = hashlib.sha256((membership / "enabled.js").read_bytes()).hexdigest()[:12]
    tags.insert(0, f'    <script defer src="membership/enabled.js?v={flag_hash}"></script>')
    entry.write_text(template.replace(marker, "\n".join(tags) + "\n" + marker), encoding="utf-8")


def apply_course_overlay(root, output):
    marker = root / "course-overlay.json"
    if not marker.exists():
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data["archive"]["filename"] != "course-overlay.tar.gz":
        raise ValueError("Invalid course overlay specification")
    expected = {}
    permitted_replacements = {"assets/index-af0557abe4eb.js", "assets/index-DGCIrGSb.css", "index.html"}
    for spec in data["files"]:
        path = spec["path"]
        safe_path(path)
        if path in expected or not (path in permitted_replacements or path == "course-library-release.json" or path.startswith("course-audio/") and path.endswith(".mp3") and len(path.split("/")) == 2):
            raise ValueError(f"Unexpected course overlay output: {path}")
        before = output / path
        if path in permitted_replacements:
            baseline = spec["previous"]
            verified_bytes(before.read_bytes(), baseline)
        elif before.exists():
            raise ValueError(f"Course overlay would overwrite an existing file: {path}")
        expected[path] = spec
    verified_bytes((root / data["archive"]["filename"]).read_bytes(), data["archive"])
    seen = set()
    with tarfile.open(root / data["archive"]["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if spec is None or member.name in seen or not member.isfile() or member.size != spec["size"]:
                raise ValueError(f"Unexpected course overlay archive member: {member.name}")
            write_verified(output, archive.extractfile(member).read(spec["size"] + 1), spec)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Course overlay archive did not contain all declared files")
    print(f"Verified native course overlay: {len(seen)} files", flush=True)


def apply_phrasal_overlay(root, output):
    marker = root / "phrasal-overlay.json"
    if not marker.exists():
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data["archive"]["filename"] != "phrasal-overlay.tar.gz":
        raise ValueError("Invalid phrasal-verb overlay specification")
    expected = {}
    exact = {"index.html", "assets/esl-phrasal-discover.js", "assets/esl-phrasal-discover.css",
             "phrasal-verbs/index.html", "phrasal-verbs/reader.css", "phrasal-verbs/reader.js",
             "phrasal-verbs/entries.js", "phrasal-verbs/release.json"}
    for spec in data["files"]:
        path = spec["path"]
        safe_path(path)
        audio = path.startswith("phrasal-verbs/audio/") and len(path.split("/")) == 3 and path.endswith(("-term.mp3", "-example.mp3"))
        if path in expected or (path not in exact and not audio):
            raise ValueError(f"Unexpected phrasal output: {path}")
        before = output / path
        if path == "index.html":
            verified_bytes(before.read_bytes(), spec["previous"])
        elif before.exists():
            raise ValueError(f"Phrasal overlay would overwrite an existing file: {path}")
        expected[path] = spec
    verified_bytes((root / data["archive"]["filename"]).read_bytes(), data["archive"])
    seen = set()
    with tarfile.open(root / data["archive"]["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if spec is None or member.name in seen or not member.isfile() or member.size != spec["size"]:
                raise ValueError(f"Unexpected phrasal overlay archive member: {member.name}")
            write_verified(output, archive.extractfile(member).read(spec["size"] + 1), spec)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Phrasal overlay archive did not contain all declared files")
    print(f"Verified phrasal overlay: {len(seen)} files", flush=True)


def apply_golden_exam_overlay(root, output):
    marker = root / "golden-exam-overlay.json"
    if not marker.exists():
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data["archive"]["filename"] != "golden-exam-overlay.tar.gz":
        raise ValueError("Invalid golden exam overlay specification")
    exact = {"index.html", "practice/index.html", "practice/practice.js",
             "phrasal-verbs/index.html", "membership/index.html",
             "assets/index-af0557abe4eb.js", "assets/esl-golden-theme.css",
             "practice/release.json"}
    replacements = exact - {"assets/esl-golden-theme.css", "practice/release.json"}
    expected = {}
    for spec in data["files"]:
        path = spec["path"]
        safe_path(path)
        if path not in exact or path in expected:
            raise ValueError(f"Unexpected golden exam output: {path}")
        before = output / path
        if path in replacements:
            verified_bytes(before.read_bytes(), spec["previous"])
        elif before.exists():
            raise ValueError(f"Golden exam overlay would overwrite an existing file: {path}")
        expected[path] = spec
    if set(expected) != exact:
        raise ValueError("Golden exam overlay file set mismatch")
    verified_bytes((root / data["archive"]["filename"]).read_bytes(), data["archive"])
    seen = set()
    with tarfile.open(root / data["archive"]["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if spec is None or member.name in seen or not member.isfile() or member.size != spec["size"]:
                raise ValueError(f"Unexpected golden exam archive member: {member.name}")
            write_verified(output, archive.extractfile(member).read(spec["size"] + 1), spec)
            seen.add(member.name)
    if seen != exact:
        raise ValueError("Golden exam overlay archive did not contain all declared files")
    print(f"Verified golden exam workbook overlay: {len(seen)} files", flush=True)



def apply_globalistihdam_palette(root, output):
    """Add brand colors to public study surfaces, not member account pages."""
    data = (root / "book-overlay" / "globalistihdam-palette.css").read_bytes()
    asset = output / "assets" / "esl-globalistihdam-palette.css"
    if asset.exists():
        raise ValueError("Unexpected Globalistihdam palette output collision")
    asset.write_bytes(data)
    version = hashlib.sha256(data).hexdigest()[:12]
    for path, prefix in (("index.html", ""), ("practice/index.html", "../"),
                         ("phrasal-verbs/index.html", "../")):
        page = output / path
        markup = page.read_bytes()
        if markup.count(b"</head>") != 1 or b"esl-golden-theme.css" not in markup:
            raise ValueError(f"Unexpected palette stylesheet entry point: {path}")
        tag = f'<link rel="stylesheet" href="{prefix}assets/esl-globalistihdam-palette.css?v={version}">'
        page.write_bytes(markup.replace(b"</head>", tag.encode("ascii") + b"\n</head>"))


def apply_human_reading_shelf(root, output):
    """Add the reviewed human-authored reading and human narration resource shelf."""
    import re

    shelf = (root / "book-overlay" / "human-reading" / "index.html").read_bytes()
    if hashlib.sha256(shelf).hexdigest() != "b0fae392c74243833d1e599a45bb5784a7b1a6cc96cece6b2a08319270a7991f":
        raise ValueError("Reviewed human-reading shelf changed")
    route = output / "human-reading"
    route.mkdir()
    marker = b'<label for="type">'
    if shelf.count(marker) != 1:
        raise ValueError("Unexpected shelf link anchor")
    link = b'<p><a href="voice/">Compare a human recording with optional on-device AI narration</a></p>'
    (route / "index.html").write_bytes(shelf.replace(marker, link + marker))
    voice = (root / "book-overlay" / "human-reading" / "voice" / "index.html").read_bytes()
    if hashlib.sha256(voice).hexdigest() != "9e152eb8c325b3062d604a864cd82299edf5cb906433e12140c693fde1af00ee":
        raise ValueError("Reviewed voice comparison changed")
    comparison = route / "voice"
    comparison.mkdir()
    (comparison / "index.html").write_bytes(voice)
    for name, prefix in (("index.html", ""), ("practice/index.html", "../"), ("phrasal-verbs/index.html", "../")):
        page = output / name
        html = page.read_bytes()
        notice = (
            '<aside aria-label="Human reading and listening" '
            'style="background:#e6eddf;color:#102e31;margin:0;padding:.65rem max(1rem,calc((100% - 68rem)/2));font:600 1rem/1.45 system-ui,sans-serif">'
            f'<a style="color:#102e31;text-decoration:underline;text-underline-offset:.2em" href="{prefix}human-reading/">'
            'Read and listen with human voices</a></aside>'
        ).encode("utf-8")
        markup, count = re.subn(rb"(<body(?:\s[^>]*)?>)", lambda m: m[1] + notice, html, flags=re.I)
        if count != 1:
            raise ValueError(f"Unexpected human-reading entry point: {name}")
        page.write_bytes(markup)


def apply_local_narration(root, base):
    """Add optional local US AI narration without replacing existing recordings."""
    import re
    from hashlib import sha256

    overlay=root/"book-overlay"/"narration"
    (base/"assets"/"esl-local-voice.js").write_bytes((overlay/"esl-local-voice.js").read_bytes())
    def patch_native():
        bundle=(base/'assets/index-af0557abe4eb.js').read_bytes()
        assert sha256(bundle).hexdigest()=='253ff1fc8bbe5eab5fda63943ee72c00ccbfd2a2ab4659ad9d6f562314cc7ce9'
        text=bundle.decode()
        def replace(old,new,expected=1):
         nonlocal text
         c=text.count(old)
         assert c==expected,(old[:110],c)
         text=text.replace(old,new)
        def splice(start,end,code):
         nonlocal text
         assert text.count(start)==1 and text.count(end)==1,(start,end)
         left,right=text.index(start),text.index(end)
         assert left<right
         text=text[:left]+code+text[right:]

        splice('function acSpeechEngine(){','function pr({lesson:',(overlay/'native-bridge.js').read_text()+'\n')
        splice('function _(){if(tn(),!window.speechSynthesis)','let v=e=>e.normalize(`NFKC`)','''function _(){tn();const text=t?.realisations?.[e.id]||Kt(e.term);if(!eslStartVoice(text,{rate:.87,onError:()=>m(`The on-device voice did not play. The lesson MP3 remains available.`)}))m(`No on-device US English voice. You can use the complete lesson MP3 below.`)}''')
        replace('(0,Z.jsxs)(`button`,{className:`vl-text-button`,onClick:_,','(0,Z.jsx)(ESLVoicePicker,{}),(0,Z.jsxs)(`button`,{className:`vl-text-button`,onClick:_,')
        replace('t&&(0,Z.jsxs)(`details`,{className:`vl-full-passage`','t?.text&&(0,Z.jsx)(AcUsSpeech,{text:t.text,element:`div`,rate:a,buttonLabel:`Read full passage with device voice`,onUnavailable:`No on-device US voice is available. Use the lesson MP3 or full passage below.`}),t&&(0,Z.jsxs)(`details`,{className:`vl-full-passage`')
        splice('function readPassageOnDevice(text)','function pauseNarration()', 'function readPassageOnDevice(text){\n const token={mode:`device`};z.current=token;\n const clear=msg=>{if(z.current===token){finishReading();if(msg)I(msg)}};\n const started=eslStartVoice(text,{voiceURI:O||void 0,rate:x,onEnd:()=>clear(),onAbort:()=>clear(),onError:()=>clear(`The selected device voice could not play. The lesson MP3 remains available.`)});\n if(!started){finishReading();return false}\n M(!0);P(!1);return true\n}\nfunction _e(text){ge();I(``);\n if(readPassageOnDevice(text))return;\n const player=re.current;\n if(player){const token={mode:`recording`,audio:player};z.current=token;M(!0);P(!1);\n  if(`preservesPitch` in player)player.preservesPitch=!0;\n  player.playbackRate=x;try{player.currentTime=0}catch{}\n  I(`On-device US narration is unavailable. Playing the existing lesson recording.`);\n  const failure=()=>{if(z.current===token){finishReading();I(`The lesson recording could not play. You can still use the written passage.`)}};\n  try{Promise.resolve(player.play()).catch(failure)}catch{failure()}return\n }\n I(`No on-device US English voice is available. You can still read the passage.`)\n}\n')
        replace('else if(N)window.speechSynthesis.resume();else window.speechSynthesis.pause();','else if(N)eslVoice()?.resume();else eslVoice()?.pause();')
        replace('window.speechSynthesis?.cancel();document.querySelectorAll(`audio`).forEach(e=>e.pause());if(active?.mode','eslVoice()?.abort();document.querySelectorAll(`audio`).forEach(e=>e.pause());if(active?.mode')
        replace('window.speechSynthesis?.cancel();if(!primary)finishReading();','eslVoice()?.abort();if(!primary)finishReading();')
        replace('if(window.speechSynthesis){let t=()=>D(window.speechSynthesis.getVoices().filter(e=>e.lang.startsWith(`en`)));return t(),window.speechSynthesis.addEventListener(`voiceschanged`,t),()=>{e=!0,window.speechSynthesis.cancel(),window.speechSynthesis.removeEventListener(`voiceschanged`,t)}}','if(eslVoice()){const v=eslVoice();const update=()=>D(v.voices());update();const off=v.subscribe(update);return()=>{e=!0;v.abort();off?.()}}')
        replace('value:``,children:`Clear female lesson recording (recommended)`','value:``,children:`Recommended installed US voice`')
        replace('E.map(e=>(0,Z.jsxs)(`option`,{value:e.name,children:[e.name,` (`,e.lang,`)`]},e.name))','E.map(e=>(0,Z.jsxs)(`option`,{value:e.voiceURI,children:[e.name,` (`,e.lang,`)`]},e.voiceURI))')
        replace('The default uses the lesson’s female British English recording at a comfortable pace. Pick a device voice for a different accent. Restart to apply a voice or speed change.','Choose an installed US English device voice. If none is available, the full passage uses the existing lesson recording where one is available. Restart to apply a voice or speed change.')
        splice('function bn(e,t=.85)','var xn=', 'function bn(e,t=.85){return eslStartVoice(e,{rate:t})}')
        replace('A recognised female English device voice is unavailable. Use the female-voice downloadable lesson recording.','No on-device US English voice is available. Use the downloadable lesson recording where offered.')
        replace('className:`ac-audio-actions`,children:[','className:`ac-audio-actions`,children:[(0,Z.jsx)(AcUsSpeech,{text:e.audio.transcript,element:`div`,rate:m,showPicker:!0,buttonLabel:`Read transcript with device voice`,onUnavailable:`No on-device US voice is available. Use the existing recording or the transcript.`}),')
        assert 'speechSynthesis.speak(' not in text
        assert 'engine.speak(' not in text
        (base/'assets/index-af0557abe4eb.js').write_text(text, encoding='utf-8')
        html=(base/'index.html').read_text()
        old='    <script type="module" crossorigin src='
        assert html.count(old)==1
        html=html.replace(old,'    <script src="assets/esl-local-voice.js"></script>\n'+old)
        html=html.replace('practice=253ff1fc8bbe','practice=253ff1fc8bbe&amp;voice='+sha256(text.encode()).hexdigest()[:12])
        (base/'index.html').write_text(html, encoding='utf-8')

    patch_native()

    def digest(b):return sha256(b).hexdigest()
    def swap(t,a,b):
     assert t.count(a)==1,(a[:90],t.count(a))
     return t.replace(a,b,1)
    helper=(overlay/'esl-local-voice.js').read_bytes()
    prefix=f'<script defer src="../assets/esl-local-voice.js?v={digest(helper)[:12]}"></script>'
    def write(path,content):
     (base/path).write_text(content,encoding="utf-8")
    phtml=(base/'phrasal-verbs/index.html').read_text()
    reader=(base/'phrasal-verbs/reader.js').read_text()
    reader=swap(reader, "  const voice = new Audio();","  const local = window.ESLLocalVoice;\n  const voice = new Audio();")
    reader=swap(reader,"let speaker=null,token=0, speech=null;","let speaker=null,token=0, mode=null;")
    reader=swap(reader,"    $('stop').disabled=true;","    $('stop').disabled=true;\n    $('pause-audio').disabled=true;\n    $('pause-audio').textContent='Pause audio';\n    mode=null;")
    reader=swap(reader,"    if(speech){window.speechSynthesis?.cancel();speech=null;}","    local?.abort();")
    start=reader.index('  function fallback(');end=reader.index("  $('stop').onclick",start)
    reader=reader[:start]+"  function play(btn,row,kind){\n    if(btn===speaker){stop('Audio stopped.');return;}\n    stop();\n    const id=token,label=kind==='term'?row.verb:'example for '+row.verb;\n    const text=kind==='term'?'to '+row.verb:row.example;\n    mode=$('voice-mode').value==='mp3'?'mp3':'device';\n    const rate=Number($('voice-rate').value);\n    speaker=btn;btn.setAttribute('aria-pressed','true');$('stop').disabled=false;\n    $('pause-audio').disabled=false;\n    if(mode==='device'){\n      $('audio-status').textContent='Starting your device voice…';\n      const missing='No matching US English voice is installed on this device. Choose Existing AI MP3 or read the example.';\n      if(!local){finish(missing);return;}\n      local.start(text,{rate,onStart:voice=>{if(id===token)$('audio-status').textContent='Playing '+label+' · '+voice.name+' (US English).';},\n       onEnd:()=>{if(id===token)finish('Finished '+label+'.');},\n       onAbort:()=>{if(id===token)finish('Audio stopped.');},\n       onError:error=>{if(id===token)finish(error==='unavailable'?missing:'Your device voice could not play.');}});\n      return;\n    }\n    $('audio-status').textContent='Playing the existing AI recording for '+label+'.';\n    voice.src=new URL('audio/'+row.id+'-'+kind+'.mp3',document.baseURI).href;\n    voice.playbackRate=rate;\n    voice.onended=()=>{if(id===token)finish('Finished '+label+'.');};\n    const fail=()=>{if(id===token)finish('The existing recording could not load. You can still read the text.');};\n    try{Promise.resolve(voice.play()).catch(fail);}catch(e){fail();}\n  }\n  $('pause-audio').onclick=()=>{\n    if(!mode)return;\n    const b=$('pause-audio'),resume=b.textContent==='Resume audio';\n    let ok=false;\n    if(mode==='device')ok=resume?local?.resume():local?.pause();\n    else if(resume){try{Promise.resolve(voice.play()).catch(()=>finish('Playback could not resume.'));ok=true;}catch(e){}}\n    else{voice.pause();ok=true;}\n    if(ok){b.textContent=resume?'Pause audio':'Resume audio';$('audio-status').textContent=resume?'Playback resumed.':'Playback paused.';}\n  };\n  $('voice-mode').addEventListener('change',()=>{if(speaker)stop('Audio stopped. Select a term or example to play the newly chosen voice.');});\n" + reader[end:]
    phtml=swap(phtml,'<script defer src="reader.js"></script>',prefix+f'\n<script defer src="reader.js?v={digest(reader.encode())[:12]}"></script>')
    phtml=swap(phtml,'<p>US English audio · synthetic, no sign-in required. Verb audio starts with “to.”</p><button id="stop"','<p>AI narration · US English, on this device by default. Verb audio starts with “to.”</p><label>Voice source <select id="voice-mode"><option value="device">Best available on-device US voice</option><option value="mp3">Existing AI MP3</option></select></label><label>Speed <select id="voice-rate"><option value=".72">0.72×</option><option selected value=".87">0.87×</option><option value="1">1×</option><option value="1.15">1.15×</option></select></label><button id="pause-audio" type="button" disabled>Pause audio</button><button id="stop"')
    phtml=swap(phtml,'US English audio is synthetic narration generated locally with the CMU Flite SLT voice. The written example remains available if audio cannot play.','On-device narration needs an installed US English voice. Existing recordings are synthetic US English made with CMU Flite SLT and play only if selected. The written example is always available.')
    write('phrasal-verbs/reader.js',reader);write('phrasal-verbs/index.html',phtml)
    det=(base/'practice/practice.js').read_text()
    from_source='''    if ("speechSynthesis" in window && typeof window.SpeechSynthesisUtterance === "function") synth = window.speechSynthesis;'''
    det=swap(det,from_source,"    synth = window.ESLLocalVoice;")
    det=swap(det,"    if (synth) synth.cancel();","    synth?.abort();")
    start=det.index('    const play = btn("Play audio"');end=det.index('\n  function timerPanel()',start)
    det=det[:start]+'    const rate=node("select",{"aria-label":"AI narration speed"},\n      ...[[".72","0.72×"],[".87","0.87×"],["1","1×"],["1.15","1.15×"]].map(([value,text])=>node("option",{value,text})));\n    rate.value=".87";\n    status.textContent="AI narration uses an installed US English voice. Show the transcript or open the existing recording if needed.";\n    function finish(message){status.textContent=message;pause.disabled=true;stop.disabled=true;pause.textContent="Pause audio";}\n    const play = btn("Play local AI narration",()=>{\n      if(!synth){finish("The local voice engine is unavailable. Use the transcript or existing recording.");return;}\n      const ok=synth.start(exam.listening.transcript,{rate:Number(rate.value),\n       onStart:voice=>{status.textContent=voice.name+" · on-device US AI narration.";},\n       onEnd:()=>finish("Playback finished."),onAbort:()=>finish("Playback stopped."),\n       onError:reason=>finish(reason==="unavailable"?"No supported US English voice is installed. Use the transcript or existing recording.":"Playback failed. Use the transcript or existing recording.")});\n      if(ok){pause.disabled=false;stop.disabled=false;pause.textContent="Pause audio";status.textContent="Starting your device voice…";}\n    });\n    const pause=btn("Pause audio",()=>{const resume=pause.textContent==="Resume audio";const ok=resume?synth?.resume():synth?.pause();if(ok){pause.textContent=resume?"Pause audio":"Resume audio";status.textContent=resume?"Playback resumed.":"Playback paused.";}}, "btn secondary");\n    const stop=btn("Stop audio",()=>{synth?.abort();finish("Playback stopped.");},"btn secondary");\n    pause.disabled=stop.disabled=true;\n    const existing=node("a",{class:"btn secondary",href:"../exam-audio/det-workbook-"+String(exam.id).padStart(2,"0")+"-audio.mp3",target:"_blank",rel:"noopener noreferrer",text:"Open existing AI MP3 (new tab)"});\n    panel.append(node("div", { class: "actions" }, play,pause,stop,rate,reveal,existing), status, transcript);\n  }' + det[end:]
    dh=(base/'practice/index.html').read_text()
    matches=re.findall(r'<script defer src="\./practice\.js(?:\?[^"]*)?"></script>',dh)
    assert len(matches)==1,matches
    dh=swap(dh,matches[0],prefix+f'\n  <script defer src="./practice.js?v={digest(det.encode())[:12]}"></script>')
    write('practice/practice.js',det);write('practice/index.html',dh)
    a=json.loads((base/'practice/exams.json').read_text());b=json.loads((base/'exam-forms.json').read_text())
    for x in a:
     f=next(k for k in b if k['id']==f'det-workbook-{x["id"]:02}')
     audio=[z for y in f['sections'] for z in y.get('stimuli',[]) if z.get('audio')]
     assert len(audio)==1 and audio[0]['text']==x['listening']['transcript']
     expected=f'exam-audio/det-workbook-{x["id"]:02}-audio.mp3'
     assert audio[0]['audio'].endswith(expected) and (base/expected).exists()

    for path, wanted in {'assets/esl-local-voice.js': '72e6b7b03bb29037eb710dcc6f517b4f78dcbf74d475906370519480669d397c', 'assets/index-af0557abe4eb.js': 'b07bfffd2cdc3c03dfe4bf6aed1cbbfa53f7897e16fab1e7b8a57b54df14dd31', 'index.html': '780175d57dea7d6952c539998211e7a6fcbe1ae7eb921d63418391c8517191cf', 'phrasal-verbs/index.html': '1a51dd542a1d0a1ddfc3473e94164faa485072df19ce4cd642a71f6878b616b6', 'phrasal-verbs/reader.js': '88788f2408f40d3e2d2d8bf17463a5ed3eb8cab98dd29ed4e0badee8eb1bb7c5', 'practice/index.html': 'dd25722a74eb3247cb03eef86485a61a7ea89a409da17fe03023aecb77817212', 'practice/practice.js': '427884a9ef5ea4d534e7dd7f87936a33cde61d2ff123ded101dda175220447e9'}.items():
        if sha256((base/path).read_bytes()).hexdigest()!=wanted:
            raise ValueError("Narration output changed: "+path)
    print("Verified optional local narration on three entry surfaces",flush=True)



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--local-assets", type=Path, help="Offline validation only; workflow always downloads public files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "asset-manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != 1 or manifest["source_base"] != SOURCE_BASE:
        raise ValueError("Unexpected package format or source origin")
    expected = {}
    for spec in manifest["files"]:
        safe_path(spec["path"])
        if spec["path"] in expected or spec["source"] not in {"core", "public"} or not isinstance(spec["size"], int) or spec["size"] < 0:
            raise ValueError("Invalid or duplicate file specification")
        if len(spec["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in spec["sha256"]):
            raise ValueError("Invalid SHA256")
        expected[spec["path"]] = spec
    if len(expected) != manifest["summary"]["file_count"] or "index.html" not in expected:
        raise ValueError("Manifest file count/entry mismatch")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Output must be empty; refusing to overwrite existing files")
    core = manifest["core"]
    if core["filename"] != "site-core.tar.gz":
        raise ValueError("Unexpected core archive filename")
    verified_bytes((root / core["filename"]).read_bytes(), core)
    extracted = set()
    with tarfile.open(root / core["filename"], mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            spec = expected.get(member.name)
            if not member.isfile() or spec is None or spec["source"] != "core" or member.name in extracted or member.size != spec["size"]:
                raise ValueError(f"Unexpected archive member: {member.name}")
            fileobj = archive.extractfile(member)
            write_verified(output, fileobj.read(spec["size"] + 1), spec)
            extracted.add(member.name)
    if extracted != {path for path, spec in expected.items() if spec["source"] == "core"}:
        raise ValueError("Core archive file list mismatch")

    def fetch_file(spec):
        if args.local_assets:
            data = (args.local_assets / spec["path"]).read_bytes()
        else:
            url = SOURCE_BASE + "/" + quote(spec["path"], safe="/")
            for attempt in range(3):
                try:
                    request = Request(url, headers={"User-Agent": "EnglishStudyLab-GitHubPages-Migration/1.0", "Accept-Encoding": "identity"})
                    with urlopen(request, timeout=60) as response:
                        final = urlparse(response.geturl())
                        if response.status != 200 or f"{final.scheme}://{final.netloc}" != ALLOWED_ORIGIN or not final.path.startswith(ALLOWED_SITE_PATH):
                            raise ValueError(f"Unexpected HTTP response for {spec['path']}")
                        length = response.headers.get("Content-Length")
                        if length is not None and int(length) != spec["size"]:
                            raise ValueError(f"Unexpected response size for {spec['path']}")
                        data = response.read(spec["size"] + 1)
                    break
                except HTTPError as error:
                    if error.code < 500 or attempt == 2:
                        raise RuntimeError(f"Asset request failed: {spec['path']} (HTTP {error.code})") from None
                    time.sleep(attempt + 1)
                except (URLError, TimeoutError):
                    if attempt == 2:
                        raise RuntimeError(f"Asset request timed out: {spec['path']}") from None
                    time.sleep(attempt + 1)
        write_verified(output, data, spec)
        return spec["path"]

    downloads = [spec for spec in expected.values() if spec["source"] == "public"]
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_file, spec) for spec in downloads]
        try:
            for done, future in enumerate(as_completed(futures), 1):
                future.result()
                if done % 50 == 0 or done == len(downloads):
                    print(f"Verified public assets: {done}/{len(downloads)}", flush=True)
        except Exception:
            for future in futures:
                future.cancel()
            raise
    actual = {file.relative_to(output).as_posix() for file in output.rglob("*") if file.is_file()}
    if actual != set(expected):
        raise ValueError("Final artifact file list mismatch")
    for path, spec in expected.items():
        verified_bytes((output / path).read_bytes(), spec)
    total = sum(spec["size"] for spec in expected.values())
    audio_count = sum(path.endswith(".mp3") for path in expected)
    if total != manifest["summary"]["total_bytes"] or audio_count != manifest["summary"]["mp3_count"]:
        raise ValueError("Final artifact summary mismatch")
    print(f"Complete artifact verified: {len(actual)} files, {audio_count} MP3s, {total} bytes", flush=True)
    apply_textbook_overlay(root, output)
    print("Textbook overlay added; verified content and media are unchanged", flush=True)
    apply_course_overlay(root, output)
    apply_phrasal_overlay(root, output)
    apply_golden_exam_overlay(root, output)
    apply_globalistihdam_palette(root, output)
    apply_human_reading_shelf(root, output)
    apply_local_narration(root, output)


if __name__ == "__main__":
    main()
