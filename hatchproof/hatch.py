"""Estimate stroke direction from real neighboring pixels on an original drawing."""
from itertools import combinations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from image_lab.validation import integer, number

from .photo import decode, pixels, png, MAX_IMAGE_BYTES


LUMA = np.array([0.2126, 0.7152, 0.0722])
BIN_WIDTH = 5
BIN_COUNT = 180 // BIN_WIDTH
GROUP_MINIMUM = 4
GROUP_SEPARATION = 25
DEFAULT_TOLERANCE = 10


def settings(value, size):
    width, height = size
    left = integer(value.get("left"), "左界 X", 0, width - 1)
    top = integer(value.get("top"), "上界 Y", 0, height - 1)
    return {
        "left": left, "right": integer(value.get("right"), "右界 X", left, width - 1),
        "top": top, "bottom": integer(value.get("bottom"), "下界 Y", top, height - 1),
        "focus": integer(value.get("focus"), "截线 Y", 0, height - 1),
        "cutoff": number(value.get("cutoff"), "最小纹理强度", 0.1, 180),
        "tolerance": number(value.get("tolerance", DEFAULT_TOLERANCE), "组内轴向容差", 0, 89),
    }


def defaults(size):
    width, height = size
    return settings({"left": width // 7, "right": width * 6 // 7, "top": height // 5,
                     "bottom": height * 4 // 5, "focus": height // 2, "cutoff": 8,
                     "tolerance": DEFAULT_TOLERANCE}, size)


def local_direction(gx, gy):
    magnitude = np.hypot(gx, gy)
    direction = (np.degrees(np.arctan2(gy, gx)) + 90) % 180
    return magnitude, direction


def in_frame(x, y, config):
    return config["left"] <= x <= config["right"] and config["top"] <= y <= config["bottom"]


def clipped(rgb):
    return any(channel == 0 or channel == 255 for channel in rgb)


def point_data(image, x, y, config, magnitude=None, angle=None):
    rgb = image[y, x]
    evidence = magnitude is not None and magnitude >= config["cutoff"]
    return {
        "x": x, "y": y, "rgb": rgb.tolist(), "brightness": float(rgb @ LUMA),
        "strength": float(magnitude) if magnitude is not None else None,
        "direction": float(angle) if evidence else None,
        "in_frame": in_frame(x, y, config), "clipped": clipped(rgb.tolist()),
    }


def point(image, x, y, config):
    height, width = image.shape[:2]
    if not (1 <= x < width - 1 and 1 <= y < height - 1):
        return point_data(image, x, y, config)
    neighbors = image[[y, y, y - 1, y + 1], [x - 1, x + 1, x, x]] @ LUMA
    left, right, top, bottom = neighbors
    return point_data(image, x, y, config, *local_direction((right - left) / 2, (bottom - top) / 2))


def axis_difference(angles, direction):
    gap = np.abs(np.asarray(angles, dtype=float) - direction) % 180
    return np.minimum(gap, 180 - gap).astype(float)


def supported(row, config, height, width):
    """A source point counts only with its centre and four neighbours inside the frame."""
    x, y = row["x"], row["y"]
    return (row["in_frame"] and not row["clipped"] and row["direction"] is not None
            and all(in_frame(*pixel, config) for pixel in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                    ) and 1 <= x < width - 1 and 1 <= y < height - 1)


def candidates(image, config):
    """Source points on the cut line, in frame with in-frame neighbours, unclipped, evidenced."""
    left, right = config["left"], config["right"]
    y = config["focus"]
    if not config["top"] <= y <= config["bottom"]:
        return []
    height, width = image.shape[:2]
    return [(row["x"], row) for x in range(left, right + 1)
            for row in [point(image, x, y, config)] if supported(row, config, height, width)]


def covering_axis(angles):
    """Axis in the middle of the shortest circular arc that holds every angle."""
    values = np.sort(np.asarray(angles, dtype=float) % 180)
    if len(values) == 1:
        return float(values[0])
    gaps = np.diff(np.concatenate([values, [values[0] + 180]]))
    cut = int(np.argmax(gaps))
    start, end = values[(cut + 1) % len(values)], values[cut]
    return float((start + (end - start) % 180 / 2) % 180)


def settle(angles, direction, tolerance):
    """Members within tolerance of one axis, the axis re-centred on the set until it holds."""
    axis = float(direction)
    for _ in range(16):
        members = np.flatnonzero(axis_difference(angles, axis) <= tolerance)
        centred = covering_axis(angles[members]) if len(members) else axis
        if axis_difference([centred], axis)[0] < 1e-9:
            break
        axis = centred
    members = np.flatnonzero(axis_difference(angles, axis) <= tolerance)
    return tuple(sorted(members.tolist())), axis


def group_options(angles, tolerance):
    """Stable clusters of at least four origins; wider support first, duplicates by subset removed."""
    options = [settle(angles, angle, tolerance) for angle in np.unique(angles)]
    kept = []
    for option in sorted(set(options), key=lambda item: (-len(item[0]), round(item[1], 9))):
        if not any(set(option[0]) <= set(earlier[0]) for earlier in kept):
            kept.append(option)
    return [option for option in kept if len(option[0]) >= GROUP_MINIMUM]


def spread(angles, indices, axis):
    """Worst axis offset inside a group, the measure of how level its directions are."""
    return float(np.max(axis_difference(angles[list(indices)], axis)))


