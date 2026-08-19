#!/usr/bin/env python3
"""コントラスト実測（Chrome headless）。静的解析では入れ子の背景を追えないため、実レンダリングで測る。
  python3 contrast.py <file.html> [...]
前提: /Applications/Google Chrome.app が存在すること。3〜4ファイルずつが安定。
"""
import sys, json, re, html, pathlib, subprocess, tempfile

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
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
"""

def run(paths):
    payload = {pathlib.Path(p).name: pathlib.Path(p).read_text(encoding='utf-8') for p in paths}
    doc = ('<!doctype html><meta charset="utf-8"><body style="margin:0"><pre id="out">measuring...</pre>'
           '<script id="data" type="application/json">' + json.dumps(payload, ensure_ascii=False) + '</script>'
           '<script>const DATA=JSON.parse(document.getElementById("data").textContent);' + JS +
           '(async()=>{const res={};for(const f of Object.keys(DATA)){'
           'const fr=document.createElement("iframe");'
           'fr.style.cssText="width:1280px;height:900px;border:0;position:absolute;left:-9999px";'
           'fr.srcdoc=DATA[f];document.body.appendChild(fr);'
           'await new Promise(r=>{fr.onload=r});await new Promise(r=>setTimeout(r,150));'
           'res[f]=audit(fr.contentDocument,fr.contentWindow);fr.remove()}'
           'document.getElementById("out").textContent=JSON.stringify(res)})();</script>')
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as fh:
        fh.write(doc); tmp = fh.name
    dom = subprocess.run([CHROME, '--headless', '--disable-gpu', '--no-sandbox',
                          '--virtual-time-budget=8000', '--dump-dom', 'file://'+tmp],
                         capture_output=True, text=True).stdout
    pathlib.Path(tmp).unlink(missing_ok=True)
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    if not m: return None
    raw = html.unescape(m.group(1))
    if raw.strip() == 'measuring...': return None
    return json.loads(raw)

if __name__ == '__main__':
    res = run(sys.argv[1:])
    if res is None:
        sys.exit('測定失敗（Chrome未検出、またはファイル数が多すぎる。3〜4件ずつ試す）')
    for f, r in res.items():
        print(f"\n{f} : 検査 {r['checked']}要素(解析不能{r['skip']}) / 違反 {len(r['out'])}件 / 最悪 {r['worst']}:1")
        for x in sorted(r['out'], key=lambda x: x['ratio'])[:8]:
            print(f"   {x['ratio']}:1 (要{x['need']}) {x['px']}px  {x['sel']}  \"{x['txt']}\"")
        if len(r['out']) > 8: print(f"   … 他 {len(r['out'])-8} 件")
