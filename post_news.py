"""
Daily IT News -> Persian editorial rewrite -> Instagram.
V2: correct Persian RTL/BiDi rendering and cleaner Persian typography.
"""

import os
import sys
import base64
import json
import re
import time
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, features
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
INSTAGRAM_CAPTION_LIMIT = 2200
USE_RAQM = features.check("raqm")


def fa_digits(text: str) -> str:
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def fa_display(text: str) -> str:
    """Prepare Persian text for PIL only when libraqm is unavailable."""
    text = str(text or "")
    if USE_RAQM:
        return text
    return get_display(arabic_reshaper.reshape(text))


def fa_textlength(draw, text: str, font) -> float:
    if USE_RAQM:
        return draw.textlength(text, font=font, direction="rtl", language="fa")
    return draw.textlength(fa_display(text), font=font)


def fa_draw(draw, xy, text: str, font, fill, anchor="ra", spacing=4):
    """Draw logical Persian text. Pillow/RAQM performs the BiDi layout."""
    kwargs = {
        "font": font,
        "fill": fill,
        "anchor": anchor,
        "align": "right",
        "spacing": spacing,
    }
    if USE_RAQM:
        kwargs.update(direction="rtl", language="fa")
        return draw.multiline_text(xy, str(text or ""), **kwargs)
    return draw.multiline_text(xy, fa_display(text), **kwargs)


def fa_wrap(text: str, font, draw, max_px: int, max_lines: int = 3) -> str:
    """Wrap logical Persian text. Never reverse the logical string."""
    words = str(text or "").split()
    if not words:
        return ""
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        if fa_textlength(draw, candidate, font) > max_px and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    if len(lines) <= max_lines:
        return "\n".join(lines)
    kept = lines[:max_lines]
    last = kept[-1]
    while last and fa_textlength(draw, last + "…", font) > max_px:
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
# News
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
# AI Persian editor
# -----------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


