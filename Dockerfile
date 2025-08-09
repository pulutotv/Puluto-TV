# 1. Temiz bir Python 3.12 ortamı kullan
FROM python:3.12-slim

# 2. Çalışma dizinini ayarla
WORKDIR /app

# 3. Gerekli Python kütüphanelerini kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Uygulama kodunu kopyala
COPY app.py .

# 5. Render.com'un dış dünyaya açacağı portu belirt
EXPOSE 10000

# 6. Uygulamayı Gunicorn ile production modunda başlat
# Render, PORT çevre değişkenini otomatik olarak sağlar
CMD ["gunicorn", "--bind", "0.0.0.0:${PORT}", "app:app"]