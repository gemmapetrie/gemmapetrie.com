"""Generate the static site from build/collections.json (scraped from Squarespace).

Run from the repo root:  python3 build/build.py
Downloads images into images/ (skips ones already present) and writes all HTML pages.
"""
import hashlib, html, json, os, re, subprocess, sys, time, datetime
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from clean import clean

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, 'images')
os.makedirs(IMG_DIR, exist_ok=True)

SITE = 'Gemma Petrie'
DOMAIN = 'https://gemmapetrie.com/'
PAGES = []
EMAIL = 'gemmapetrie@gmail.com'
# Contact form: set by putting the form endpoint URL (a public URL) in build/contact_endpoint.txt.
# Without it, Contact falls back to a mailto link and no contact page is built.
_ep = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contact_endpoint.txt')
CONTACT_ENDPOINT = open(_ep).read().strip() if os.path.exists(_ep) else ''
CONTACT_HREF = lambda root='': (root + 'contact.html') if CONTACT_ENDPOINT else f'mailto:{EMAIL}'
PROFILE_IMG = 'https://images.squarespace-cdn.com/content/v1/5fe0fbec379c5c56f0c80371/1608588010818-VII993KJN9B3AQH5UFS0/L1090151.JPG'
ABOUT_IMG = 'https://images.squarespace-cdn.com/content/v1/5fe0fbec379c5c56f0c80371/1608587013933-BV1YQM5HI74UJXC5TU2C/2019-04-03+23.40.56-1.jpg'

# ---------- images ----------
from images import ImageStore, normalize_url as local_name
store = ImageStore(IMG_DIR, flickr_size=1600, flickr_quality=84)
wanted = store.wanted

def register(src):
    return '@ROOT@images/' + store.register(src)

# ---------- content ----------
data = json.load(open(os.path.join(ROOT, 'build', 'collections.json')))


MINOR = {'a','an','and','as','at','but','by','for','in','nor','of','on','or','the','to','vs','via'}
def title_case(t):
    out = []; start = True
    for w in t.split(' '):
        core = w.lstrip('“"‘\'(')
        pre = w[:len(w) - len(core)]
        def cap(part, force):
            bare = part.strip('.,:;!?”"’\')')
            if not bare: return part
            if any(c.isupper() for c in bare[1:]) or any(c.isdigit() for c in bare): return part
            if bare.lower() in MINOR and not force: return part.lower() if part.lower()==part else part[:0]+part.lower()
            return part[0].upper() + part[1:]
        parts = core.split('-')
        core2 = '-'.join(cap(p, start or i > 0) for i, p in enumerate(parts))
        out.append(pre + core2)
        start = core.endswith((':', '?', '!', '.', '—'))
    return ' '.join(out)

def build_items(kind):
    items = []
    for it in data[kind]:
        slug = it['urlId'].split('/')[-1]
        body = clean(it['body'], register)
        d = datetime.datetime.fromtimestamp(it['publishOn'] / 1000, datetime.timezone.utc)
        thumb = register(it['assetUrl']) if it.get('assetUrl') else None
        text = re.sub(r'<[^>]+>', ' ', body)
        text = html.unescape(re.sub(r'\s+', ' ', text)).strip()
        items.append(dict(slug=slug, title=(title_case(html.unescape(it['title'])) if kind == 'blog' else html.unescape(it['title'])), date=d, body=body,
                          thumb=thumb, excerpt=(text[:170].rsplit(' ', 1)[0] + '…') if len(text) > 170 else text))
    items.sort(key=lambda x: x['date'], reverse=True)
    return items

posts = build_items('blog')
recipes = build_items('recipes')

print('upgraded from Flickr originals:', store.refresh_flickr())
print(f'downloading {len(wanted)} images…')
failed = store.fetch_all()
print('failed:', len(failed))
keep = set(wanted.values()) | {'portrait.jpg','favicon.png','favicon.svg','og.jpg'}
for f in os.listdir(IMG_DIR):
    if f not in keep: os.remove(os.path.join(IMG_DIR, f))

