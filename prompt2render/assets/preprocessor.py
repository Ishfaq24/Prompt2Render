"""Image pre-processing and legibility conditioning for video assets.

Ensures real-world photography and graphics maintain WCAG text contrast,
standard 16:9 framing, and clean transparency cutouts.
"""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


def crop_to_aspect_ratio(
    image: Image.Image,
    target_width: int = 1920,
    target_height: int = 1080,
) -> Image.Image:
    """Center-crop and resize an image to exact target dimensions."""
    target_ratio = target_width / target_height
    src_w, src_h = image.size
    src_ratio = src_w / src_h

    if abs(src_ratio - target_ratio) < 1e-3:
        return image.resize((target_width, target_height), Image.Resampling.LANCZOS)

    if src_ratio > target_ratio:
        # Source is wider than 16:9 -> crop left/right
        new_w = int(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        box = (offset, 0, offset + new_w, src_h)
    else:
        # Source is taller than 16:9 -> crop top/bottom
        new_h = int(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        box = (0, offset, src_w, offset + new_h)

    cropped = image.crop(box)
    return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)


def apply_background_scrim(
    image: Image.Image,
    darkness: float = 0.40,
    blur_radius: float = 1.5,
) -> Image.Image:
    """Darken and apply a subtle vignette + blur to create a high-contrast background."""
    img = image.convert("RGBA")
    w, h = img.size

    # 1. Subtle blur to reduce high-frequency photographic noise behind text
    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # 2. Base darkening layer (dark slate #080c14 with alpha)
    overlay = Image.new("RGBA", (w, h), (8, 12, 20, int((1.0 - darkness) * 255)))
    img = Image.alpha_composite(img, overlay)

    # 3. Radial dark vignette
    vignette = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(vignette)
    cx, cy = w / 2, h / 2
    max_radius = math.hypot(cx, cy)

    # Draw gradient rings
    steps = 40
    for i in range(steps):
        r = max_radius * (i / steps)
        # Alpha ramps up towards outer edges
        alpha = int((i / steps) ** 1.8 * 140)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=alpha, width=int(max_radius / steps) + 2)

    vignette_color = Image.new("RGBA", (w, h), (4, 6, 10, 0))
    vignette_color.putalpha(vignette)
    img = Image.alpha_composite(img, vignette_color)

    return img.convert("RGB")


def create_asset_card(
    image: Image.Image,
    target_width: int = 960,
    target_height: int = 540,
    corner_radius: int = 16,
    border_color: tuple[int, int, int] = (50, 130, 240),
    border_width: int = 3,
) -> Image.Image:
    """Format image into a clean rounded reference card with subtle border."""
    fitted = crop_to_aspect_ratio(image, target_width, target_height).convert("RGBA")
    w, h = fitted.size

    # Create rounded corner mask
    mask = Image.new("L", (w, h), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle([(0, 0), (w, h)], radius=corner_radius, fill=255)

    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    card.paste(fitted, (0, 0), mask=mask)

    # Draw border
    draw_card = ImageDraw.Draw(card)
    draw_card.rounded_rectangle(
        [(border_width // 2, border_width // 2), (w - border_width // 2 - 1, h - border_width // 2 - 1)],
        radius=corner_radius,
        outline=(*border_color, 255),
        width=border_width,
    )

    return card


def prepare_scene_asset(
    src_path: Path,
    dest_path: Path,
    role: str = "background",
    target_width: int = 1920,
    target_height: int = 1080,
    darkness: float = 0.40,
) -> Path:
    """Process and condition a downloaded external asset for video rendering.

    Args:
        src_path: Path to the raw downloaded image.
        dest_path: Destination path for the processed asset.
        role: One of 'background', 'card', 'raw', 'cutout'.
        target_width: Target image width in pixels.
        target_height: Target image height in pixels.
        darkness: Brightness factor for backgrounds (0.0 to 1.0; 0.40 = 60% darker).

    Returns:
        The processed image destination Path.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src_path) as img:
        # Handle EXIF orientation
        img = ImageOps.exif_transpose(img)

        if role == "background":
            cropped = crop_to_aspect_ratio(img, target_width, target_height)
            result = apply_background_scrim(cropped, darkness=darkness)
            result.save(dest_path, format="PNG")

        elif role == "card":
            result = create_asset_card(img, target_width, target_height)
            result.save(dest_path, format="PNG")

        elif role == "cutout":
            # Keep alpha channel if present
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            result = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            result.save(dest_path, format="PNG")

        else:  # raw
            result = crop_to_aspect_ratio(img, target_width, target_height)
            result.save(dest_path, format="PNG")

    return dest_path
