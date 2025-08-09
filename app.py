import os
from flask import Flask, request, redirect, Response
import requests
from urllib.parse import unquote
from cachetools import TTLCache

# --- Vavoo linklerini çözmek için gerekli olan sınıf (önceki kodunuzdan alındı) ---
class VavooResolver:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'MediaHubMX/2'})
        # Çözümlenmiş linkler için basit bir önbellek
        self.cache = TTLCache(maxsize=100, ttl=3600)

    def get_auth_signature(self):
        # Bu fonksiyon, normalde dinamik bir imza almalıdır.
        # Kolaylık olması için, genellikle çalışan bir imza kullanıyoruz.
        # Eğer çalışmazsa, bu imzanın güncellenmesi gerekebilir.
        return "2:1722883072:c7XnuFh_e9x0Aog2M2y5Ew:xMhAjhAg4s5I4lkU1T0u02p2FqM"

    def resolve_vavoo_link(self, link):
        cache_key = link
        if cache_key in self.cache:
            print(f"Cache HIT for: {link}")
            return self.cache[cache_key]
        
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
        data = {
            "language": "de",
            "url": link,
            "clientVersion": "3.0.2"
        }
        
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
                self.cache[cache_key] = resolved_url
                return resolved_url
            else:
                print(f"Failed to resolve. Response: {result}")
                return None
                
        except Exception as e:
            print(f"Exception during Vavoo resolution: {e}")
            return None

# --- Flask Uygulaması ---
app = Flask(__name__)
vavoo_resolver = VavooResolver()

@app.route('/<path:full_path>')
def proxy_handler(full_path):
    # Gelen isteğin tam yolunu al (örn: vavoo.to/vavoo-iptv/play/123.m3u8)
    original_url_path = unquote(full_path)

    # Sadece .m3u8 ile biten istekleri işle
    if not original_url_path.endswith('.m3u8'):
        return "Hata: URL '.m3u8' ile bitmelidir.", 400

    # .m3u8 uzantısını kaldır ve https:// ekle
    target_url = "https://" + original_url_path.removesuffix('.m3u8')
    print(f"Processing URL: {target_url}")

    # Vavoo linkini çöz
    resolved_m3u8_url = vavoo_resolver.resolve_vavoo_link(target_url)

    if resolved_m3u8_url:
        # Kullanıcıyı çözümlenmiş M3U8 linkine yönlendir
        return redirect(resolved_m3u8_url, code=302)
    else:
        # Çözümleme başarısız olursa hata döndür
        return "Hata: Vavoo linki çözümlenemedi veya geçersiz.", 500

@app.route('/')
def index():
    return """
    <h1>M3U8 Docker Proxy</h1>
    <p>Bu proxy, girilen URL'nin sonuna <b>.m3u8</b> ekleyerek çalışır.</p>
    <p><b>Örnek Kullanım:</b></p>
    <code>https://{sunucu-adresiniz}/vavoo.to/vavoo-iptv/play/31561783590bdea7d4bf69.m3u8</code>
    """

if __name__ == '__main__':
    # Render.com'un sağladığı PORT değişkenini kullan
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)