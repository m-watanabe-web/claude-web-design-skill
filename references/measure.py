#!/usr/bin/env python3
"""web-design スキルの静的チェッカー（構造・セマンティクス・見た目）。
コントラストは扱わない → references/contrast.py（Chrome headless 実測）を使うこと。

  python3 measure.py <file.html> [...]        # 全項目
  python3 measure.py --ux <file.html> [...]   # UX(ux.md)のみ
  python3 measure.py --look <file.html> [...] # 見た目(forbid.md)のみ

注意：静的解析のため、深く入れ子になった背景や JS で変わる状態は追えない。
コントラストは「:root のトークン＋body背景」を前提とした近似値。
"""
import re, sys, pathlib, colorsys

EMOJI = re.compile('[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]')  # 矢印は含めない

# ---------- 色の解決 ----------
def _hex2rgb(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def root_vars(css):
    m = re.search(r':root\s*\{(.*?)\}', css, re.S)
    return dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', m.group(1))) if m else {}

def resolve(val, vars_, depth=0):
    """var() / color-mix() を解いて (r,g,b,alpha) にする。解けなければ None。"""
    if depth > 6 or not val: return None
    val = val.strip()
    m = re.fullmatch(r'var\(\s*(--[\w-]+)\s*(?:,([^)]*))?\)', val)
    if m:
        return resolve(vars_.get(m.group(1), m.group(2) or ''), vars_, depth+1)
    m = re.fullmatch(r'color-mix\(\s*in\s+\w+\s*,\s*(.+?)\s+([\d.]+)%\s*,\s*(.+?)\s*\)', val)
    if m:
        base = resolve(m.group(1), vars_, depth+1); pct = float(m.group(2))/100
        if not base: return None
        if m.group(3).strip() == 'transparent':
            return (base[0], base[1], base[2], base[3]*pct)
        other = resolve(m.group(3), vars_, depth+1)
        if not other: return None
        return tuple(base[i]*pct + other[i]*(1-pct) for i in range(3)) + (1.0,)
    m = re.fullmatch(r'rgba?\(([^)]*)\)', val)
    if m:
        p = [x.strip() for x in re.split(r'[,\s/]+', m.group(1)) if x.strip()]
        try: return (float(p[0]), float(p[1]), float(p[2]), float(p[3]) if len(p) > 3 else 1.0)
        except (ValueError, IndexError): return None
    m = re.search(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b', val)
    if m: return _hex2rgb(m.group(0)) + (1.0,)
    return {'white': (255,255,255,1.0), 'black': (0,0,0,1.0)}.get(val.lower())

def _lin(c):
    c /= 255
    return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4

def contrast(fg, bg):
    over = tuple(fg[i]*fg[3] + bg[i]*(1-fg[3]) for i in range(3))
    lf = .2126*_lin(over[0]) + .7152*_lin(over[1]) + .0722*_lin(over[2])
    lb = .2126*_lin(bg[0]) + .7152*_lin(bg[1]) + .0722*_lin(bg[2])
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi+.05)/(lo+.05)

# ---------- 見た目（forbid.md） ----------
def extract_gradients(t):
    out = []
    for m in re.finditer(r'(linear|radial|conic)-gradient\(', t):
        i, d = m.end(), 1
        while i < len(t) and d:
            d += (t[i] == '(') - (t[i] == ')'); i += 1
        out.append(t[m.end():i-1])
    return out

def decorative(g):
    stops = re.findall(r'#[0-9a-fA-F]{3,6}|rgba?\([^)]*\)|var\(--[\w-]+\)|color-mix\([^)]*\)', g)
    hues = {s for s in stops if not re.search(r',\s*0\s*\)$', s)}
    return len(hues) >= 2

def hue_count(css):
    b, gray = set(), False
    for m in re.finditer(r'#([0-9a-fA-F]{6})\b|#([0-9a-fA-F]{3})\b', css):
        h = m.group(1) or ''.join(c*2 for c in m.group(2))
        r, g, bl = [x/255 for x in _hex2rgb(h)]
        hh, l, s = colorsys.rgb_to_hls(r, g, bl)
        if s < .12: gray = True
        else: b.add(int(hh*360)//30)
    return len(b) + (1 if gray else 0)

# ---------- 本体 ----------
def measure(p):
    t = pathlib.Path(p).read_text(encoding='utf-8')
    css = ' '.join(re.findall(r'<style.*?>(.*?)</style>', t, re.S))
    gs = extract_gradients(t)
    heads = re.findall(r'<h([1-6])\b', t)
    skip = any(int(heads[i+1]) - int(heads[i]) > 1 for i in range(len(heads)-1))
    inputs = len(re.findall(r'<(input|select|textarea)\b', t))
    labels = len(re.findall(r'<label[^>]*\bfor=', t))
    return {
        'file': pathlib.Path(p).name,
        # --- UX (ux.md) ---
        'alt欠落': len(re.findall(r'<img(?![^>]*\balt=)', t)),
        'ラベル欠落': max(0, inputs - labels),
        '空リンク': len(re.findall(r'href="#"', t)) + len(re.findall(r'<button[^>]*>\s*</button>', t)),
        'lang': 'o' if re.search(r'<html[^>]*\blang=', t) else 'X',
        '見出し飛び': 'X' if skip else 'o',
        'focus': 'o' if re.search(r':focus', css) else 'X',
        'reduced-motion': 'o' if 'prefers-reduced-motion' in css else ('-' if not re.search(r'@keyframes|animation\s*:|transition\s*:', css) else 'X'),
        'main': 'o' if '<main' in t else 'X',
        'viewport': 'o' if 'name="viewport"' in t else 'X',
        # --- 見た目 (forbid.md) ---
        '装飾グラデ': sum(1 for g in gs if decorative(g)),
        '色相数': hue_count(css),
        '絵文字': len(EMOJI.findall(t)),
        '角丸': len(re.findall(r'border-radius', css)),
        '均一カード': len(re.findall(r'repeat\(\s*3\s*,\s*1fr|repeat\(auto-fit', css)),
        'KB': round(len(t.encode())/1024),
    }

UX = ['file','alt欠落','ラベル欠落','空リンク','lang','見出し飛び','focus','reduced-motion','main','viewport']
LOOK = ['file','装飾グラデ','色相数','絵文字','角丸','均一カード','KB']

def show(rows, keys):
    wcs = lambda s: sum(2 if ord(c) > 0x2000 else 1 for c in str(s))
    w = {k: max(wcs(k), *(wcs(r[k]) for r in rows)) for k in keys}
    pad = lambda v, k: str(v) + ' '*(w[k]-wcs(v))
    print(' | '.join(pad(k, k) for k in keys))
    print('-+-'.join('-'*w[k] for k in keys))
    for r in rows: print(' | '.join(pad(r[k], k) for k in keys))

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    mode = next((a for a in sys.argv[1:] if a.startswith('--')), None)
    rows = [measure(p) for p in args]
    if mode != '--look':
        print('■ UX（ux.md）  o=満たす X=違反 -=該当なし'); show(rows, UX); print()
    if mode != '--ux':
        print('■ 見た目（forbid.md）'); show(rows, LOOK); print()
    print("※ コントラストはこのスクリプトでは判定しない（入れ子の背景を追えず誤検出・見逃しの両方が出た）。")
    print("   必ず実レンダリングで測ること: python3 contrast.py <file.html>")