def finish(s, root):
    # drop <img> whose download failed, then resolve root
    for f in failed:
        s = re.sub(r'<img src="@ROOT@images/%s"[^>]*>' % re.escape(f), '', s)
    # old Squarespace internal links -> new static paths
    s = re.sub(r'href="(?:https?://www\.gemmapetrie\.com)?/blog/([^"/#?]+)/?"', r'href="@ROOT@writing/\1.html"', s)
    s = re.sub(r'href="(?:https?://www\.gemmapetrie\.com)?/recipes/(?:\d{4}/\d\d/\d\d/)?([^"/#?]+)/?"', r'href="@ROOT@recipes/\1.html"', s)
    s = s.replace(f'href="mailto:{EMAIL}"', f'href="#contact" data-u="{EMAIL.split("@")[0]}" data-d="{EMAIL.split("@")[1]}"')
    s = re.sub(r'href="(www\.[^"]+)"', r'href="https://\1"', s)
    rslugs = {r['slug'] for r in recipes}; pslugs = {p['slug'] for p in posts}
    def old_site(m):
        kind, slug = m.group(1), m.group(2)
        if slug in rslugs and kind in ('foodandtravel', 'recipes'): return f'href="@ROOT@recipes/{slug}.html"'
        if slug in pslugs: return f'href="@ROOT@writing/{slug}.html"'
        return m.group(0)
    s = re.sub(r'href="https?://(?:www\.)?gemmapetrie\.com/(foodandtravel|all|blog|recipes)/(?:\d{4}/\d\d/\d\d/)?([^"/#?]+)[^"]*"', old_site, s)
    return s.replace('@ROOT@', root)

# ---------- templates ----------
def esc(s): return html.escape(s, quote=True)

NAV = [('publications', 'publications.html', 'Publications'), ('speaking', 'speaking.html', 'Speaking'),
       ('writing', 'writing/index.html', 'Writing'), ('recipes', 'recipes/index.html', 'Recipes'),
       ('about', 'about.html', 'About')]

CSS_V = hashlib.sha1(open(os.path.join(ROOT, 'style.css'), 'rb').read()).hexdigest()[:8]  # cache-bust so style changes show right away

def page(title, body, root='', current='', desc='', extra_class=''):
    cur = ' aria-current="page"'
    nav = ''.join(f'<a href="{root}{href}"{cur if key == current else ""}>{label}</a>' for key, href, label in NAV)
    nav += (f'<a href="{root}contact.html"{cur if current == "contact" else ""}>Contact</a>' if CONTACT_ENDPOINT
            else f'<a href="mailto:{EMAIL}">Contact</a>')
    foot_contact = (f'<a href="{root}contact.html">Contact</a>' if CONTACT_ENDPOINT else f'<a href="mailto:{EMAIL}">Email</a>')
    full_title = SITE if not title else f'{title} · {SITE}'
    out = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc or 'Gemma Petrie is a Principal Researcher in Chicago exploring the intersection of people, society, and technology.')}">
<link rel="icon" type="image/svg+xml" href="{root}images/favicon.svg"><link rel="icon" type="image/png" href="{root}images/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Young+Serif&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}style.css?v={CSS_V}">
</head>
<body class="{extra_class}">
<a class="skip" href="#content">Skip to content</a>
<header class="wrap top">
  <a class="brand" href="{root}index.html">Gemma Petrie</a>
  <nav aria-label="Main">{nav}</nav>
