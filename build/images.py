"""Shared image pipeline: register URLs, then fetch every one into a cache dir as a <=1200px JPEG.

Source order per URL:
  1. local Flickr export (matched by photo id found in the URL or filename)
  2. Wayback Machine for Typepad-hosted images (serialized + paced to avoid 429s)
  3. the original URL
"""
import hashlib, html, os, re, subprocess, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

FLICKR_DIR = os.environ.get('FLICKR_DIR', '/Users/gpetrie/Dropbox/Photos/Flickr')
UA = {'User-Agent': 'Mozilla/5.0'}
_wayback_lock = threading.Lock()

_flickr_index = None
def flickr_index():
    global _flickr_index
    if _flickr_index is None:
        _flickr_index = {}
        if os.path.isdir(FLICKR_DIR):
            for dp, _, fs in os.walk(FLICKR_DIR):
                for f in fs:
                    m = re.search(r'_(\d{8,})_o\.(?:jpe?g|png|gif)$', f, re.I)
                    if m: _flickr_index.setdefault(m.group(1), os.path.join(dp, f))
    return _flickr_index

def to_jpeg(src, dest):
    subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '78', '-Z', '1200', src, '--out', dest],
                   check=True, capture_output=True)

def normalize_url(src):
    if src.startswith('//'): src = 'https:' + src
    src = html.unescape(src).replace('http://', 'https://')
    if 'squarespace-cdn.com' in src and 'format=' not in src:
        src += ('&' if '?' in src else '?') + 'format=1500w'
    return src

def flickr_id(url):
    # farm5.static.flickr.com/4132/5045275118_6ba953bb8b.jpg  or  .../2020/01/332c6-5308316758_501c5a0273_b.jpg
    m = re.search(r'(?<![\d])(\d{9,11})_[0-9a-f]{8,12}', url)
    return m.group(1) if m else None

class ImageStore:
    def __init__(self, cache_dir):
        self.dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.wanted = {}   # url -> filename
        self.failed = set()  # filenames

    def register(self, src):
        url = normalize_url(src)
        if url not in self.wanted:
            self.wanted[url] = hashlib.sha1(url.encode()).hexdigest()[:12] + '.jpg'
        return self.wanted[url]

    def _fetch_bytes(self, url):
        wayback = 'typepad.com' in url
        if wayback and os.environ.get('NO_WAYBACK'): return None
        target = ('https://web.archive.org/web/2015id_/' + url) if wayback else url
        for attempt in range(5):
            try:
                if wayback:
                    with _wayback_lock:
                        time.sleep(1.5)
                        data = urllib.request.urlopen(urllib.request.Request(target, headers=UA), timeout=60).read()
                else:
                    data = urllib.request.urlopen(urllib.request.Request(target, headers=UA), timeout=45).read()
                if len(data) < 200: raise ValueError('tiny')
                return data
            except urllib.error.HTTPError as e:
                if e.code == 429 and wayback:
                    with _wayback_lock: time.sleep(30)
                    continue
                if e.code in (403, 404, 410): return None
                time.sleep(1)
            except Exception:
                time.sleep(1)
        return None

    def _fetch(self, url):
        path = os.path.join(self.dir, self.wanted[url])
        if os.path.exists(path) and os.path.getsize(path) > 0: return url, True
        fid = flickr_id(url) if ('flickr.com' in url or 'wordpress.com' in url) else None
        src = flickr_index().get(fid) if fid else None
        if src:
            to_jpeg(src, path); return url, True
        data = self._fetch_bytes(url)
        if not data: return url, False
        tmp = path + '.tmp'
        open(tmp, 'wb').write(data)
        try:
            to_jpeg(tmp, path)
        except subprocess.CalledProcessError:
            return url, False
        finally:
            if os.path.exists(tmp): os.remove(tmp)
        return url, True

    def fetch_all(self):
        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(self._fetch, list(self.wanted)))
        self.failed = {self.wanted[u] for u, ok in results if not ok}
        return self.failed