def choose(image, config):
    """Adopt two disjoint groups at least 25° apart: widest real support first, then the most level."""
    entries = candidates(image, config)
    angles = np.asarray([row["direction"] for _, row in entries])
    options = group_options(angles, config["tolerance"]) if len(entries) >= GROUP_MINIMUM else []
    ranking = []
    for first, second in combinations(range(len(options)), 2):
        one, two = options[first], options[second]
        if set(one[0]) & set(two[0]):
            continue
        if axis_difference([one[1]], two[1])[0] < GROUP_SEPARATION:
            continue
        ranking.append((-(len(one[0]) + len(two[0])),
                        spread(angles, *one) + spread(angles, *two), first, second))
    picked = min(ranking, default=None)
    return entries, None if picked is None else (options[picked[2]], options[picked[3]])


def analysis(image, config):
    entries, groups = choose(image, config)
    axes = [axis for _, axis in groups] if groups else []
    claimed = {index: number for number, (indices, _) in enumerate(groups or []) for index in indices}
    pieces = []
    for index, (_, row) in enumerate(entries):
        number = claimed.get(index)
        axis = None if number is None else axes[number]
        pieces.append({**row, "group": None if number is None else number + 1,
                       "axis": axis, "offset": None if axis is None else
                       float(axis_difference([row["direction"]], axis)[0])})
    return entries, pieces, groups, axes


def resume(config):
    """Cards saved before the tolerance field existed fall back to the default."""
    return {**config, "tolerance": number(config.get("tolerance", DEFAULT_TOLERANCE),
                                          "组内轴向容差", 0, 89)}


def reason(row, config, height, width):
    """Why an origin was left out, or None when it is a usable candidate."""
    x, y = row["x"], row["y"]
    if not row["in_frame"]:
        return "中心不在原框"
    if row["clipped"]:
        return "RGB 通道触 0 或 255"
    if not (1 <= x < width - 1 and 1 <= y < height - 1):
        return "邻点越出原片"
    if any(not in_frame(*pixel, config) for pixel in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
        return "邻点越出原框"
    if row["direction"] is None:
        return "纹理强度低于阈值"
    return None


def verdict(row, config, height, width):
    return "采用" if row["group"] is not None else "未采用", reason(row, config, height, width)


def axis_list(groups, axes):
    return [{"group": number + 1, "direction": float(axis), "points": len(groups[number][0])}
            for number, axis in enumerate(axes)]


def probe(image, x, y, config):
    """One source reading with its adopted group, or the reason it was not adopted."""
    config = resume(config)
    height, width = image.shape[:2]
    entries, pieces, groups, axes = analysis(image, config)
    found = next((piece for piece in pieces if piece["x"] == x and piece["y"] == y), None)
    if found is None:
        found = {**point(image, x, y, config), "group": None, "axis": None, "offset": None}
    found["status"], found["reason"] = verdict(found, config, height, width)
    found["groups"] = axis_list(groups, axes)
    return found


def row_entries(image, config, pieces):
    """Every origin on the cut line keeps its own angle, strength and RGB, adopted or not."""
    left, right, y = config["left"], config["right"], config["focus"]
    height, width = image.shape[:2]
    claimed = {(piece["x"], piece["y"]): piece for piece in pieces}
    rows = []
    for x in range(left, right + 1):
        row = claimed.get((x, y))
        if row is None:
            row = {**point(image, x, y, config), "group": None, "axis": None, "offset": None}
        row["status"], row["reason"] = verdict(row, config, height, width)
        rows.append(row)
    return rows


def group_reading(entries, groups, axes, config):
    """The adopted axes, wider real support listed first."""
    if not groups:
        return None
    angles = np.asarray([row["direction"] for _, row in entries])
    listed = sorted(range(len(groups)), key=lambda number: -len(groups[number][0]))
    return {
        "y": config["focus"],
        "candidates": len(entries),
        "groups": [{"group": number + 1, "direction": float(axes[number]),
                    "points": len(groups[number][0]),
                    "spread": spread(angles, groups[number][0], axes[number])}
                   for number in listed],
    }


def direction_field(image):
    brightness = image @ LUMA
    horizontal = (brightness[1:-1, 2:] - brightness[1:-1, :-2]) / 2
    vertical = (brightness[2:, 1:-1] - brightness[:-2, 1:-1]) / 2
    return local_direction(horizontal, vertical)


def histogram(angles):
    bins = (np.floor((angles + BIN_WIDTH / 2) / BIN_WIDTH).astype(int)) % BIN_COUNT
    return np.bincount(bins, minlength=BIN_COUNT)


def report(image, config):
    config = resume(config)
    left, right, top, bottom, y = (config[k] for k in ("left", "right", "top", "bottom", "focus"))
    strength, direction = direction_field(image)
    end_y, end_x = strength.shape
    area = np.s_[max(0, top - 1):min(end_y, bottom), max(0, left - 1):min(end_x, right)]
    directions = direction[area][strength[area] >= config["cutoff"]]
    counts = histogram(directions)
    entries, pieces, groups, axes = analysis(image, config)
    reading = group_reading(entries, groups, axes, config)
    rows = row_entries(image, config, pieces) if top <= y <= bottom else []
    return {"reading": reading, "row": rows, "focus": y, "candidates": len(entries),
            "qualified": len(directions),
            "histogram": [{"direction": i * BIN_WIDTH, "count": int(n)} for i, n in enumerate(counts)]}


def practice():
    width, height = 784, 472
    cfg = settings({"left": 139, "right": 644, "top": 123, "bottom": 346, "focus": 176,
                    "cutoff": 8, "tolerance": DEFAULT_TOLERANCE}, (width, height))
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