</header>
<main id="content" class="wrap" tabindex="-1">
{body}
</main>
<footer class="site-footer"><div class="wrap"><span>© Gemma Petrie<noscript> · {EMAIL.replace("@"," [at] ").replace("."," [dot] ")}</noscript></span><nav aria-label="Footer"><a href="https://www.linkedin.com/in/gemmapetrie/">LinkedIn</a>{foot_contact}</nav></div></footer>
<script>document.querySelectorAll("a[data-u]").forEach(function(a){{a.addEventListener("click",function(e){{e.preventDefault();location.href="mail"+"to:"+a.dataset.u+"@"+a.dataset.d;}});}});</script>
</body>
</html>
'''
    return finish(out, root)

def _jpeg_size(p):
    import struct
    d = open(p, 'rb').read(); i = 2
    while i < len(d):
        if d[i] != 0xFF: i += 1; continue
        if d[i+1] in (0xC0, 0xC1, 0xC2): h, w = struct.unpack('>HH', d[i+5:i+9]); return w, h
        i += 2 + struct.unpack('>H', d[i+2:i+4])[0]
    return 0, 0

def pair_portraits(content, path):
    """A paragraph holding only two portrait photos becomes a side-by-side pair."""
    up = '../' * path.count('/')
    def repl(m):
        body = m.group(1)
        srcs = re.findall(r'<img src="' + re.escape(up) + r'(images/[^"]+)"', body)
        if len(srcs) != 2 or re.sub(r'<a [^>]*>|</a>|<img[^>]*>|\s|<br>', '', body): return m.group(0)
        try: sizes = [_jpeg_size(os.path.join(ROOT, s)) for s in srcs]
        except OSError: return m.group(0)
        return f'<p class="pair">{body}</p>' if all(h > w for w, h in sizes) else m.group(0)
    return re.sub(r'<p>(.*?)</p>', repl, content, flags=re.S)

def write(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    content = pair_portraits(content, path)
    if '<link rel="stylesheet"' in content and '<meta name="robots" content="noindex">' not in content:
        url = DOMAIN + ('' if path == 'index.html' else path)
        t = re.search(r'<title>(.*?)</title>', content).group(1)
        d = re.search(r'<meta name="description" content="(.*?)">', content).group(1)
        og = (f'<link rel="canonical" href="{url}">\n<meta property="og:type" content="website">\n<meta property="og:site_name" content="Gemma Petrie">\n'
              f'<meta property="og:title" content="{t}">\n<meta property="og:description" content="{d}">\n<meta property="og:url" content="{url}">\n'
              f'<meta property="og:image" content="{DOMAIN}images/og.jpg">\n<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">\n'
              f'<meta name="twitter:card" content="summary_large_image">\n')
        content = content.replace('</head>', og + '</head>', 1)
        if path != '404.html': PAGES.append(path)
    open(full, 'w').write(content)

def fmt(d): return d.strftime('%B %-d, %Y')

# home
# home: "Selected work" strip (links come from publications.json)
_pubs = json.load(open(os.path.join(ROOT, 'build', 'publications.json')))
_url = lambda prefix: next(x['url'] for x in _pubs if x['title'].startswith(prefix))
SELECTED = [
    ('Active Choice Interventions', '2026 · NBER Working Paper', 'Active Choice Interventions at Scale',
     'Browser choice screens required by the DMA increased Firefox daily active users by 91% on iOS and 13% on Android, evidence that regulation can help independent browsers compete.'),
    ('Designing Better Digital Competition Remedies', '2025 · Mozilla', 'Designing Better Digital Competition Remedies',
     'Case studies from Mozilla’s competition research on how concept testing, usability testing, and behavioral experiments can strengthen the design of regulatory remedies.'),
    ('Can Browser Choice Screens Be Effective', '2023 · Mozilla', 'Can Browser Choice Screens Be Effective?',
     'A 12,000-person experiment in Germany, Spain, and Poland showing that a choice screen’s design, content, and timing shape its effectiveness.'),
    ('Who Gets to Define Success', '2020 · Ethnographic Praxis in Industry', 'Who Gets to Define Success?',
     'Diary studies, interviews, and workshops with 61 people in six cities show what usage metrics leave out: a low-usage product like Firefox Focus can still play a distinct role in how people browse.'),
]
selected_html = ('<section class="sw"><div class="sw-head"><h2>Selected work</h2><a href="publications.html">Publications →</a></div><div class="sw-grid">'
    + ''.join(f'<a class="sw-card" href="{esc(_url(k))}"><span class="sw-meta">{m}</span><h3>{t}</h3><p>{d}</p></a>' for k, m, t, d in SELECTED)
    + '</div></section>')

write('index.html', page('', f'''
<section class="hero">
  <h1>I <span class="u">research</span> how design and platform conditions shape people’s choices and experiences with technology.</h1>
  <div class="wr"><div class="ph"><img src="@ROOT@images/portrait.jpg" alt="Gemma Petrie" width="1000" height="1000"></div></div>
</section>
<section class="bio">
  <p>I’m Gemma Petrie (she/her), a Principal Researcher in Chicago, exploring the intersection of people, society, and technology. My work focuses on understanding how technology and design impact people’s lives and how research can inform policy and regulation.</p>
  <p>I lead competition and regulation research for <a class="m" href="https://research.mozilla.org/browser-competition/">Mozilla</a>. Previously, I led the <a class="m" href="https://www.firefox.com/">Firefox</a> User Research Team.</p>
</section>
{selected_html}''', extra_class='home'))

# contact (only when a form endpoint is configured)
if CONTACT_ENDPOINT:
    write('contact.html', page('Contact', f'''<section class="prose contact">
  <h1>Contact</h1>
  <p class="sub">Send a message and it goes to my email.</p>
  <form id="cform" action="{esc(CONTACT_ENDPOINT)}" method="POST" class="cform">
    <label>Name<input name="name" type="text" autocomplete="name" required></label>
    <label>Email<input name="email" type="email" autocomplete="email" required></label>
    <label>Message<textarea name="message" rows="7" required></textarea></label>
    <input type="text" name="_gotcha" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">
    <button type="submit">Send</button>
    <p id="cstatus" role="status" aria-live="polite"></p>
  </form>
