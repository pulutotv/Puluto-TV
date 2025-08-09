import os
from flask import Flask, Response, stream_with_context
import requests
from urllib.parse import unquote, urljoin
from cachetools import TTLCache

# --- Dinamik İmza Alan Gelişmiş VavooResolver Sınıfı ---
class VavooResolver:
    def __init__(self):
        self.session = requests.Session()
        self.signature_cache = TTLCache(maxsize=1, ttl=3600)
        self.resolved_link_cache = TTLCache(maxsize=100, ttl=3600)

    def get_auth_signature(self):
        cached_sig = self.signature_cache.get("auth_sig")
        if cached_sig:
            print("Signature CACHE HIT")
            return cached_sig
        print("Fetching new signature from Vavoo...")
        headers = {"user-agent": "okhttp/4.11.0", "accept": "application/json", "content-type": "application/json; charset=utf-8"}
        data = {
            "token": "tosFwQCJMS8qrW_AjLoHPQ41646J5dRNha6ZWHnijoYQQQoADQoXYSo7ki7O5-CsgN4CH0uRk6EEoJ0728ar9scCRQW3ZkbfrPfeCXW2VgopSW2FWDqPOoVYIuVPAOnXCZ5g",
            "reason": "app-blur", "locale": "de", "theme": "dark",
            "metadata": {
                "device": {"type": "Handset", "brand": "google", "model": "Nexus", "name": "21081111RG", "uniqueId": "d10e5d99ab665233"},
                "os": {"name": "android", "version": "7.1.2", "abis": ["arm64-v8a", "armeabi-v7a", "armeabi"], "host": "android"},
                "app": {"platform": "android", "version": "3.1.20", "buildId": "289515000", "engine": "hbc85", "signatures": ["6e8a975e3cbf07d5de823a760d4c2547f86c1403105020adee5de67ac510999e"], "installer": "app.revanced.manager.flutter"},
                "version": {"package": "tv.vavoo.app", "binary": "3.1.20", "js": "3.1.20"}
            },
            "package": "tv.vavoo.app", "version": "3.1.20", "process": "app"
        }
        try:
            resp = self.session.post("https://www.vavoo.tv/api/app/ping", json=data, headers=headers, timeout=20)
            resp.raise_for_status()
            result = resp.json()
            addon_sig = result.get("addonSig")
            if addon_sig:
                print("New signature fetched successfully.")
                self.signature_cache["auth_sig"] = addon_sig
                return addon_sig
            return None
        except Exception as e:
            print(f"EXCEPTION while fetching signature: {e}")
            return None

    def resolve_vavoo_link(self, link):
        cached_link = self.resolved_link_cache.get(link)
        if cached_link:
            print(f"Resolved link CACHE HIT for: {link}")
            return cached_link
        print(f"Resolving Vavoo link: {link}")
        signature = self.get_auth_signature()
        if not signature:
            return None
        headers = {"user-agent": "MediaHubMX/2", "accept": "application/json", "content-type": "application/json; charset=utf-8", "mediahubmx-signature": signature}
        data = {"language": "de", "url": link, "clientVersion": "3.0.2"}
        try:
            resp = self.session.post("https://vavoo.to/mediahubmx-resolve.json", json=data, headers=headers, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            resolved_url = result[0].get("url") if isinstance(result, list) and result else result.get("url") if isinstance(result, dict) else None
            if resolved_url:
                print(f"Resolved successfully: {resolved_url}")
                self.resolved_link_cache[link] = resolved_url
                return resolved_url
            return None
        except Exception as e:
            print(f"EXCEPTION during Vavoo resolution: {e}")
            return None

# --- Flask Uygulaması ---
app = Flask(__name__)
vavoo_resolver = VavooResolver()
http_session = requests.Session()

# Ana M3U8 işleyici yolu
@app.route('/<path:full_path>')
def m3u8_handler(full_path):
    original_url_path = unquote(full_path)
    if not original_url_path.endswith('.m3u8'):
        return "Hata: URL '.m3u8' ile bitmelidir.", 400

    target_url = "https://" + original_url_path.removesuffix('.m3u8')
    print(f"STEP 1: Processing URL: {target_url}")

    resolved_m3u8_url = vavoo_resolver.resolve_vavoo_link(target_url)
    if not resolved_m3u8_url:
        return "Hata: Vavoo linki çözümlenemedi veya imza alınamadı. Logları kontrol edin.", 500

    print(f"STEP 2: Fetching M3U8 content from: {resolved_m3u8_url}")
    try:
        m3u8_response = http_session.get(resolved_m3u8_url, timeout=15)
        m3u8_response.raise_for_status()
        m3u8_content = m3u8_response.text
        
        # M3U8 içeriğindeki linkleri kendi proxy'miz üzerinden geçecek şekilde yeniden yaz
        base_url = urljoin(resolved_m3u8_url, '.')
        rewritten_content = []
        for line in m3u8_content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXT-X-KEY'):
                # Şifreleme anahtarı linkini yeniden yaz
                uri_part = line.split('URI="')[1].split('"')[0]
                new_uri = f"/key/{requests.utils.quote(uri_part, safe='')}"
                line = line.replace(uri_part, new_uri)
            elif line and not line.startswith('#'):
                # Video segmenti (.ts) linkini yeniden yaz
                segment_full_url = urljoin(base_url, line)
                line = f"/ts/{requests.utils.quote(segment_full_url, safe='')}"
            rewritten_content.append(line)
        
        final_content = "\n".join(rewritten_content)
        return Response(final_content, mimetype='application/vnd.apple.mpegurl')

    except Exception as e:
        print(f"EXCEPTION while fetching/rewriting M3U8: {e}")
        return f"Hata: M3U8 içeriği alınamadı veya işlenemedi. {e}", 500

# Video segmentlerini (.ts) proxy'leyen yol
@app.route('/ts/<path:ts_url>')
def ts_proxy(ts_url):
    decoded_url = requests.utils.unquote(ts_url)
    print(f"Proxying TS segment: {decoded_url}")
    try:
        req = http_session.get(decoded_url, stream=True, timeout=20)
        return Response(stream_with_context(req.iter_content(chunk_size=1024)), content_type=req.headers['content-type'])
    except Exception as e:
        print(f"EXCEPTION proxying TS: {e}")
        return "TS segment error", 500

# Şifreleme anahtarlarını proxy'leyen yol
@app.route('/key/<path:key_url>')
def key_proxy(key_url):
    decoded_url = requests.utils.unquote(key_url)
    print(f"Proxying KEY: {decoded_url}")
    try:
        req = http_session.get(decoded_url, timeout=15)
        return Response(req.content, content_type=req.headers['content-type'])
    except Exception as e:
        print(f"EXCEPTION proxying KEY: {e}")
        return "Key error", 500

@app.route('/')
def index():
    return """<h1>Nihai M3U8 Proxy</h1><p>Bu versiyon, tam akış proxy'si olarak çalışır.</p>"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
