import os
import requests
from flask import Flask, Response, stream_with_context
from urllib.parse import unquote, urljoin, quote
from cachetools import TTLCache

# --- Proxy Ayarlarını Çevre Değişkenlerinden Oku ---
# Bu ayar, Render.com'un "Environment" sekmesinden alınacaktır.
http_proxy = os.environ.get("PROXY")
proxies = {"http": http_proxy, "https": http_proxy} if http_proxy else None

if proxies:
    print("Harici proxy başarıyla yapılandırıldı.")
else:
    print("UYARI: Harici proxy ayarlanmamış. Render.com üzerinde istekler başarısız olabilir.")


# --- SİZİN SAĞLADIĞINIZ app.py DOSYASINDAN ALINAN TAM VE DOĞRU VAVOORESOLVER ---
class VavooResolver:
    def __init__(self):
        self.session = requests.Session()
        self.session.proxies = proxies  # Proxy ayarını session'a uygula
        self.session.headers.update({'User-Agent': 'MediaHubMX/2'})
        self.auth_cache = TTLCache(maxsize=1, ttl=3600)  # İmzayı 1 saat cache'le

    def getAuthSignature(self):
        """Sizin sağladığınız tam app.py dosyasındaki doğru kimlik doğrulama fonksiyonu."""
        if "auth_sig" in self.auth_cache:
            print("Vavoo Signature CACHE HIT")
            return self.auth_cache["auth_sig"]

        print("Fetching new Vavoo signature with full payload...")
        headers = {
            "user-agent": "okhttp/4.11.0", "accept": "application/json",
            "content-type": "application/json; charset=utf-8"
        }
        # Bu, Vavoo'nun beklediği tam ve doğru data bloğudur.
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
            # Dış istek proxy üzerinden yapılır.
            resp = self.session.post("https://www.vavoo.tv/api/app/ping", json=data, headers=headers, timeout=30)
            resp.raise_for_status()
            addon_sig = resp.json().get("addonSig")
            if addon_sig:
                print("New Vavoo signature fetched successfully.")
                self.auth_cache["auth_sig"] = addon_sig
                return addon_sig
            print(f"Error: 'addonSig' not found in Vavoo response. Response: {resp.text}")
            return None
        except Exception as e:
            print(f"FATAL EXCEPTION while fetching Vavoo signature: {e}")
            return None

    def resolve_vavoo_link(self, link):
        """Sizin sağladığınız tam app.py dosyasındaki doğru çözümleme fonksiyonu."""
        signature = self.getAuthSignature()
        if not signature:
            print("Failed to get Vavoo signature, aborting resolution.")
            return None
            
        headers = {
            "user-agent": "MediaHubMX/2", "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "mediahubmx-signature": signature
        }
        data = {"language": "de", "url": link, "clientVersion": "3.0.2"}
        
        try:
            # Dış istek proxy üzerinden yapılır.
            resp = self.session.post("https://vavoo.to/mediahubmx-resolve.json", json=data, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, list) and result and result[0].get("url"):
                resolved_url = result[0]["url"]
                print(f"Vavoo link resolved successfully: {resolved_url}")
                return resolved_url
            print(f"Failed to extract URL from Vavoo resolve response. Response: {result}")
            return None
        except Exception as e:
            print(f"FATAL EXCEPTION during Vavoo resolution: {e}")
            return None

# --- Flask Uygulaması ve Yolları (Routes) ---
app = Flask(__name__)
vavoo_resolver = VavooResolver()
# Dışarıya yapılacak tüm istekler için proxy'li bir session
http_session = requests.Session()
http_session.proxies = proxies

@app.route('/<path:full_path>')
def m3u8_handler(full_path):
    original_url_path = unquote(full_path)
    if not original_url_path.endswith('.m3u8'):
        return "Hata: URL '.m3u8' ile bitmelidir.", 400

    target_url = "https://" + original_url_path.removesuffix('.m3u8')
    print(f"STEP 1: Resolving URL: {target_url}")
    resolved_m3u8_url = vavoo_resolver.resolve_vavoo_link(target_url)

    if not resolved_m3u8_url:
        return "Hata: Vavoo linki çözümlenemedi veya imza alınamadı. Render loglarını kontrol edin.", 500

    print(f"STEP 2: Fetching M3U8 content from: {resolved_m3u8_url}")
    try:
        m3u8_response = http_session.get(resolved_m3u8_url, timeout=20)
        m3u8_response.raise_for_status()
        base_url = urljoin(resolved_m3u8_url, '.')
        rewritten_content = []
        for line in m3u8_response.text.splitlines():
            line = line.strip()
            if line.startswith('#EXT-X-KEY'):
                try:
                    uri_part = line.split('URI="')[1].split('"')[0]
                    # Anahtar URL'sini de proxy üzerinden geçecek şekilde yeniden yaz
                    new_uri = f"/key/{quote(urljoin(base_url, uri_part))}"
                    line = line.replace(uri_part, new_uri)
                except IndexError:
                    pass
            elif line and not line.startswith('#'):
                # Video segment URL'sini proxy üzerinden geçecek şekilde yeniden yaz
                line = f"/ts/{quote(urljoin(base_url, line))}"
            rewritten_content.append(line)
        
        final_content = "\n".join(rewritten_content)
        return Response(final_content, mimetype='application/vnd.apple.mpegurl')
    except Exception as e:
        print(f"EXCEPTION while fetching/rewriting M3U8: {e}")
        return f"Hata: M3U8 içeriği alınamadı veya işlenemedi. {e}", 500

@app.route('/ts/<path:ts_url>')
def ts_proxy(ts_url):
    decoded_url = unquote(ts_url)
    try:
        req = http_session.get(decoded_url, stream=True, timeout=30)
        return Response(stream_with_context(req.iter_content(chunk_size=8192)), content_type=req.headers['content-type'])
    except Exception:
        return "TS segment error", 500

@app.route('/key/<path:key_url>')
def key_proxy(key_url):
    decoded_url = unquote(key_url)
    try:
        req = http_session.get(decoded_url, timeout=20)
        return Response(req.content, content_type=req.headers.get('content-type', 'application/octet-stream'))
    except Exception:
        return "Key error", 500

@app.route('/')
def index():
    return "<h1>Nihai Vavoo Proxy (Doğru Kimlik Doğrulama ile)</h1>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
