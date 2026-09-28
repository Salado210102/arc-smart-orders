"""Render a flashy PNG poster for the contest results (sent as a Telegram photo) + its caption.

Design is text/shapes only (no color-emoji font needed); the eye-catching emojis go in the HTML
caption that accompanies the image. Falls back gracefully if Pillow is not installed.
"""
from __future__ import annotations

import io
import time

BG = (15, 20, 27)
GOLD = (240, 185, 11)
WHITE = (245, 247, 250)
MUT = (139, 152, 169)
GREEN = (46, 204, 113)
BLUE = (90, 160, 255)

_FONTS = {
    "bold": ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",),
    "reg": ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",),
}


def pillow_available() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _font(kind, size):
    from PIL import ImageFont
    for p in _FONTS.get(kind, ()) + _FONTS["reg"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def round_label(round_start: int, round_hours: int = 12) -> str:
    """Human label for a closed round (UTC)."""
    a = time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(round_start)))
    b = time.strftime("%H:%M", time.gmtime(int(round_start) + round_hours * 3600))
    return f"{a} \u2192 {b} UTC"


def render_contest_poster(*, title: str = "CONCURSO POR VOLUMEN", label: str = "",
                          pozo: float = 0.0, trader: dict | None = None,
                          affiliate: dict | None = None,
                          cta: str = "Opera y gana la siguiente ronda",
                          footer: str = "SNIPER IA \u00b7 ARC") -> bytes:
    from PIL import Image, ImageDraw
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, H - 1], outline=GOLD, width=8)
    d.rectangle([0, 0, W, 160], fill=GOLD)
    d.text((W // 2, 80), title, font=_font("bold", 58), fill=(20, 24, 30), anchor="mm")
    d.text((W // 2, 280), "POZO", font=_font("bold", 46), fill=MUT, anchor="mm")
    d.text((W // 2, 410), f"${pozo:,.2f}", font=_font("bold", 150), fill=GOLD, anchor="mm")
    if label:
        d.text((W // 2, 520), label, font=_font("reg", 34), fill=MUT, anchor="mm")
    y = 620
    for lab, w, col in (("TRADER", trader, GREEN), ("AFILIADO", affiliate, BLUE)):
        d.rounded_rectangle([80, y, W - 80, y + 150], radius=26, fill=(24, 31, 41))
        d.text((120, y + 26), lab, font=_font("bold", 34), fill=col)
        if w:
            d.text((120, y + 78), f"{w.get('user', '')}  \u00b7  ${w.get('volume', 0):,.0f}",
                   font=_font("reg", 40), fill=WHITE)
            d.text((W - 120, y + 78), f"+${w.get('prize', 0):.2f}", font=_font("bold", 46),
                   fill=GOLD, anchor="ra")
        else:
            d.text((120, y + 78), "sin volumen", font=_font("reg", 40), fill=MUT)
        y += 180
    d.text((W // 2, 1000), cta, font=_font("bold", 42), fill=WHITE, anchor="mm")
    d.text((W // 2, 1052), footer, font=_font("reg", 28), fill=MUT, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def poster_caption(pozo: float, trader: dict | None, affiliate: dict | None) -> str:
    """Flashy HTML caption that goes with the image (Telegram HTML)."""
    lines = ["\U0001F3C6\U0001F525 <b>RESULTADOS DEL CONCURSO</b> \U0001F525\U0001F3C6",
             f"\U0001F4B0 Pozo repartido: <b>${pozo:,.2f}</b>", ""]
    for emoji, label, w in (("\U0001F947", "Trader", trader), ("\U0001F947", "Afiliado", affiliate)):
        if w:
            lines.append(f"{emoji} <b>{label}:</b> {w.get('user', '')} \u2014 "
                         f"${w.get('volume', 0):,.0f} \u2192 gana <b>${w.get('prize', 0):.2f}</b>")
        else:
            lines.append(f"{emoji} <b>{label}:</b> sin volumen")
    lines.append("")
    lines.append("\U0001F4A5 \u00a1Opera y gana la pr\u00f3xima ronda!")
    return "\n".join(lines)
