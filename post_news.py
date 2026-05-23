"""
Daily IT News → Farsi → Instagram
Posts 5 tech headlines per day as a single styled image.
"""

import os, sys, base64, time, requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from deep_translator import GoogleTranslator

NEWS_API_KEY    = os.environ["NEWS_API_KEY"]
IG_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_ACCOUNT_ID   = os.environ["INSTAGRAM_ACCOUNT_ID"]
IMGBB_API_KEY   = os.environ["IMGBB_API_KEY"]

FONT_BOLD    = "fonts/Vazirmatn-Bold.ttf"
FONT_REGULAR = "fonts/Vazirmatn-Regular.ttf"
IMAGE_OUT    = "post.jpg"


# ── Farsi helpers ─────────────────────────────────────────────────────────────
def fa(text: str) -> str:
    """Reshape Farsi letters so they connect properly in PIL."""
    return arabic_reshaper.reshape(str(text))


def fa_wrap(text: str, font, draw, max_px: int) -> str:
    """Word-wrap Farsi text to fit within max_px width, measured in pixels."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        w = draw.textlength(fa(test), font=font)
        if w > max_px and current:
            lines.append(fa(" ".join(current)))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(fa(" ".join(current)))
    return "\n".join(lines)


# ── 1. Fetch 5 news ───────────────────────────────────────────────────────────
def fetch_it_news(count=5):
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"category": "technology", "language": "en",
                "pageSize": 20, "apiKey": NEWS_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for a in resp.json().get("articles", []):
        if a.get("title") and "[Removed]" not in a["title"]:
            results.append(a)
        if len(results) == count:
            break
    return results


# ── 2. Translate ──────────────────────────────────────────────────────────────
def to_farsi(text: str, max_chars=300) -> str:
    try:
        return GoogleTranslator(source="en", target="fa").translate(text[:max_chars]) or text
    except Exception as e:
        print(f"Translation error: {e}")
        return text


# ── 3. Create image ───────────────────────────────────────────────────────────
def create_post_image(items: list) -> str:
    W, H = 1080, 1080
    ACCENT  = "#00e5ff"
    ACCENT2 = "#7c3aed"
    WHITE   = "#ffffff"
    MUTED   = "#a0b4cc"
    CARD_BG = "#0d1e3a"
    NUMS    = ["#00e5ff", "#7c3aed", "#00e5ff", "#7c3aed", "#00e5ff"]

    img  = Image.new("RGB", (W, H), "#060818")
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=(
            int(6  + t * 8),
            int(8  + t * 18),
            int(24 + t * 29),
        ))

    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    draw.rectangle([0, H-6, W, H], fill=ACCENT2)

    def font(path, size):
        try:    return ImageFont.truetype(path, size)
        except: return ImageFont.load_default()

    f_hdr  = font(FONT_BOLD,    40)
    f_num  = font(FONT_BOLD,    32)
    f_title= font(FONT_BOLD,    32)
    f_src  = font(FONT_REGULAR, 20)
    f_foot = font(FONT_REGULAR, 22)

    # Header
    hdr = fa("📡  پنج خبر برتر فناوری امروز")
    draw.text((W//2, 56), hdr, font=f_hdr, fill=ACCENT, anchor="mm")
    draw.rectangle([60, 84, W-60, 87], fill=ACCENT)

    # Cards
    card_h = 150
    gap    = 10
    y0_start = 100
    text_max_px = W - 160  # card width minus number circle and padding

    for i, item in enumerate(items[:5]):
        x0 = 40
        y0 = y0_start + i * (card_h + gap)
        x1 = W - 40
        y1 = y0 + card_h

        draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=CARD_BG)
        draw.rounded_rectangle([x0, y0, x0+8, y1], radius=4, fill=NUMS[i])

        # Number circle
        cx, cy = x0 + 44, y0 + card_h // 2
        draw.ellipse([cx-20, cy-20, cx+20, cy+20], fill=NUMS[i])
        draw.text((cx, cy), str(i+1), font=f_num, fill="#060818", anchor="mm")

        # Farsi title — pixel-wrapped, right-aligned
        title_wrapped = fa_wrap(item["title_fa"], f_title, draw, text_max_px)
        draw.text(
            (x1 - 18, y0 + 30),
            title_wrapped,
            font=f_title, fill=WHITE,
            anchor="ra", align="right", spacing=6,
        )

        # Source
        draw.text(
            (x1 - 18, y1 - 18),
            item["source"],
            font=f_src, fill=MUTED, anchor="rm",
        )

    # Footer date
    date_str = datetime.now().strftime("%d %b %Y")
    draw.text((W//2, H-32), f"📅  {date_str}", font=f_foot, fill=ACCENT, anchor="mm")

    img.save(IMAGE_OUT, quality=95)
    print(f"✅ Image saved → {IMAGE_OUT}")
    return IMAGE_OUT


# ── 4. Upload image ───────────────────────────────────────────────────────────
def upload_image(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": b64, "expiration": 86400},
        timeout=30,
    )
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"imgbb failed: {data}")
    url = data["data"]["url"]
    print(f"✅ Hosted → {url}")
    return url


# ── 5. Post to Instagram ──────────────────────────────────────────────────────
def post_to_instagram(image_url: str, caption: str):
    base = f"https://graph.instagram.com/v21.0/{IG_ACCOUNT_ID}"

    r1 = requests.post(f"{base}/media", data={
        "image_url": image_url, "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }, timeout=30)
    container = r1.json()
    print(f"📦 Container: {container}")
    if "id" not in container:
        raise RuntimeError(f"Container failed: {container}")

    cid = container["id"]
    print("⏳ Waiting for processing…")
    for attempt in range(12):
        time.sleep(8)
        s = requests.get(
            f"https://graph.instagram.com/v21.0/{cid}",
            params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN},
            timeout=15,
        ).json()
        print(f"   [{attempt+1}] {s.get('status_code')}")
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Processing error: {s}")

    r2 = requests.post(f"{base}/media_publish", data={
        "creation_id": cid, "access_token": IG_ACCESS_TOKEN,
    }, timeout=30)
    result = r2.json()
    print(f"📤 Result: {result}")
    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("="*55)
    print(f"🕙  {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  |  Starting…")
    print("="*55)

    articles = fetch_it_news(5)
    if not articles:
        print("❌ No articles."); sys.exit(1)

    items, caption_lines = [], ["🔴 پنج خبر برتر فناوری امروز\n"]
    for i, a in enumerate(articles):
        title_fa = to_farsi(a["title"])
        source   = a.get("source", {}).get("name", "Tech")
        print(f"  {i+1}. {title_fa}")
        items.append({"title_fa": title_fa, "source": source})
        caption_lines.append(f"{i+1}. {title_fa}")

    caption_lines += ["\n──────────────────────",
                      "#فناوری #اخبارفناوری #تکنولوژی #هوش_مصنوعی #IT #Tech"]
    caption = "\n".join(caption_lines)

    create_post_image(items)
    image_url = upload_image(IMAGE_OUT)
    post_to_instagram(image_url, caption)
    print("🎉 Done!")


if __name__ == "__main__":
    main()
