"""Estimate stroke direction from real neighboring pixels on an original drawing."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from image_lab.validation import integer, number

from .photo import decode, pixels, png, MAX_IMAGE_BYTES


LUMA = np.array([0.2126, 0.7152, 0.0722])
BIN_WIDTH = 5
BIN_COUNT = 180 // BIN_WIDTH


def settings(value, size):
    width, height = size
    left = integer(value.get("left"), "左界 X", 0, width - 1)
    top = integer(value.get("top"), "上界 Y", 0, height - 1)
    return {
        "left": left, "right": integer(value.get("right"), "右界 X", left, width - 1),
        "top": top, "bottom": integer(value.get("bottom"), "下界 Y", top, height - 1),
        "focus": integer(value.get("focus"), "截线 Y", 0, height - 1),
        "cutoff": number(value.get("cutoff"), "最小纹理强度", 0.1, 180),
    }


def defaults(size):
    width, height = size
    return settings({"left": width // 7, "right": width * 6 // 7, "top": height // 5,
                     "bottom": height * 4 // 5, "focus": height // 2, "cutoff": 8}, size)


def local_direction(gx, gy):
    magnitude = np.hypot(gx, gy)
    direction = (np.degrees(np.arctan2(gy, gx)) + 90) % 180
    return magnitude, direction


def point_data(image, x, y, config, magnitude=None, angle=None):
    rgb = image[y, x]
    evidence = magnitude is not None and magnitude >= config["cutoff"]
    return {
        "x": x, "y": y, "rgb": rgb.tolist(), "brightness": float(rgb @ LUMA),
        "strength": float(magnitude) if magnitude is not None else None,
        "direction": float(angle) if evidence else None,
    }


def point(image, x, y, config):
    height, width = image.shape[:2]
    if not (1 <= x < width - 1 and 1 <= y < height - 1):
        return point_data(image, x, y, config)
    neighbors = image[[y, y, y - 1, y + 1], [x - 1, x + 1, x, x]] @ LUMA
    left, right, top, bottom = neighbors
    return point_data(image, x, y, config, *local_direction((right - left) / 2, (bottom - top) / 2))


def direction_field(image):
    brightness = image @ LUMA
    horizontal = (brightness[1:-1, 2:] - brightness[1:-1, :-2]) / 2
    vertical = (brightness[2:, 1:-1] - brightness[:-2, 1:-1]) / 2
    return local_direction(horizontal, vertical)


def histogram(angles):
    bins = (np.floor((angles + BIN_WIDTH / 2) / BIN_WIDTH).astype(int)) % BIN_COUNT
    return np.bincount(bins, minlength=BIN_COUNT)


def report(image, config):
    left, right, top, bottom, y = (config[k] for k in ("left", "right", "top", "bottom", "focus"))
    strength, direction = direction_field(image)
    end_y, end_x = strength.shape
    area = np.s_[max(0, top - 1):min(end_y, bottom), max(0, left - 1):min(end_x, right)]
    directions = direction[area][strength[area] >= config["cutoff"]]
    counts = histogram(directions)
    profile = [point(image, x, y, config) for x in range(left, right + 1)] if top <= y <= bottom else []
    angles = np.asarray([row["direction"] for row in profile if row["direction"] is not None])
    row_histogram = histogram(angles)
    reading = None
    if len(angles):
        index = int(np.argmax(row_histogram))
        reading = {"direction": index * BIN_WIDTH, "dominant": int(row_histogram[index]),
                   "qualified": len(angles), "samples": len(profile), "y": y}
    return {"reading": reading, "profile": profile, "focus": y, "qualified": len(directions),
            "histogram": [{"direction": i * BIN_WIDTH, "count": int(n)} for i,n in enumerate(counts)]}


def practice():
    width, height = 784, 472
    cfg = settings({"left": 139, "right": 644, "top": 123, "bottom": 346, "focus": 176,
                    "cutoff": 8}, (width, height))
    y, x = np.indices((height, width))
    paper = (83 < x) & (x < 702) & (76 < y) & (y < 401)
    top_panel = paper & (111 <= x) & (x <= 672) & (112 <= y) & (y <= 229)
    lower_panel = paper & (111 <= x) & (x <= 672) & (245 <= y) & (y <= 360)
    vertical = 86 * np.exp(-(((x - 122 + 7) % 15 - 7) / 2.5) ** 2)
    horizontal = 77 * np.exp(-(((y - 245 + 9) % 19 - 9) / 3.4) ** 2)
    diagonal = 20 * np.exp(-(((x - 1.28*y + 14) % 29 - 14) / 2.8) ** 2)
    noise = 2.2 * np.sin(x * 0.44 + y * 0.61) + 1.5 * np.sin(y * 0.53 - x * 0.12)
    darkness = top_panel * (vertical + diagonal) + lower_panel * (horizontal + diagonal)
    tone = np.where(paper,209,60) + noise - darkness
    photo = Image.fromarray((tone[...,None] + np.array([6,0,-10])).clip(0,255).astype("uint8"),"RGB")
    draw = ImageDraw.Draw(photo)
    draw.rounded_rectangle((83,76,702,401),radius=8,outline="#d6b89e",width=2)
    draw.text((112,88),"GRAPHITE HATCH CARD / A AND B",fill="#58545a",font=ImageFont.load_default(size=13))
    draw.text((108,428),"SIMULATED DRAWING PHOTO",fill="#ddd1c9",font=ImageFont.load_default(size=12))
    return photo.size,png(photo),cfg


def width_report(*args, **kwargs):
    from .width import width_report as implementation
    return implementation(*args, **kwargs)


def measure_stroke_width(*args, **kwargs):
    from .width import measure_stroke_width as implementation
    return implementation(*args, **kwargs)


def measure_width(*args, **kwargs):
    from .width import measure_width as implementation
    return implementation(*args, **kwargs)


def stroke_width(*args, **kwargs):
    from .width import stroke_width as implementation
    return implementation(*args, **kwargs)
