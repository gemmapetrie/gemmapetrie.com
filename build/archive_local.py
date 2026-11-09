"""Build a private, local-only copy of the old Pro Bono Baker / research blog archive.

    python3 build/archive_local.py

Writes a plain static folder OUTSIDE this repo (default ../gemmapetrie-archive). Open its index.html
in a browser. It is not part of the published site and has no password.
"""
import html, os, re, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from images import ImageStore
from wpparse import load_entries, plain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get('ARCHIVE_OUT', os.path.join(os.path.dirname(ROOT), 'gemmapetrie-archive'))
store = ImageStore(os.path.join(ROOT, 'build', 'cache_archive'), flickr_size=1600, flickr_quality=84)
entries = load_entries(lambda src: '@IMG:' + store.register(src))
print(len(entries), 'entries,', sum(len(e['comments']) for e in entries), 'comments')
print('upgraded from Flickr originals:', store.refresh_flickr())
print(f'fetching {len(store.wanted)} images (cached ones are skipped)…')
failed = store.fetch_all(); print('images failed:', len(failed))

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(os.path.join(OUT, 'posts')); os.makedirs(os.path.join(OUT, 'images'))
shutil.copy(os.path.join(ROOT, 'style.css'), os.path.join(OUT, 'style.css'))
esc = lambda s: html.escape(s, quote=True)

def fix_imgs(h, up):
    def repl(m):
        n = m.group(1)
        if n in failed: return ''
        src = os.path.join(store.dir, n)
        if not os.path.exists(os.path.join(OUT, 'images', n)): shutil.copy(src, os.path.join(OUT, 'images', n))
        return f'<img src="{up}images/{n}" alt="{m.group(2)}" loading="lazy">'
    return re.sub(r'<img src="@IMG:([0-9a-f]+\.jpg)" alt="([^"]*)" loading="lazy">', repl, h)

def shell(title, body, up=''):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Young+Serif&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}style.css"></head>
<body><div class="wrap top"><a class="brand" href="{up}index.html">Archive</a><nav></nav><span style="justify-self:end;color:var(--muted);font-size:.9rem">Local copy · not published</span></div>
<main class="wrap">{body}</main></body></html>'''

for e in entries:
    byp = {}
    for c in e['comments']: byp.setdefault(c['parent'] or '0', []).append(c)
    def draw(pid, d):
        return ''.join(f'<div class="comment" style="margin-left:{min(d,4)*1.25}rem"><p class="c-meta"><strong>{esc(c["author"])}</strong> · {c["date"]}</p>'
                       f'<p class="c-text">{esc(c["text"])}</p>{draw(c["id"], d+1)}</div>' for c in byp.get(pid, []))
    comments = (f'<section class="comments"><h2>{len(e["comments"])} comment{"s" if len(e["comments"])>1 else ""}</h2>{draw("0",0)}</section>' if e['comments'] else '')
    body = (f'<article class="prose post"><p class="back"><a href="../index.html">← Archive</a></p><h1>{esc(e["title"])}</h1>'
            f'<p class="meta">{e["date"]}{" · " + esc(", ".join(e["cats"])) if e["cats"] else ""}</p>{fix_imgs(e["html"], "../")}{comments}</article>')
    open(os.path.join(OUT, 'posts', e['slug'] + '.html'), 'w').write(shell(e['title'], body, '../'))

# index: grouped by year, with a category row
cats = sorted({c for e in entries for c in e['cats']})
chips = ''.join(f'<a href="#" data-cat="{esc(c)}">{esc(c)}</a>' for c in cats)
os.makedirs(os.path.join(OUT, 'thumbs'), exist_ok=True)
def thumb_for(e):
    # first photo in the post that actually exists, as a small thumbnail
    for n in re.findall(r'@IMG:([0-9a-f]+\.jpg)', e['html']):
        src = os.path.join(store.dir, n)
        if n in failed or not os.path.exists(src): continue
        dest = os.path.join(OUT, 'thumbs', n)
        if not os.path.exists(dest):
            subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '70', '-Z', '360', src, '--out', dest], capture_output=True)
        return f'<img class="thumb" src="thumbs/{n}" alt="" loading="lazy">'
    return '<span class="thumb"></span>'

rows, year = '', None
for e in entries:
    y = e['date'][:4]
    if y != year:
        rows += ('</ul>' if year else '') + f'<h2 class="year">{y}</h2><ul class="list">'; year = y
    ex = re.sub(r'\s+', ' ', plain(re.sub(r'<img[^>]*>', '', e['html'])))
    ex = (ex[:150].rsplit(' ', 1)[0] + '…') if len(ex) > 150 else ex
    rows += (f'<li data-cats="{esc("|".join(e["cats"]))}" data-q="{esc((e["title"] + " " + ex).lower())}"><a href="posts/{e["slug"]}.html">'
             f'{thumb_for(e)}<span class="txt"><span class="t">{esc(e["title"])}</span><span class="ex">{esc(ex)}</span></span><time>{e["date"][5:]}</time></a></li>')
rows += '</ul>'
script = '''<script>
const q=document.getElementById('q'),sel=document.getElementById('cat');
function f(){const t=q.value.toLowerCase().trim(),c=sel.value;document.querySelectorAll('.list li').forEach(li=>{
li.hidden=!((!t||li.dataset.q.includes(t))&&(!c||li.dataset.cats.split('|').includes(c)))});
document.querySelectorAll('.list').forEach(ul=>{const h=ul.previousElementSibling;const any=[...ul.children].some(l=>!l.hidden);ul.hidden=h.hidden=!any})}
q.addEventListener('input',f);sel.addEventListener('change',f);</script>'''
opts = '<option value="">All categories</option>' + ''.join(f'<option>{esc(c)}</option>' for c in cats)
body = (f'<section class="prose wide"><h1>Archive</h1><p class="sub">{len(entries)} entries · Pro Bono Baker, user research and library writing</p>'
        f'<div class="a-filters"><input id="q" class="a-search" type="search" placeholder="Search titles and previews"><select id="cat" class="a-cat">{opts}</select></div>{rows}</section>{script}')
open(os.path.join(OUT, 'index.html'), 'w').write(shell('Archive', body))
print('wrote', OUT, '|', len(os.listdir(os.path.join(OUT, 'posts'))), 'pages,', len(os.listdir(os.path.join(OUT, 'images'))), 'images')
