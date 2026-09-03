"""
Daily IT News -> Persian editorial rewrite -> Instagram
Posts 5 technology news items per day as one RTL Persian image.

V1:
- Natural Persian editorial writing instead of machine translation.
- Neutral tone and strict source fidelity.
- Proper Persian RTL/BiDi rendering on the image and caption.
- More readable editorial card design.
"""

import os
import sys
import base64
import json
import re
import time
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
IG_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_ACCOUNT_ID = os.environ["INSTAGRAM_ACCOUNT_ID"]
IMGBB_API_KEY = os.environ["IMGBB_API_KEY"]

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
FONT_BOLD = "fonts/Vazirmatn-Bold.ttf"
FONT_REGULAR = "fonts/Vazirmatn-Regular.ttf"
IMAGE_OUT = "post.jpg"
RLM = "\u200f"
LRM = "\u200e"


# -----------------------------------------------------------------------------
# Persian RTL helpers
# -----------------------------------------------------------------------------
def fa_display(text: str) -> str:
    """Convert logical Persian text to a PIL-ready visual RTL string."""
    text = str(text or "")
    return get_display(arabic_reshaper.reshape(text))


def fa_digits(text: str) -> str:
    """Convert Western digits to Persian digits for Persian-facing text."""
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def fa_wrap(text: str, font, draw, max_px: int, max_lines: int = 3) -> str:
    """Wrap logical Persian text by pixel width, then apply BiDi per line."""
    words = str(text or "").split()
    if not words:
        return ""

    lines = []
    current = []

    for word in words:
        candidate = " ".join(current + [word])
        width = draw.textlength(fa_display(candidate), font=font)
        if width > max_px and current:
            lines.append(fa_display(" ".join(current)))
            current = [word]
        else:
            current.append(word)

    if current:
        lines.append(fa_display(" ".join(current)))

    if len(lines) <= max_lines:
        return "\n".join(lines)

    kept = lines[:max_lines]
    last = kept[-1]
    while last and draw.textlength(last + "…", font=font) > max_px:
        last = last[:-1]
    kept[-1] = last.rstrip() + "…"
    return "\n".join(kept)


def safe_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        print(f"WARNING: Font not found: {path}")
        return ImageFont.load_default()


