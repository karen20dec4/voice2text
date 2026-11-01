from PIL import Image, ImageDraw, ImageFilter
import os
import math
from pathlib import Path


def create_brand_icon(output_dir):
    """Create the editable SVG plus matching transparent PNG/ICO app icons."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs><linearGradient id="bg" x2="0" y2="1"><stop stop-color="#1c425c"/><stop offset="1" stop-color="#0c1927"/></linearGradient></defs>
<rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)" stroke="#46c9ff" stroke-width="3"/>
<g fill="#25d9e5"><rect x="43" y="115" width="6" height="20" rx="3"/><rect x="58" y="101" width="6" height="48" rx="3"/><rect x="73" y="109" width="6" height="32" rx="3"/><rect x="177" y="109" width="6" height="32" rx="3"/><rect x="192" y="101" width="6" height="48" rx="3"/><rect x="207" y="115" width="6" height="20" rx="3"/></g>
<g fill="none" stroke="#f3f8fc" stroke-width="7" stroke-linecap="round"><rect x="106" y="53" width="44" height="84" rx="22"/><path d="M89 130a39 37 0 0 0 78 0M128 169v27M106 198h44"/></g>
</svg>'''
    (directory / "icon.svg").write_text(svg, encoding="utf-8")
    scale = 4
    size = 256 * scale
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8*scale, 8*scale, 248*scale, 248*scale), radius=56*scale, fill=255)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        t = y / (size-1)
        color = tuple(round(a*(1-t)+b*t) for a,b in zip((28,66,92),(12,25,39)))
        draw.line((0,y,size,y), fill=color+(255,))
    image.putalpha(mask)
    draw = ImageDraw.Draw(image)
    def box(values): return tuple(round(value*scale) for value in values)
    draw.rounded_rectangle(box((8,8,248,248)), radius=56*scale, outline="#46c9ff", width=3*scale)
    for x, height in ((43,20),(58,48),(73,32),(177,32),(192,48),(207,20)):
        draw.rounded_rectangle(box((x,125-height/2,x+6,125+height/2)),radius=3*scale,fill="#25d9e5")
    draw.rounded_rectangle(box((106,53,150,137)),radius=22*scale,outline="#f3f8fc",width=7*scale)
    draw.arc(box((89,93,167,167)),0,180,fill="#f3f8fc",width=7*scale)
    draw.line(box((128,169,128,196)),fill="#f3f8fc",width=7*scale)
    draw.line(box((106,198,150,198)),fill="#f3f8fc",width=7*scale)
    image=image.resize((256,256),Image.Resampling.LANCZOS)
    image.save(directory / "icon.png")
    image.save(directory / "icon.ico",sizes=[(n,n) for n in (16,24,32,48,64,128,256)])


def create_ui_assets(output_dir):
    """Render small UI glyphs as antialiased PNGs with genuine RGBA transparency."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    scale = 4
    ink = (232, 235, 241, 255)
    for name in ("mic", "chevron", "settings", "grip"):
        image = Image.new("RGBA", (32 * scale, 32 * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        def box(values):
            return tuple(round(value * scale) for value in values)
        def line(points, width=2):
            draw.line([(round(x * scale), round(y * scale)) for x, y in points],
                      fill=ink, width=round(width * scale), joint="curve")
        if name == "mic":
            draw.rounded_rectangle(box((12, 4, 20, 20)), radius=4 * scale,
                                   outline=ink, width=2 * scale)
            draw.arc(box((7, 10, 25, 26)), 0, 180, fill=ink, width=2 * scale)
            line([(16, 26), (16, 29)])
            line([(11, 29), (21, 29)])
        elif name == "chevron":
            line([(8, 12), (16, 20), (24, 12)], width=2.4)
        elif name == "settings":
            points = []
            for index in range(32):
                radius = 13 if index % 4 in (0, 1) else 10
                angle = index * math.pi / 16
                points.append(((16 + math.cos(angle) * radius) * scale,
                               (16 + math.sin(angle) * radius) * scale))
            draw.polygon(points, fill=ink)
            draw.ellipse(box((10, 10, 22, 22)), fill=(0, 0, 0, 0))
        else:
            for x in (12, 20):
                for y in (8, 16, 24):
                    draw.ellipse(box((x - 1.3, y - 1.3, x + 1.3, y + 1.3)),
                                 fill=(163, 168, 180, 180))
        image = image.resize((32, 32), Image.Resampling.LANCZOS)
        image.save(directory / f"{name}.png")
    create_button_skin(112, 28, primary=True).save(directory / "button-primary.png")
    create_button_skin(24, 28, primary=False).save(directory / "button-secondary.png")


def create_button_skin(width, height, primary=True):
    """Code-generated RGBA backplates matching the supplied blue/graphite reference."""
    scale = 4
    width, height = width * scale, height * scale
    radius = (height - 4 * scale) // 2 if primary else 8 * scale
    bounds = (scale, scale, width - scale - 1, height - 3 * scale - 1)
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(bounds, radius=radius, fill=255)
    shadow_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(shadow_mask).rounded_rectangle(
        (scale, 2 * scale, width - scale - 1, height - scale - 1), radius=radius, fill=140)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(scale))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.putalpha(shadow_mask)
    gradient = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(gradient)
    top, bottom = ((32, 75, 110), (13, 39, 52)) if primary else ((44, 52, 63), (27, 33, 40))
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(round(a * (1 - t) + b * t) for a, b in zip(top, bottom))
        draw.line((0, y, width, y), fill=color + (255,))
    gradient.putalpha(mask)
    image.alpha_composite(gradient)
    ImageDraw.Draw(image).rounded_rectangle(bounds, radius=radius,
        outline=(80, 186, 233, 255) if primary else (72, 82, 95, 255), width=scale)
    return image

def create_app_icon(output_path):
    # Create a 64x64 icon with a dark background and a glowing cyan/purple microphone design
    size = (64, 64)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw rounded circle / background badge
    draw.ellipse([4, 4, 60, 60], fill=(31, 111, 235, 255), outline=(56, 139, 253, 255), width=2)

    # Draw microphone body
    # Capsule
    draw.rounded_rectangle([26, 16, 38, 36], radius=6, fill=(255, 255, 255, 255))

    # Arc around capsule
    draw.arc([20, 24, 44, 42], start=0, end=180, fill=(255, 255, 255, 255), width=3)

    # Mic stem
    draw.line([32, 42, 32, 48], fill=(255, 255, 255, 255), width=3)

    # Mic base
    draw.line([25, 48, 39, 48], fill=(255, 255, 255, 255), width=3)

    image.save(output_path)
    return image

if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    create_brand_icon(directory)
    create_ui_assets(directory / "assets")
    print("Voice2Text SVG, ICO, PNG and UI assets created.")
