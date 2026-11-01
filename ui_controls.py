from functools import lru_cache
import os
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


ASSETS = Path(__file__).resolve().parent / "assets"
RECORDING_PLATE = ("#ff8f8f", "#ffd6d6")  # Light red fill and its bright border.
RECORDING_INK = (74, 14, 18, 255)


def _recording_plate(image):
    plate = ImageOps.colorize(ImageOps.grayscale(image.convert("RGB")),
                              black=RECORDING_PLATE[0], white=RECORDING_PLATE[1]).convert("RGBA")
    plate.putalpha(image.getchannel("A"))
    return plate


@lru_cache(maxsize=128)
def _button_image(width, height, icon, text, hovered, recording=False):
    primary = icon == "mic"
    with Image.open(ASSETS / ("button-primary.png" if primary else "button-secondary.png")) as source:
        image = source.convert("RGBA").resize((width * 4, height * 4), Image.Resampling.LANCZOS)
    if recording:
        image = _recording_plate(image)
    if hovered:
        image = ImageEnhance.Brightness(image).enhance(1.15)
    draw = ImageDraw.Draw(image)
    with Image.open(ASSETS / f"{icon}.png") as source:
        size = 13 if primary else 14
        glyph = source.convert("RGBA").resize((size * 4, size * 4), Image.Resampling.LANCZOS)
    if primary:
        if recording:
            ink = Image.new("RGBA", glyph.size, RECORDING_INK)
            ink.putalpha(glyph.getchannel("A"))
            glyph = ink
        image.alpha_composite(glyph, (17 * 4, 6 * 4))
        for x, bar_height in ((8, 3), (11, 7), (14, 4)):
            draw.rounded_rectangle((x * 4, (13 - bar_height / 2) * 4,
                                    (x + 1.4) * 4, (13 + bar_height / 2) * 4),
                                   radius=2, fill=RECORDING_INK if recording else (51, 190, 234, 255))
        draw.line((35 * 4, 7 * 4, 35 * 4, 21 * 4),
                  fill=RECORDING_INK if recording else (75, 116, 144, 220), width=3)
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        font = ImageFont.truetype(str(font_path), 11 * 4) if font_path.exists() else ImageFont.load_default(size=11 * 4)
        label = text
        while label and draw.textlength(label, font=font) > (width - 43) * 4:
            label = label[:-1]
        draw.text(((width + 36) * 2, 13.5 * 4), label, font=font,
                  fill=RECORDING_INK if recording else (245, 249, 253, 255), anchor="mm")
    else:
        image.alpha_composite(glyph, ((width * 4 - glyph.width) // 2, 6 * 4))
    return image


class ImageButton(ctk.CTkButton):
    """CTk mouse interactions with an RGBA image skin instead of emoji glyphs."""
    def __init__(self, master, *, text="", icon, width, command):
        self.label_text = text
        self.icon = icon
        self.skin_width = width
        self.skin_height = 28
        self._skin_hovered = False
        self._skin_recording = False
        self._skin_image = self._make_image()
        super().__init__(master, text="", image=self._skin_image, width=width, height=28,
                         corner_radius=0, border_width=0, border_spacing=0,
                         fg_color="transparent", hover_color="#141b22", command=command)

    def _make_image(self):
        image = _button_image(self.skin_width, self.skin_height, self.icon, self.label_text,
                              self._skin_hovered, self._skin_recording)
        return ctk.CTkImage(light_image=image, dark_image=image, size=(self.skin_width, self.skin_height))

    def set_recording(self, recording):
        self._skin_recording = recording
        self._skin_image = self._make_image()
        super().configure(image=self._skin_image)

    def configure(self, require_redraw=False, **kwargs):
        changed = "text" in kwargs
        if changed:
            self.label_text = kwargs.pop("text")
        # State color belongs to the status strip; only recording tints the
        # backplate, through set_recording.
        kwargs.pop("fg_color", None)
        kwargs.pop("text_color", None)
        if changed:
            self._skin_image = self._make_image()
            kwargs["image"] = self._skin_image
        return super().configure(require_redraw=require_redraw, **kwargs)

    def _on_enter(self, event=None):
        super()._on_enter(event)
        self._skin_hovered = True
        self._skin_image = self._make_image()
        super().configure(image=self._skin_image)

    def _on_leave(self, event=None):
        super()._on_leave(event)
        self._skin_hovered = False
        self._skin_image = self._make_image()
        super().configure(image=self._skin_image)