# -----------------------------------------------------------------------------
# 1. Fetch technology news
# -----------------------------------------------------------------------------
def fetch_it_news(count=5):
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={
            "category": "technology",
            "language": "en",
            "pageSize": 20,
            "apiKey": NEWS_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()

    results = []
    for article in resp.json().get("articles", []):
        title = (article.get("title") or "").strip()
        if not title or "[Removed]" in title:
            continue
        results.append(article)
        if len(results) == count:
            break
    return results


# -----------------------------------------------------------------------------
# 2. AI Persian news editor
# -----------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    """Parse JSON returned by the model, including a possible code fence."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def edit_news_in_farsi(article: dict) -> dict:
    """Create a natural, neutral Persian news item from source material."""
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    content = (article.get("content") or "").strip()
    source = (article.get("source", {}).get("name") or "Tech").strip()

    source_material = "\n".join(
        part
        for part in [
            f"Source: {source}",
            f"Title: {title}",
            f"Description: {description}",
            f"Available content: {content}",
        ]
        if part.split(": ", 1)[-1].strip()
    )

    prompt = f"""
You are the Persian technology news editor for a professional Instagram news account.

Your task is NOT literal translation. First understand the English source, then
write a natural Persian news report as a human editor would write it.

STRICT EDITORIAL RULES:
- All Persian output must be natural Persian and intended to be read RIGHT TO LEFT.
- Do not translate sentence by sentence.
- Use clear, modern, professional Persian.
- Be neutral, factual and concise.
- Do not praise, criticize, speculate, sensationalize or advertise.
- Do not invent facts, context, causes, dates, numbers or conclusions.
- Use only information supported by the supplied source material.
- Preserve company names, product names, game names, model names, dates and numbers.
- Keep important technical names in Latin script when that is clearer.
- Distinguish clearly between confirmed facts and plans, expectations or claims.
- If the source gives little information, write a shorter report. Do not fill gaps.
- Do not use emojis in title, summary or report.
- Avoid machine-translation wording and English sentence structure.

Create exactly these four fields:
1. category: one of AI, Software, Hardware, Cybersecurity, Gaming, Internet, Other
2. title_fa: one natural Persian headline, about 8-18 words
3. summary_fa: 2-3 natural Persian sentences, about 35-60 words
4. caption_fa: a more detailed but factual Persian report, about 70-120 words

Return ONLY valid JSON. Do not use Markdown and do not add commentary.

SOURCE MATERIAL:
{source_material[:7000]}
""".strip()

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "input": prompt,
            "max_output_tokens": 900,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    output_text = data.get("output_text", "").strip()
    if not output_text:
        chunks = []
        for item in data.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text" and part.get("text"):
                    chunks.append(part["text"])
        output_text = "".join(chunks).strip()

    result = extract_json(output_text)
    required = ["category", "title_fa", "summary_fa", "caption_fa"]
    if any(not str(result.get(key, "")).strip() for key in required):
        raise RuntimeError(f"AI returned incomplete news item: {result}")

    return {
        "category": str(result["category"]).strip(),
        "title_fa": str(result["title_fa"]).strip(),
        "summary_fa": str(result["summary_fa"]).strip(),
        "caption_fa": str(result["caption_fa"]).strip(),
        "source": source,
    }


# -----------------------------------------------------------------------------
# 3. Create the Instagram image
# -----------------------------------------------------------------------------
def create_post_image(items: list) -> str:
    W, H = 1080, 1080

    bg_top = (5, 9, 20)
    bg_bottom = (10, 19, 35)
    card_bg = (14, 24, 42)
    card_edge = (30, 47, 70)
    white = "#f8fafc"
    muted = "#94a3b8"
    accent = "#22d3ee"
    purple = "#8b5cf6"

    category_colors = {
        "AI": accent,
        "Software": "#60a5fa",
        "Hardware": "#34d399",
        "Cybersecurity": "#fb7185",
        "Gaming": "#c084fc",
        "Internet": "#38bdf8",
        "Other": muted,
    }

    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / (H - 1)
        color = tuple(int(bg_top[i] + (bg_bottom[i] - bg_top[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=color)

    draw.rectangle([0, 0, W, 5], fill=accent)
    draw.rectangle([0, H - 5, W, H], fill=purple)

    f_brand = safe_font(FONT_BOLD, 28)
    f_date = safe_font(FONT_REGULAR, 19)
    f_header = safe_font(FONT_BOLD, 42)
    f_num = safe_font(FONT_BOLD, 25)
    f_cat = safe_font(FONT_BOLD, 17)
    f_title = safe_font(FONT_BOLD, 28)
    f_summary = safe_font(FONT_REGULAR, 19)
    f_source = safe_font(FONT_REGULAR, 16)

    draw.text((55, 42), "TECH DAILY", font=f_brand, fill=accent, anchor="lm")

    persian_months = {
        1: "ژانویه", 2: "فوریه", 3: "مارس", 4: "آوریل", 5: "مه", 6: "ژوئن",
        7: "ژوئیه", 8: "اوت", 9: "سپتامبر", 10: "اکتبر", 11: "نوامبر", 12: "دسامبر",
    }
    now = datetime.now()
    date_label = f"{fa_display(fa_digits(str(now.day)))} {fa_display(persian_months[now.month])} {fa_display(fa_digits(str(now.year)))}"
    draw.text((W - 55, 42), date_label, font=f_date, fill=muted, anchor="rm")

    header = fa_display("پنج خبر برتر فناوری امروز")
    draw.text((W - 55, 92), header, font=f_header, fill=white, anchor="ra")
    draw.line([(55, 125), (W - 55, 125)], fill=(37, 55, 78), width=2)

    card_x0, card_x1 = 45, W - 45
    card_h, gap = 166, 8
    y_start = 143
    text_right = card_x1 - 30
    text_width = 760

    for i, item in enumerate(items[:5]):
        y0 = y_start + i * (card_h + gap)
        y1 = y0 + card_h
        category = item.get("category", "Other")
        card_accent = category_colors.get(category, accent)

        draw.rounded_rectangle(
            [card_x0, y0, card_x1, y1],
            radius=16,
            fill=card_bg,
            outline=card_edge,
            width=1,
        )

        # Left editorial index area.
        index_x = card_x0 + 46
        draw.text((index_x, y0 + 30), fa_digits(f"{i + 1:02d}"), font=f_num, fill=card_accent, anchor="mm")
        draw.line([(index_x - 16, y0 + 58), (index_x + 16, y0 + 58)], fill=card_accent, width=2)
        draw.text((index_x, y0 + 88), category.upper(), font=f_cat, fill=card_accent, anchor="mm")

        title = fa_wrap(item["title_fa"], f_title, draw, text_width, max_lines=2)
        draw.multiline_text(
            (text_right, y0 + 22),
            title,
            font=f_title,
            fill=white,
            anchor="ra",
            align="right",
            spacing=5,
        )

        summary = fa_wrap(item["summary_fa"], f_summary, draw, text_width, max_lines=2)
        draw.multiline_text(
            (text_right, y0 + 91),
            summary,
            font=f_summary,
            fill=muted,
            anchor="ra",
            align="right",
            spacing=4,
        )

        source_text = f"SOURCE · {item['source']}"
        draw.text((text_right, y1 - 14), source_text, font=f_source, fill=(113, 132, 154), anchor="ra")

    footer = fa_display("خبرهای فناوری، کوتاه و بی‌طرفانه")
    draw.text((W - 55, H - 22), footer, font=f_source, fill=muted, anchor="rs")

    img.save(IMAGE_OUT, quality=95, optimize=True)
    print(f"OK: Image saved -> {IMAGE_OUT}")
    return IMAGE_OUT


# -----------------------------------------------------------------------------
# 4. Upload image
# -----------------------------------------------------------------------------
def upload_image(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": b64, "expiration": 86400},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"imgbb failed: {data}")

    url = data["data"]["url"]
    print(f"OK: Hosted -> {url}")
    return url


# -----------------------------------------------------------------------------
# 5. Instagram caption
# -----------------------------------------------------------------------------
def build_caption(items: list) -> str:
    lines = [f"{RLM}🔴 پنج خبر مهم فناوری امروز", ""]

    for i, item in enumerate(items[:5], start=1):
        lines.append(f"{RLM}{fa_digits(str(i)).zfill(2)}. {item['caption_fa']}")
        lines.append(f"{RLM}منبع: {LRM}{item['source']}{LRM}")
        lines.append("")

    lines.extend([
        f"{RLM}──────────────────────",
        f"{RLM}این پست با هدف ارائه خلاصه‌ای کوتاه و بی‌طرفانه از اخبار فناوری تهیه شده است.",
        "",
        f"{RLM}#فناوری #اخبارفناوری #تکنولوژی #هوش_مصنوعی #امنیت_سایبری #AI #Tech #IT",
    ])
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# 6. Post to Instagram
# -----------------------------------------------------------------------------
def post_to_instagram(image_url: str, caption: str):
    base = f"https://graph.instagram.com/v21.0/{IG_ACCOUNT_ID}"

    r1 = requests.post(
        f"{base}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    r1.raise_for_status()
    container = r1.json()
    print(f"Container: {container}")
    if "id" not in container:
        raise RuntimeError(f"Container failed: {container}")

    cid = container["id"]
    print("Waiting for Instagram processing...")
    finished = False
    for attempt in range(12):
        time.sleep(8)
        status_response = requests.get(
            f"https://graph.instagram.com/v21.0/{cid}",
            params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN},
            timeout=15,
        )
        status_response.raise_for_status()
        status = status_response.json()
        print(f"  [{attempt + 1}] {status.get('status_code')}")
        if status.get("status_code") == "FINISHED":
            finished = True
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Processing error: {status}")

    if not finished:
        raise RuntimeError("Instagram media container did not finish processing in time")

    r2 = requests.post(
        f"{base}/media_publish",
        data={"creation_id": cid, "access_token": IG_ACCESS_TOKEN},
        timeout=30,
    )
    r2.raise_for_status()
    result = r2.json()
    print(f"Publish result: {result}")
    return result


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    print("=" * 60)
    print(f"Starting: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 60)

    articles = fetch_it_news(5)
    if not articles:
        print("ERROR: No articles found.")
        sys.exit(1)

    print(f"Found {len(articles)} technology articles")
    print(f"Writing natural Persian news with {OPENAI_MODEL}...")

    items = []
    for i, article in enumerate(articles, start=1):
        item = edit_news_in_farsi(article)
        items.append(item)
        print(f"  {i}. [{item['category']}] {item['title_fa']}")

    if len(items) != 5:
        raise RuntimeError(f"Expected 5 news items, got {len(items)}")

    print("Creating RTL Persian image...")
    create_post_image(items)

    caption = build_caption(items)

    print("Uploading image...")
    image_url = upload_image(IMAGE_OUT)

    print("Posting to Instagram...")
    post_to_instagram(image_url, caption)
    print("Done!")


if __name__ == "__main__":
    main()
