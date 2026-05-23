"""
Daily IT News → Farsi → Instagram
Posts 5 tech headlines per day as a single styled image.
"""

import os
import sys
import base64
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


# ── Farsi helpers ─────────────────────────────────────────────────────────────
def rtl(text: str) -> str:
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


def farsi_wrap(text: str, words_per_line: int = 5) -> str:
    """Split Farsi text into lines by word count, apply RTL per line."""
    words = text.split()
    lines = []
    for i in range(0, len(words), words_per_line):
        chunk = " ".join(words[i:i + words_per_line])
        lines.append(rtl(chunk))
    return "\n".join(lines)


# ── 1. Fetch 5 news articles ──────────────────────────────────────────────────
def fetch_it_news(count: int = 5):
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={
            "category": "technology",
            "language": "en",
            "pageSize": 20,
            "apiKey":   NEWS_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    results = []
    for a in articles:
        if a.get("title") and "[Removed]" not in a["title"]:
            results.append(a)
        if len(results) == count:
            break
    return results


# ── 2. Translate ──────────────────────────────────────────────────────────────
def to_farsi(text: str, max_chars: int = 300) -> str:
    try:
        return GoogleTranslator(source="en", target="fa").translate(text[:max_chars]) or text
    except Exception as e:
        print(f"Translation error: {e}")
        return text


# ── 3. Create image with 5 news items ────────────────────────────────────────
def create_post_image(items: list) -> str:
    """
    items: list of dicts with keys 'title_fa', 'source'
    """
    W, H = 1080, 1080

    ACCENT   = "#00e5ff"
    ACCENT2  = "#7c3aed"
    WHITE    = "#ffffff"
    MUTED    = "#a0b4cc"
    CARD_BG  = "#0d1e3a"
    NUM_COL  = ["#00e5ff", "#7c3aed", "#00e5ff", "#7c3aed", "#00e5ff"]

    # Background gradient
    img  = Image.new("RGB", (W, H), "#060818")
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(6  + t * (14 - 6))
        g = int(8  + t * (26 - 8))
        b = int(24 + t * (53 - 24))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Top / bottom accent bars
    draw.rectangle([0,   0, W,  6], fill=ACCENT)
    draw.rectangle([0, H-6, W,  H], fill=ACCENT2)

    # Fonts
    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    f_header = font(FONT_BOLD,    42)
    f_num    = font(FONT_BOLD,    36)
    f_title  = font(FONT_BOLD,    34)
    f_source = font(FONT_REGULAR, 22)
    f_footer = font(FONT_REGULAR, 24)

    # Header
    header = rtl("📡  پنج خبر برتر فناوری امروز")
    draw.text((W // 2, 58), header, font=f_header, fill=ACCENT, anchor="mm")
    draw.rectangle([60, 86, W - 60, 89], fill=ACCENT)

    # News cards
    card_h      = 148
    card_margin = 14
    start_y     = 106

    for idx, item in enumerate(items[:5]):
        x0 = 40
        y0 = start_y + idx * (card_h + card_margin)
        x1 = W - 40
        y1 = y0 + card_h

        # Card background
        draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=CARD_BG)

        # Left accent stripe
        draw.rounded_rectangle([x0, y0, x0 + 8, y1], radius=4, fill=NUM_COL[idx])

        # Number circle
        cx, cy = x0 + 46, y0 + card_h // 2
        draw.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=NUM_COL[idx])
        draw.text((cx, cy), str(idx + 1), font=f_num, fill="#060818", anchor="mm")

        # Farsi headline (right side, RTL)
        text_x = x1 - 20
        title_text = farsi_wrap(item["title_fa"], words_per_line=6)
        draw.text(
            (text_x, y0 + 38),
            title_text,
            font=f_title,
            fill=WHITE,
            anchor="ra",
            align="right",
            spacing=8,
        )

        # Source label
        source_text = rtl(f"📰 {item['source']}")
        draw.text(
            (text_x, y1 - 22),
            source_text,
            font=f_source,
            fill=MUTED,
            anchor="rm",
        )

    # Footer
    date_str = datetime.now().strftime("%d %b %Y")
    draw.text((W // 2, H - 38), f"📅  {date_str}", font=f_footer, fill=ACCENT, anchor="mm")

    img.save(IMAGE_OUT, quality=95)
    print(f"✅ Image saved → {IMAGE_OUT}")
    return IMAGE_OUT


# ── 4. Upload image ───────────────────────────────────────────────────────────
def upload_image(path: str) -> str:
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


# ── 5. Post to Instagram ──────────────────────────────────────────────────────
def post_to_instagram(image_url: str, caption: str):
    base = f"https://graph.instagram.com/v21.0/{IG_ACCOUNT_ID}"

    r1 = requests.post(
        f"{base}/media",
        data={"image_url": image_url, "caption": caption, "access_token": IG_ACCESS_TOKEN},
        timeout=30,
    )
    container = r1.json()
    print(f"📦 Container: {container}")
    if "id" not in container:
        raise RuntimeError(f"Media container failed: {container}")

    container_id = container["id"]
    print("⏳ Waiting for Instagram to process image...")
    for attempt in range(12):
        time.sleep(8)
        status_r = requests.get(
            f"https://graph.instagram.com/v21.0/{container_id}",
            params={"fields": "status_code,status", "access_token": IG_ACCESS_TOKEN},
            timeout=15,
        )
        status = status_r.json()
        print(f"   Status {attempt+1}: {status.get('status_code')}")
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Media error: {status}")
    else:
        raise RuntimeError("Timed out waiting for Instagram")

    r2 = requests.post(
        f"{base}/media_publish",
        data={"creation_id": container_id, "access_token": IG_ACCESS_TOKEN},
        timeout=30,
    )
    result = r2.json()
    print(f"📤 Publish result: {result}")
    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print(f"🕙  {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  |  Bot starting…")
    print("=" * 55)

    print("📰 Fetching 5 articles…")
    articles = fetch_it_news(count=5)
    if not articles:
        print("❌ No articles found.")
        sys.exit(1)

    print("🔄 Translating to Farsi…")
    items = []
    caption_lines = ["🔴 پنج خبر برتر فناوری امروز\n"]
    for i, a in enumerate(articles):
        title_fa = to_farsi(a["title"])
        source   = a.get("source", {}).get("name", "Tech")
        print(f"  {i+1}. {title_fa}")
        items.append({"title_fa": title_fa, "source": source})
        caption_lines.append(f"{i+1}. {title_fa}")

    caption_lines.append("\n──────────────────────")
    caption_lines.append("#فناوری #اخبارفناوری #تکنولوژی #هوش_مصنوعی #IT #Tech")
    caption = "\n".join(caption_lines)

    print("🎨 Creating image…")
    create_post_image(items)

    print("☁️  Uploading image…")
    image_url = upload_image(IMAGE_OUT)

    print("📲 Posting to Instagram…")
    post_to_instagram(image_url, caption)
    print("🎉 Done!")


if __name__ == "__main__":
    main()
