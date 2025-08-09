import os
from flask import Flask, request, redirect
import requests
from urllib.parse import unquote
from cachetools import TTLCache

# --- Dinamik İmza Alan Gelişmiş VavooResolver Sınıfı ---
class VavooResolver:
    def __init__(self):
        self.session = requests.Session()
        # İmza ve çözümlenmiş linkler için önbellekler
        self.signature_cache = TTLCache(maxsize=1, ttl=3600)  # İmzayı 1 saat önbellekte tut
        self.resolved_link_cache = TTLCache(maxsize=100, ttl=3600) # Çözülmüş linki 1 saat tut

    def get_auth_signature(self):
        """Vavoo'dan dinamik ve geçerli bir imza alır."""
        cached_sig = self.signature_cache.get("auth_sig")
        if cached_sig:
            print("Signature CACHE HIT")
            return cached_sig

        print("Signature CACHE MISS. Fetching new signature from Vavoo...")
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
        }
        # Bu data, orijinal tvproxy kodunuzdan alınmıştır ve geçerli bir imza istemek için gereklidir.
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
            else:
                print("Error: addonSig not found in ping response.")
                return None
        except Exception as e:
            print(f"Exception while fetching signature: {e}")
            return None

    def resolve_vavoo_link(self, link):
        cached_link = self.resolved_link_cache.get(link)
        if cached_link:
            print(f"Resolved link CACHE HIT for: {link}")
            return cached_link

        print(f"Resolving Vavoo link: {link}")
        signature = self.get_auth_signature()
        if not signature:
            print("Error: Could not get auth signature.")
            return None

        headers = {
            "user-agent": "MediaHubMX/2",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "mediahubmx-signature": signature
        }
        data = {"language": "de", "url": link, "clientVersion": "3.0.2"}

        try:
            resp = self.session.post("https://vavoo.to/mediahubmx-resolve.json", json=data, headers=headers, timeout=15)
            resp.raise_for_status()
            result = resp.json()

            resolved_url = None
            if isinstance(result, list) and result and result[0].get("url"):
                resolved_url = result[0]["url"]
            elif isinstance(result, dict) and result.get("url"):
                resolved_url = result["url"]

            if resolved_url:
                print(f"Resolved successfully: {resolved_url}")
                self.resolved_link_cache[link] = resolved_url
                return resolved_url
            else:
                print(f"Failed to resolve. Vavoo response: {result}")
                return None
        except Exception as e:
            print(f"Exception during Vavoo resolution: {e}")
            return None

# --- Flask Uygulaması ---
app = Flask(__name__)
vavoo_resolver = VavooResolver()

@app.route('/<path:full_path>')
def proxy_handler(full_path):
    original_url_path = unquote(full_path)
    if not original_url_path.endswith('.m3u8'):
        return "Hata: URL '.m3u8' ile bitmelidir.", 400

    target_url = "https://" + original_url_path.removesuffix('.m3u8')
    print(f"Processing URL: {target_url}")

    resolved_m3u8_url = vavoo_resolver.resolve_vavoo_link(target_url)

    if resolved_m3u8_url:
        return redirect(resolved_m3u8_url, code=302)
    else:
        return "Hata: Vavoo linki çözümlenemedi veya geçersiz.", 500

@app.route('/')
def index():
    return """
    <h1>M3U8 Docker Proxy (Dinamik İmza)</h1>
    <p>Bu proxy, girilen URL'nin sonuna <b>.m3u8</b> ekleyerek çalışır ve Vavoo'dan dinamik imza alır.</p>
    <p><b>Örnek Kullanım:</b></p>
    <code>https://{sunucu-adresiniz}/vavoo.to/vavoo-iptv/play/31561783590bdea7d4bf69.m3u8</code>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