</section>
<script>
document.getElementById("cform").addEventListener("submit", function (e) {{
  e.preventDefault();
  var f = e.target, s = document.getElementById("cstatus"), b = f.querySelector("button");
  b.disabled = true; s.textContent = "Sending…";
  fetch(f.action, {{ method: "POST", body: new FormData(f), headers: {{ Accept: "application/json" }} }})
    .then(function (r) {{ if (!r.ok) throw 0; f.reset(); s.textContent = "Thanks. Your message was sent."; }})
    .catch(function () {{ s.textContent = "Something went wrong. Please try again."; }})
    .then(function () {{ b.disabled = false; }});
}});
</script>''', current='contact', desc='Contact Gemma Petrie'))
elif os.path.exists(os.path.join(ROOT, 'contact.html')):
    os.remove(os.path.join(ROOT, 'contact.html'))

# about
write('about.html', page('About', f'''
<div class="about"><article class="prose">
  <h1>About</h1>
  <p>As Principal Researcher at <a href="https://research.mozilla.org/browser-competition/">Mozilla</a>, I lead research at the intersection of competition, regulation, and technology—investigating how digital interfaces shape user behavior and how well-designed regulatory remedies can promote real choice and meaningful competition in tech markets. Over the past four years, I’ve led Mozilla’s <a href="https://research.mozilla.org/browser-competition/">research portfolio</a> on browser choice and defaults, directly informing global regulatory initiatives such as the EU’s Digital Markets Act (DMA).</p>
  <p>With over 15 years of experience in user research, my expertise includes managing mixed-method teams, defining organizational standards and processes for high-quality research, fostering a culture of cross-functional collaboration, and scaling the impact of research in fast-paced, distributed organizations. I previously led the <a href="https://www.firefox.com/">Firefox</a> User Research Team, where I helped shape research strategy for one of the world’s most widely used browsers.</p>
  <p>I care deeply about understanding the complex interplay between people, technology, and context—and using research to shape more open, user-centered digital experiences. I hold a BA in Philosophy from <a href="https://www.reed.edu/">Reed College</a> and an MLIS from the <a href="https://ischool.illinois.edu/">University of Illinois at Urbana-Champaign</a>. I’ve been recognized as one of Chicago’s Tech 50 by <em>Crain’s</em> and as a Person of the Year by the <em>Chicago Reader</em> for my contributions to the UX community.</p>
  <p>Interested in working together? Please <a href="{CONTACT_HREF()}">get in touch</a>.</p>
</article>
<div class="wr"><div class="ph"><img src="@ROOT@images/portrait.jpg" alt="Gemma Petrie" width="1000" height="1000"></div></div></div>''', current='about', desc='About Gemma Petrie'))

# speaking / publications: simple lists driven by build/speaking.json and build/publications.json
def entries_page(slug, title, intro, link_event=False):
    items = json.load(open(os.path.join(ROOT, 'build', slug + '.json')))
    def when(d):
        parts = str(d).split('-')
        return (datetime.date(int(parts[0]), int(parts[1]), 1).strftime('%B %Y')) if len(parts) > 1 else parts[0]
    if not items:
        inner = f'<p class="sub">Coming soon. In the meantime, see <a href="writing/index.html">Writing</a> or <a href="{CONTACT_HREF()}">get in touch</a>.</p>'
    else:
        inner = ''
        groups = {}
        for it in sorted(items, key=lambda x: str(x.get('date', '')), reverse=True):
            groups.setdefault(str(it.get('date', ''))[:4] or 'Other', []).append(it)
        for y in sorted(groups, reverse=True):
            inner += f'<h2 class="year">{esc(y)}</h2><ul class="list">'
            for it in groups[y]:
                t = esc(it['title']); pub = esc(it.get('publication') or it.get('detail') or '')
                if it.get('url'):
                    if link_event and pub: pub = f'<a href="{esc(it["url"])}">{pub}</a>'
                    else: t = f'<a href="{esc(it["url"])}">{t}</a>'
                inner += (f'<li><div class="row"><span class="txt"><span class="t">{t}</span>'
                          + (f'<span class="ex">{pub}' + (f'<span class="org">{esc(it["organizer"])}</span>' if it.get('organizer') else '') + '</span>' if pub else '') + '</span>'
                          + f'<time>{when(it["date"])}</time></div></li>')
            inner += '</ul>'
    write(f'{slug}.html', page(title, f'<section class="prose wide"><h1>{title}</h1><p class="sub">{intro}</p>{inner}</section>', current=slug))

entries_page('speaking', 'Speaking', 'Selected talks, panels, and conference sessions', link_event=True)
entries_page('publications', 'Publications', 'Selected papers, reports, and articles')

# writing
cards = ''.join(
    f'<li><a href="{p["slug"]}.html">' +
    (f'<img src="{p["thumb"]}" alt="" loading="lazy">' if p['thumb'] else '<span class="ph"></span>') +
    f'<span class="t">{esc(p["title"])}</span><time>{p["date"].strftime("%B %Y")}</time></a></li>'
    for p in posts)
write('writing/index.html', page('Writing', f'<section class="wide"><h1>Writing</h1><ul class="grid cards">{cards}</ul></section>', root='../', current='writing'))

for i, p in enumerate(posts):
    write(f'writing/{p["slug"]}.html', page(p['title'], f'''