def edit_news_in_farsi(article: dict) -> dict:
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    content = (article.get("content") or "").strip()
    source = (article.get("source", {}).get("name") or "Tech").strip()

    source_material = "\n".join(
        part for part in [
            f"Source: {source}",
            f"Title: {title}",
            f"Description: {description}",
            f"Available content: {content}",
        ]
        if part.split(": ", 1)[-1].strip()
    )

    prompt = f"""
You are a professional Persian technology news editor.

Understand the English source first. Then write a natural Persian news report.
Do NOT translate word by word or sentence by sentence.

RULES:
- Persian is written RIGHT TO LEFT.
- Use modern, natural Persian used by a professional technology newsroom.
- The headline must sound like a real Persian news headline.
- The summary must explain what happened, who/what is involved, and the key
  detail that is supported by the source.
- The Instagram report may be more detailed, but it must stay factual.
- Neutral tone. No hype, praise, criticism, clickbait or advertising.
- Never invent facts, reasons, dates, prices, specifications or conclusions.
- Do not turn a possibility, plan, claim or expectation into a confirmed fact.
- Keep product, company, game and technical names accurate. Keep Latin names
  when that is clearer than a Persian transliteration.
- Use Persian grammar and natural sentence order.
- Do not use emojis in title, summary or report.
- Avoid machine-translation phrases and awkward literal translations.

Return ONLY valid JSON with exactly these keys:
{{
  "category": "AI | Software | Hardware | Cybersecurity | Gaming | Internet | Other",
  "title_fa": "natural Persian headline, 8-16 words",
  "summary_fa": "2 natural Persian sentences, about 30-50 words",
  "caption_fa": "natural Persian Instagram report, about 45-65 words"
}}

The five reports together must fit Instagram's 2200-character caption limit.

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
# Image
# -----------------------------------------------------------------------------
def create_post_image(items: list) -> str:
    W, H = 1080, 1080
    bg_top, bg_bottom = (5, 9, 20), (10, 19, 35)
    card_bg, card_edge = (14, 24, 42), (30, 47, 70)
    white, muted = "#f8fafc", "#94a3b8"
    accent, purple = "#22d3ee", "#8b5cf6"

    category_colors = {
        "AI": accent, "Software": "#60a5fa", "Hardware": "#34d399",
        "Cybersecurity": "#fb7185", "Gaming": "#c084fc",
        "Internet": "#38bdf8", "Other": muted,
    }

    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(bg_top[i] + (bg_bottom[i] - bg_top[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=c)

    draw.rectangle([0, 0, W, 5], fill=accent)
    draw.rectangle([0, H - 5, W, H], fill=purple)

    f_brand = safe_font(FONT_BOLD, 28)
    f_date = safe_font(FONT_REGULAR, 19)
    f_header = safe_font(FONT_BOLD, 38)
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
    date_label = f"{fa_digits(str(now.day))} {persian_months[now.month]} {fa_digits(str(now.year))}"
    fa_draw(draw, (W - 55, 42), date_label, f_date, muted, anchor="rm")

    # Keep the headline clearly separated from the divider below it.
    fa_draw(draw, (W - 55, 88), "پنج خبر برتر فناوری امروز", f_header, white, anchor="ra")
    draw.line([(55, 124), (W - 55, 124)], fill=(37, 55, 78), width=2)

    card_x0, card_x1 = 45, W - 45
    card_h, gap = 166, 8
    y_start = 143
    text_right, text_width = card_x1 - 30, 760

    for i, item in enumerate(items[:5]):
        y0, y1 = y_start + i * (card_h + gap), y_start + i * (card_h + gap) + card_h
        category = item.get("category", "Other")
        card_accent = category_colors.get(category, accent)

        draw.rounded_rectangle([card_x0, y0, card_x1, y1], radius=16, fill=card_bg, outline=card_edge, width=1)

        index_x = card_x0 + 46
        draw.text((index_x, y0 + 30), fa_digits(f"{i + 1:02d}"), font=f_num, fill=card_accent, anchor="mm")
        draw.line([(index_x - 16, y0 + 58), (index_x + 16, y0 + 58)], fill=card_accent, width=2)
        draw.text((index_x, y0 + 88), category.upper(), font=f_cat, fill=card_accent, anchor="mm")

        title = fa_wrap(item["title_fa"], f_title, draw, text_width, 2)
        fa_draw(draw, (text_right, y0 + 22), title, f_title, white, anchor="ra", spacing=5)

        summary = fa_wrap(item["summary_fa"], f_summary, draw, text_width, 2)
        fa_draw(draw, (text_right, y0 + 91), summary, f_summary, muted, anchor="ra", spacing=4)

        draw.text((text_right, y1 - 14), f"SOURCE · {item['source']}", font=f_source, fill=(113, 132, 154), anchor="ra")

    fa_draw(draw, (W - 55, H - 22), "خبرهای فناوری، کوتاه و بی‌طرفانه", f_source, muted, anchor="rs")

    img.save(IMAGE_OUT, quality=95, optimize=True)
    print(f"OK: Image saved -> {IMAGE_OUT}")
    return IMAGE_OUT


# -----------------------------------------------------------------------------
# Upload and Instagram
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


def build_caption(items: list) -> str:
    lines = [f"{RLM}🔴 پنج خبر مهم فناوری امروز", ""]
    for i, item in enumerate(items[:5], start=1):
        lines.append(f"{RLM}{fa_digits(str(i))}. {item['caption_fa']}")
        lines.append(f"{RLM}منبع: {LRM}{item['source']}{LRM}")
        lines.append("")
    lines += [
        f"{RLM}──────────────────────",
        f"{RLM}خلاصه‌ای کوتاه و بی‌طرفانه از اخبار فناوری.",
        "",
        f"{RLM}#فناوری #اخبارفناوری #تکنولوژی #هوش_مصنوعی #امنیت_سایبری #AI #Tech #IT",
    ]
    caption = "\n".join(lines)
    print(f"Instagram caption length: {len(caption)} characters")

    if len(caption) <= INSTAGRAM_CAPTION_LIMIT:
        return caption

    print("WARNING: Caption over limit; using summaries.")
    lines = [f"{RLM}🔴 پنج خبر مهم فناوری امروز", ""]
    for i, item in enumerate(items[:5], start=1):
        lines.append(f"{RLM}{fa_digits(str(i))}. {item['title_fa']} — {item['summary_fa']}")
        lines.append(f"{RLM}منبع: {LRM}{item['source']}{LRM}")
        lines.append("")
    lines.append(f"{RLM}#فناوری #اخبارفناوری #تکنولوژی #هوش_مصنوعی #AI #Tech #IT")
    caption = "\n".join(lines)

    if len(caption) <= INSTAGRAM_CAPTION_LIMIT:
        print(f"Instagram fallback caption length: {len(caption)} characters")
        return caption

    while len(caption) > INSTAGRAM_CAPTION_LIMIT and "\n\n" in caption:
        caption = caption.rsplit("\n\n", 1)[0]
    return caption[:INSTAGRAM_CAPTION_LIMIT]


def post_to_instagram(image_url: str, caption: str):
    base = f"https://graph.instagram.com/v21.0/{IG_ACCOUNT_ID}"
    r1 = requests.post(
        f"{base}/media",
        data={"image_url": image_url, "caption": caption, "access_token": IG_ACCESS_TOKEN},
        timeout=30,
    )
    if not r1.ok:
        print(f"Instagram /media failed ({r1.status_code}): {r1.text}")
    r1.raise_for_status()
    container = r1.json()
    print(f"Container: {container}")
    if "id" not in container:
        raise RuntimeError(f"Container failed: {container}")

    cid = container["id"]
    print("Waiting for processing...")
    finished = False
    for attempt in range(12):
        time.sleep(8)
        r = requests.get(
            f"https://graph.instagram.com/v21.0/{cid}",
            params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN},
            timeout=15,
        )
        r.raise_for_status()
        status = r.json()
        print(f"   [{attempt + 1}] {status.get('status_code')}")
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
    if not r2.ok:
        print(f"Instagram /media_publish failed ({r2.status_code}): {r2.text}")
    r2.raise_for_status()
    result = r2.json()
    print(f"Result: {result}")
    return result


def main():
    print("=" * 60)
    print(f"Starting: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Pillow RAQM RTL support: {USE_RAQM}")
    print("=" * 60)

    articles = fetch_it_news(5)
    if not articles:
        print("No articles found.")
        sys.exit(1)

    print(f"Found {len(articles)} technology articles")
    print(f"Writing natural Persian news with {OPENAI_MODEL}...")

    items = []
    for i, article in enumerate(articles, start=1):
        item = edit_news_in_farsi(article)
        items.append(item)
        print(f"  {i}. [{item['category']}] {item['title_fa']}")

    if len(items) != 5:
        raise RuntimeError("Exactly 5 news items are required")

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
