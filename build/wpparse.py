"""Parse the WordPress export (old Pro Bono Baker + research blog) into entries."""
import html, os, re, sys, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
from clean import clean

WP_EXPORT = os.environ.get('WP_EXPORT', '/Users/gpetrie/Dropbox/Websites/GemmaPetrie.com/Backups/'
            'justtryingtoimportautocar.wordpress.com-2020-01-19-01_37_30/sitetitle.wordpress.2020-01-19.001.xml')
# the full Pro Bono Baker export (2005-2012) first, then the older 2020 export; duplicates by title+date are dropped
WP_NEW = '/Users/gpetrie/Dropbox/Websites/probonobaker.WordPress.2026-11-04.xml'
NS = {'wp': 'http://wordpress.org/export/1.2/', 'content': 'http://purl.org/rss/1.0/modules/content/'}
BLOCK = re.compile(r'^\s*<(?:p|h\d|ul|ol|li|blockquote|div|table|pre|figure|hr)\b', re.I)
SKIP_TITLES = {'My First Blog Post', 'Introduce Yourself (Example Post)', 'Blog Feed', '404', 'Copy of New Page', 'Home'}

def txt(el, path):
    e = el.find(path, NS)
    return (e.text or '') if e is not None else ''

def autop(s):
    s = s.replace('\r\n', '\n')
    s = re.sub(r'\[/?(?:caption|gallery|embed|video|audio|youtube|vimeo)[^\]]*\]', '', s)
    out = []
    for blk in re.split(r'\n\s*\n', s):
        blk = blk.strip()
        if blk: out.append(blk if BLOCK.match(blk) else '<p>' + blk.replace('\n', '<br>') + '</p>')
    return '\n'.join(out)

def plain(s):
    s = re.sub(r'<br\s*/?>|</p>', '\n', s or '')
    s = html.unescape(re.sub(r'<[^>]+>', '', s))
    return re.sub(r'\n{3,}', '\n\n', s).strip()

def _load(path, tag, on_img):
    root = ET.parse(path).getroot().find('channel')
    entries = []
    for it in root.findall('item'):
        kind = txt(it, 'wp:post_type')
        if kind not in ('post', 'page') or txt(it, 'wp:status') != 'publish': continue
        title = html.unescape(txt(it, 'title')).strip() or '(untitled)'
        if title in SKIP_TITLES: continue
        body = clean(autop(txt(it, 'content:encoded')), on_img)
        if kind == 'page' and len(plain(body)) < 200: continue
        comments = []
        for c in it.findall('wp:comment', NS):
            if txt(c, 'wp:comment_approved') != '1' or txt(c, 'wp:comment_type') in ('pingback', 'trackback'): continue
            comments.append(dict(id=txt(c, 'wp:comment_id'), parent=txt(c, 'wp:comment_parent'),
                                 author=txt(c, 'wp:comment_author') or 'Anonymous',
                                 date=txt(c, 'wp:comment_date')[:10], text=plain(txt(c, 'wp:comment_content'))))
        comments = [c for c in comments if c['text']]
        cats = [html.unescape(c.text) for c in it.findall('category') if c.get('domain') == 'category' and c.text]
        cats = [c for c in cats if c != 'Uncategorized']
        slug = re.sub(r'[^a-z0-9-]+', '-', (txt(it, 'wp:post_name') or txt(it, 'wp:post_id')).lower()).strip('-')
        entries.append(dict(slug=f'{tag}{kind[0]}-{txt(it, "wp:post_id")}-{slug}'[:90], kind=kind, title=title,
                            date=txt(it, 'wp:post_date')[:10], cats=cats, html=body, comments=comments))
    return entries

def load_entries(on_img):
    paths = [p for p in (WP_NEW, WP_EXPORT) if os.path.exists(p)]
    entries, seen = [], set()
    for n, path in enumerate(paths):
        for e in _load(path, 'abcd'[n], on_img):
            key = (re.sub(r'[^a-z0-9]+', '', e['title'].lower()), e['date'])
            if key in seen: continue
            seen.add(key); entries.append(e)
    entries.sort(key=lambda e: e['date'], reverse=True)
    return entries