<article class="prose post">
  <p class="back"><a href="index.html">← Back</a></p>
  <h1>{esc(p["title"])}</h1>
  <p class="meta"><time datetime="{p["date"].date()}">{fmt(p["date"])}</time></p>
  {p["body"]}
</article>''', root='../', current='writing', desc=p['excerpt']))

# recipes
cards = ''.join(
    f'<li><a href="{r["slug"]}.html">' +
    (f'<img src="{r["thumb"]}" alt="" loading="lazy">' if r['thumb'] else '<span class="ph"></span>') +
    f'<span class="t">{esc(r["title"])}</span></a></li>' for r in recipes)
write('recipes/index.html', page('Recipes', f'<section class="wide"><h1>Recipes</h1><p class="sub">Remember food blogs? I used to have one called <em>Pro Bono Baker</em> and I still make many of the recipes.<br>Apologies for any cringe writing you find here.</p><ul class="grid">{cards}</ul></section>', root='../', current='recipes'))

for r in recipes:
    write(f'recipes/{r["slug"]}.html', page(r['title'], f'''
<article class="prose post">
  <p class="back"><a href="index.html">← Back</a></p>
  <h1>{esc(r["title"])}</h1>
  <p class="meta"><time datetime="{r["date"].date()}">{fmt(r["date"])}</time></p>
  {r["body"]}
</article>''', root='../', current='recipes', desc=r['excerpt']))

write('404.html', page('Not found', '<section class="prose"><h1>Page not found</h1><p><a href="index.html">Back home</a></p></section>'))
print('done:', len(posts), 'posts,', len(recipes), 'recipes')

# ---------- redirect stubs for the old Squarespace paths ----------
def stub(path, target):
    write(path, f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Redirecting…</title>
<meta name="robots" content="noindex"><link rel="canonical" href="{target}">
<meta http-equiv="refresh" content="0; url={target}"><script>location.replace("{target}")</script></head>
<body><p>This page has moved: <a href="{target}">{target}</a></p></body></html>''')

stub('blog/index.html', '../writing/index.html')
stub('about/index.html', '../about.html')
for p in posts: stub(f'blog/{p["slug"]}/index.html', f'../../writing/{p["slug"]}.html')
for r in recipes: stub(f'recipes/{r["slug"]}/index.html', f'../{r["slug"]}.html')

# ---------- report: photos that could not be recovered ----------
inv = {f: u for u, f in wanted.items()}
lines = []
for kind, items in (('recipe', recipes), ('post', posts)):
    for it in items:
        miss = [inv[f] for f in re.findall(r'@ROOT@images/([0-9a-f]+\.jpg)', it['body']) if f in failed]
        if miss: lines.append(f"{kind}\t{it['slug']}\t{len(miss)}\t" + ' '.join(miss))
open(os.path.join(ROOT, 'build', 'missing_images.txt'), 'w').write('\n'.join(lines) + '\n')
print('posts/recipes with missing photos:', len(lines))

# ---------- sitemap + robots ----------
urls = ''.join(f'  <url><loc>{DOMAIN}{"" if p == "index.html" else p}</loc></url>\n' for p in sorted(PAGES))
write_raw = lambda n, c: open(os.path.join(ROOT, n), 'w').write(c)
write_raw('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + '</urlset>\n')
write_raw('robots.txt', f'User-agent: *\nAllow: /\nSitemap: {DOMAIN}sitemap.xml\n')
