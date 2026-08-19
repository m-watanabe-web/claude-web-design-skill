#!/usr/bin/env python3
"""実レンダリング検査（Chrome headless）。静的解析では追えない項目を、実際に描画して測る。

  python3 contrast.py <file.html> [...]

検査項目
  - コントラスト比（WCAG 2.2 AA）を **明モードとダークモードの両方**で
  - 横溢れ（1280px / 380px）
  - タップ領域（WCAG 2.2 SC 2.5.8 = 24x24 が AA、SC 2.5.5 = 44x44 は AAA）

違反があれば終了コード 1（CI用）。
Chrome の場所は環境変数 CHROME_PATH で上書きできる。
"""
import sys, os, json, re, html, pathlib, subprocess, tempfile, shutil

def find_chrome():
    if os.environ.get('CHROME_PATH'): return os.environ['CHROME_PATH']
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(mac): return mac
    for n in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
        p = shutil.which(n)
        if p: return p
    return None

JS = r"""
function lin(c){c/=255;return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4)}
function lum(o){return .2126*lin(o.r)+.7152*lin(o.g)+.0722*lin(o.b)}
function parse(s){if(!s)return null;
 let m=s.match(/^color\(srgb\s+([^)]+)\)/);   // Chrome は color-mix() を color(srgb ...) で返す
 if(m){const p=m[1].split(/[\s\/]+/).filter(Boolean).map(Number);
   return{r:p[0]*255,g:p[1]*255,b:p[2]*255,a:p.length>3?p[3]:1}}
 m=s.match(/rgba?\(([^)]+)\)/); if(!m)return null;
 const p=m[1].split(/[,\s\/]+/).filter(Boolean).map(Number);
 return{r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}}
function effBg(el,win){let st=[],n=el;
 while(n&&n.nodeType===1){const c=parse(win.getComputedStyle(n).backgroundColor);
  if(c&&c.a>0){st.push(c);if(c.a>=1)break}n=n.parentElement}
 let b={r:255,g:255,b:255};
 for(let i=st.length-1;i>=0;i--){const c=st[i];
  b={r:c.r*c.a+b.r*(1-c.a),g:c.g*c.a+b.g*(1-c.a),b:c.b*c.a+b.b*(1-c.a)}}return b}

// prefers-color-scheme はヘッドレスから切り替えられないため、
// 該当する @media ブロックの中身を素のルールとして流し込んで再現する。
function freeze(doc){ // transition/animation を止める。
 // これが無いと、テーマ切替時に色が遷移し切る前に測ってしまい偽陽性が出る（実測で確認済み）。
 const s=doc.createElement('style');
 s.textContent='*,*::before,*::after{transition:none!important;animation:none!important}';
 doc.head.appendChild(s)}
function applyScheme(doc,scheme){
 let css='';
 for(const sh of Array.from(doc.styleSheets)){
  let rules; try{rules=sh.cssRules}catch(e){continue}
  for(const r of Array.from(rules||[])){
   if(r.type===4 && /prefers-color-scheme/.test(r.conditionText||'')){
    const isDark=/dark/.test(r.conditionText);
    if((scheme==='dark')===isDark) css+=Array.from(r.cssRules).map(x=>x.cssText).join('\n');
   }}}
 if(css){const s=doc.createElement('style');s.textContent=css;doc.head.appendChild(s)}
 return !!css}

function audit(doc,win){const out=[];let n=0,skip=0,worst=99;
 doc.querySelectorAll('*').forEach(el=>{
  const t=[...el.childNodes].filter(x=>x.nodeType===3&&x.textContent.trim())
        .map(x=>x.textContent.trim()).join('');
  if(!t)return;n++;const cs=win.getComputedStyle(el);
  if(cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0)return;
  const fg=parse(cs.color);if(!fg){skip++;return}
  const bg=effBg(el,win);
  const o={r:fg.r*fg.a+bg.r*(1-fg.a),g:fg.g*fg.a+bg.g*(1-fg.a),b:fg.b*fg.a+bg.b*(1-fg.a)};
  const L1=lum(o),L2=lum(bg);
  const ratio=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
  const px=parseFloat(cs.fontSize),bold=+cs.fontWeight>=700;
  const need=(px>=24||(px>=18.66&&bold))?3:4.5;
  if(ratio<worst)worst=Math.round(ratio*100)/100;
  if(ratio<need)out.push({sel:el.tagName.toLowerCase()+(typeof el.className==='string'&&el.className?
    '.'+el.className.trim().split(/\s+/).join('.'):''),
    txt:t.slice(0,18),ratio:Math.round(ratio*100)/100,need,px:Math.round(px)})});
 return{out,checked:n,skip,worst}}

function overflow(doc,win){
 const d=doc.documentElement,sw=d.scrollWidth,cw=d.clientWidth,bad=[];
 if(sw>cw+1){doc.querySelectorAll('*').forEach(e=>{const r=e.getBoundingClientRect();
  if(r.width>cw+1&&e.tagName!=='HTML'&&e.tagName!=='BODY'&&win.getComputedStyle(e).overflowX==='visible')
   bad.push(e.tagName.toLowerCase()+(typeof e.className==='string'&&e.className?
    '.'+e.className.trim().split(/\s+/)[0]:'')+'('+Math.round(r.width)+'px)')})}
 return{vw:cw,scrollWidth:sw,overflow:sw>cw+1,culprits:bad.slice(0,5)}}

function targets(doc,win){
 const sel='a[href],button,input:not([type=hidden]),select,textarea,[role=button],[tabindex]:not([tabindex="-1"])';
 const fail=[],warn=[];
 doc.querySelectorAll(sel).forEach(e=>{
  const cs=win.getComputedStyle(e);
  if(cs.display==='none'||cs.visibility==='hidden')return;
  // SC 2.5.8 の適用除外：文章の中にあるインラインリンク
  // （親タグ名で判定すると footer 直下等を取りこぼすため、
  //   「インライン表示 かつ 親に自分以外の地の文がある」で判定する）
  if(e.tagName==='A'&&cs.display.startsWith('inline')&&!cs.display.includes('flex')){
   const par=e.parentElement;
   if(par){const own=(e.textContent||'').trim();
    const around=(par.textContent||'').replace(own,'').trim();
    if(around.length>0)return;}}
  const r=e.getBoundingClientRect(); if(!r.width&&!r.height)return;
  const w=Math.round(r.width),h=Math.round(r.height);
  const label=e.tagName.toLowerCase()+(typeof e.className==='string'&&e.className?
    '.'+e.className.trim().split(/\s+/)[0]:'')+' '+w+'x'+h;
  if(w<24||h<24)fail.push(label); else if(w<44||h<44)warn.push(label)});
 return{fail:fail.slice(0,6),warn:warn.slice(0,6)}}
"""

