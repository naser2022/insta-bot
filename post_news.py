"""
Daily IT News → Farsi → Instagram
"""

import os
import sys
import base64
import textwrap
import time
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from deep_translator import GoogleTranslator

NEWS_API_KEY    = os.environ["NEWS_API_KEY"]
IG_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_ACCOUNT_ID   = os.environ["INSTAGRAM_ACCOUNT_ID"]
IMGBB_API_KEY   = os.environ["IMGBB_API_KEY"]

FONT_BOLD    = "fonts/Vazirmatn-Bold.ttf"
FONT_REGULAR = "fonts/Vazirmatn-Regular.ttf"
IMAGE_OUT    = "post.jpg"


def fetch_it_news():
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={
            "category": "technology",
            "language": "en",
            "pageSize": 10,
            "apiKey": NEWS_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    for a in articles:
        if a.get("title") and a.get("description") and "[Removed]" not in a["title"]:
            return a
    return None


def to_farsi(text, max_chars=500):
    try:
        result = GoogleTranslator(source="en", target="fa").translate(text[:max_chars])
        return result or text
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def rtl(text):
    return get_display(arabic_reshaper.reshape(text))


def create_post_image(title_fa, desc_fa, source):
    W, H = 1080, 1080

    ACCENT  = "#00e5ff"
    ACCENT2 = "#7c3aed"
    WHITE   = "#ffffff"
    MUTED   = "#8899bb"

    img  = Image.new("RGB", (W, H), "#060818")
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        r = int(6  + t * (14 - 6))
        g = int(8  + t * (26 - 8))
        b = int(24 + t * (53 - 24))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    draw.ellipse([700, -180, 1260, 380], fill="#0b1f4a")
    draw.ellipse([730, -150, 1230, 350], fill="#0d2255")
    draw.rectangle([0,   0, W,  6], fill=ACCENT)
    draw.rectangle([0, H-6, W,  H], fill=ACCENT2)

    def load_font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    f_brand  = load_font(FONT_BOLD,    36)
    f_title  = load_font(FONT_BOLD,    58)
    f_desc   = load_font(FONT_REGULAR, 34)
    f_meta   = load_font(FONT_REGULAR, 26)

    brand_text = rtl("📡  اخبار فناوری روز")
    draw.text((W // 2, 72), brand_text, font=f_brand, fill=ACCENT, anchor="mm")
    draw.rectangle([100, 108, W - 100, 111], fill=ACCENT)

    # Fix: wrap first, then apply RTL line by line
    title_lines = textwrap.wrap(title_fa, width=16)
    title_wrap  = "\n".join([rtl(line) for line in title_lines])
    draw.text(
        (W // 2, 310),
        title_wrap,
        font=f_title,
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=18,
    )

    for i, x in enumerate(range(440, 660, 30)):
        color = ACCENT if i % 2 == 0 else ACCENT2
        draw.ellipse([x, 510, x + 10, 520], fill=color)

    desc_short  = desc_fa[:280] + ("..." if len(desc_fa) > 280 else "")
    desc_lines  = textwrap.wrap(desc_short, width=26)
    desc_wrap   = "\n".join([rtl(line) for line in desc_lines])
    draw.text(
        (W // 2, 680),
        desc_wrap,
        font=f_desc,
        fill=MUTED,
        anchor="mm",
        align="center",
        spacing=12,
    )

    draw.rectangle([80, 890, W - 80, 892], fill="#1a2d55")
    date_str  = datetime.now().strftime("%d %b %Y")
    meta_text = f"📰  {source}   ·   {date_str}"
    draw.text((W // 2, 940), meta_text, font=f_meta, fill=ACCENT, anchor="mm")

    hashtags = rtl("#فناوری   #تکنولوژی   #IT   #Tech   #اخبار")
    draw.text((W // 2, 990), hashtags, font=f_meta, fill=ACCENT2, anchor="mm")

    img.save(IMAGE_OUT, quality=95)
    print(f"✅ Image saved → {IMAGE_OUT}")
    return IMAGE_OUT


def upload_image(path):
    with open(path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": img_b64, "expiration": 86400},
        timeout=30,
    )
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"imgbb upload failed: {data}")
    url = data["data"]["url"]
    print(f"✅ Image hosted → {url}")
    return url


def post_to_instagram(image_url, caption):
    base = f"https://graph.instagram.com/v21.0/{IG_ACCOUNT_ID}"

    r1 = requests.post(
        f"{base}/media",
        data={
            "image_url":    image_url,
            "caption":      caption,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    container = r1.json()
    print(f"📦 Container: {container}")
    if "id" not in container:
        raise RuntimeError(f"Media container failed: {container}")

    container_id = container["id"]

    print("⏳ Waiting for Instagram to process image...")
    for attempt in range(10):
        time.sleep(8)
        status_r = requests.get(
            f"https://graph.instagram.com/v21.0/{container_id}",
            params={
                "fields":       "status_code,status",
                "access_token": IG_ACCESS_TOKEN,
            },
            timeout=15,
        )
        status = status_r.json()
        print(f"   Status check {attempt+1}: {status}")
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Media processing error: {status}")
    else:
        raise RuntimeError("Media processing timed out after 80 seconds")

    r2 = requests.post(
        f"{base}/media_publish",
        data={
            "creation_id":  container_id,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    result = r2.json()
    print(f"📤 Publish result: {result}")
    return result


def main():
    print("=" * 55)
    print(f"🕙  {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  |  Bot starting…")
    print("=" * 55)

    article = fetch_it_news()
    if not article:
        print("❌ No suitable article found. Exiting.")
        sys.exit(1)

    title  = article["title"]
    desc   = article.get("description") or title
    source = article.get("source", {}).get("name", "Tech")
    print(f"📰 Article: {title}")

    print("🔄 Translating…")
    title_fa = to_farsi(title)
    desc_fa  = to_farsi(desc)
    print(f"📝 Farsi title: {title_fa}")

    print("🎨 Creating image…")
    create_post_image(title_fa, desc_fa, source)

    print("☁️  Uploading image…")
    image_url = upload_image(IMAGE_OUT)

    caption = (
        f"{title_fa}\n\n"
        f"{desc_fa[:350]}{'…' if len(desc_fa) > 350 else ''}\n\n"
        f"🔗 منبع: {source}\n"
        f"{'─' * 22}\n"
        f"#فناوری #اخبارفناوری #تکنولوژی #هوش_مصنوعی #IT #Tech"
    )

    print("📲 Posting to Instagram…")
    post_to_instagram(image_url, caption)
    print("🎉 Done!")


if __name__ == "__main__":
    main()
