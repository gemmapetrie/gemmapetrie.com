"""Convert Squarespace post body HTML into clean, minimal HTML.
Collects image URLs into a list so a downloader can fetch them."""
import re, html
from html.parser import HTMLParser

KEEP = {'p','h2','h3','h4','h5','ul','ol','li','a','strong','em','b','i','u','br','blockquote',
        'figure','figcaption','pre','code','hr','sup','sub','table','thead','tbody','tr','td','th'}
MAP = {'h1': 'h2'}
VOID = {'br','hr','img'}
SKIP = {'script','style','noscript'}
EMBED_OK = ('youtube.com','youtu.be','vimeo.com','docs.google.com','slides.com','soundcloud.com','spotify.com')

class Cleaner(HTMLParser):
    def __init__(self, on_img):
        super().__init__(convert_charrefs=True)
        self.out=[]; self.skip=0; self.on_img=on_img; self.stack=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in SKIP: self.skip+=1; return
        if self.skip: return
        tag=MAP.get(tag,tag)
        if tag=='img':
            src=a.get('data-src') or a.get('src') or ''
            if not src: return
            new=self.on_img(src)
            alt=html.escape(a.get('alt') or '',quote=True)
            self.out.append(f'<img src="{new}" alt="{alt}" loading="lazy">'); return
        if tag=='iframe':
            src=a.get('src') or ''
            if src.startswith('//'): src='https:'+src
            if any(d in src for d in EMBED_OK):
                self.out.append(f'<div class="embed"><iframe src="{html.escape(src,quote=True)}" loading="lazy" allowfullscreen></iframe></div>')
            return
        if tag in KEEP:
            if tag=='a':
                href=a.get('href')
                if not href: self.stack.append(None); return
                self.out.append(f'<a href="{html.escape(href,quote=True)}">'); self.stack.append('a'); return
            self.out.append(f'<{tag}>')
            if tag not in VOID: self.stack.append(tag)
        else:
            self.stack.append(None)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and tag in KEEP: self.handle_endtag(tag)
    def handle_endtag(self, tag):
        if tag in SKIP: self.skip=max(0,self.skip-1); return
        if self.skip: return
        tag=MAP.get(tag,tag)
        if tag in VOID or tag=='iframe': return
        if self.stack:
            t=self.stack.pop()
            if t: self.out.append(f'</{t}>')
    def handle_data(self, d):
        if self.skip: return
        self.out.append(html.escape(d,quote=False))

def clean(body, on_img):
    c=Cleaner(on_img); c.feed(body)
    s=''.join(c.out)
    while c.stack:
        t=c.stack.pop()
        if t: s+=f'</{t}>'
    s=re.sub(r'<(p|h[2-5]|li|blockquote|figcaption)>(\s|&nbsp;| |<br>)*</\1>','',s)
    s=re.sub(r'(<p>\s*</p>\s*)+','',s)
    return s