def run(paths):
    chrome = find_chrome()
    if not chrome: return None, 'Chrome が見つからない（CHROME_PATH を設定してください）'
    payload = {pathlib.Path(p).name: pathlib.Path(p).read_text(encoding='utf-8') for p in paths}
    doc = ('<!doctype html><meta charset="utf-8"><body style="margin:0"><pre id="out">measuring...</pre>'
           '<script id="data" type="application/json">' + json.dumps(payload, ensure_ascii=False) + '</script>'
           '<script>const DATA=JSON.parse(document.getElementById("data").textContent);' + JS +
           '(async()=>{const res={};'
           'for(const f of Object.keys(DATA)){const r={};'
           'for(const scheme of ["light","dark"]){'
           '  const fr=document.createElement("iframe");'
           '  fr.style.cssText="width:1280px;height:940px;border:0;position:absolute;left:-9999px";'
           '  fr.srcdoc=DATA[f];document.body.appendChild(fr);'
           '  await new Promise(x=>{fr.onload=x});await new Promise(x=>setTimeout(x,120));'
           '  const d=fr.contentDocument,w=fr.contentWindow;'
           '  freeze(d); const had=applyScheme(d,scheme);'
           '  await new Promise(x=>setTimeout(x,80));'
           '  const a=audit(d,w); a.themed=had;'
           '  if(scheme==="light"){a.layout=[overflow(d,w)];a.targets=targets(d,w);'
           '    fr.style.width="380px";await new Promise(x=>setTimeout(x,120));'
           '    a.layout.push(overflow(d,w));}'
           '  r[scheme]=a;fr.remove()}'
           'res[f]=r}'
           'document.getElementById("out").textContent=JSON.stringify(res)})();</script>')
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as fh:
        fh.write(doc); tmp = fh.name
    dom = subprocess.run([chrome, '--headless', '--disable-gpu', '--no-sandbox',
                          '--virtual-time-budget=12000', '--dump-dom', 'file://'+tmp],
                         capture_output=True, text=True).stdout
    pathlib.Path(tmp).unlink(missing_ok=True)
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    if not m: return None, '出力を取得できない'
    raw = html.unescape(m.group(1))
    if raw.strip() == 'measuring...': return None, '測定が完了しない（ファイル数を3〜4件に減らす）'
    return json.loads(raw), None

if __name__ == '__main__':
    res, err = run(sys.argv[1:])
    if err: sys.exit('測定失敗: ' + err)
    bad = 0
    for f, r in res.items():
        light, dark = r['light'], r['dark']
        print(f"\n{f}")
        for name, d in (('明モード', light), ('ダークモード', dark)):
            note = '' if d['themed'] else '（該当メディアブロックなし＝既定スタイルで測定）'
            mark = 'OK' if not d['out'] else f"違反 {len(d['out'])}件"
            print(f"   {name:12} 検査{d['checked']}要素 / {mark} / 最悪 {d['worst']}:1 {note}")
            for x in sorted(d['out'], key=lambda x: x['ratio'])[:5]:
                print(f"      {x['ratio']}:1 (要{x['need']}) {x['px']}px  {x['sel']}  \"{x['txt']}\"")
            if len(d['out']) > 5: print(f"      … 他 {len(d['out'])-5} 件")
            bad += len(d['out'])
        for lay in light.get('layout', []):
            if lay['overflow']:
                print(f"   横溢れ 幅{lay['vw']}px: scrollWidth={lay['scrollWidth']}px {' '.join(lay['culprits'])}")
                bad += 1
        if not any(l['overflow'] for l in light.get('layout', [])):
            print("   横溢れ         なし（1280px / 380px）")
        tg = light.get('targets', {})
        if tg.get('fail'):
            print(f"   タップ領域     24x24未満（AA違反）: {', '.join(tg['fail'])}"); bad += len(tg['fail'])
        elif tg.get('warn'):
            print(f"   タップ領域     24x24は満たすが44x44未満（AAA未達）: {', '.join(tg['warn'])}")
        else:
            print("   タップ領域     OK（44x44以上）")
    print()
    sys.exit(1 if bad else 0)
