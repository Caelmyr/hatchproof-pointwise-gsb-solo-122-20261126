"""Measure a stroke width from real source pixels on an oblique cross-section.

The functions in this module deliberately never synthesise pixels.  Geometry is
projected onto the stroke normal, but endpoint coordinates always name an
actual original image pixel.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np

from image_lab.validation import Invalid, integer, number

from .hatch import LUMA, point as hatch_point


def _coordinates(point):
    if isinstance(point, dict):
        return point["x"], point["y"]
    return point[0], point[1]


def projection_distance(point_a, point_b, normal):
    """Absolute distance between source-pixel centres projected on a normal."""
    ax, ay = _coordinates(point_a)
    bx, by = _coordinates(point_b)
    nx, ny = normal
    return abs((bx - ax) * nx + (by - ay) * ny)


def _nearest_pixel(x: float, y: float, width: int, height: int):
    """Return the nearest pixel centre, or ``None`` when outside the image."""
    ix = int(math.floor(x + 0.5))
    iy = int(math.floor(y + 0.5))
    if 0 <= ix < width and 0 <= iy < height:
        return ix, iy
    return None


def _missing_set(missing) -> set[tuple[int, int]]:
    if missing is None:
        return set()
    if isinstance(missing, np.ndarray):
        return {(int(x), int(y)) for y, x in np.argwhere(missing)}
    return {(int(x), int(y)) for x, y in missing}


def width_settings(value: dict, size: tuple[int, int]) -> dict:
    """Validate a width request without changing the older direction settings."""
    width, height = size
    if not isinstance(value, dict):
        raise Invalid("笔宽参数必须是对象")
    raw_x = value.get("x", value.get("px", value.get("origin_x")))
    raw_y = value.get("y", value.get("py", value.get("origin_y")))
    origin = value.get("origin", value.get("point"))
    if origin is not None and raw_x is None and raw_y is None:
        if isinstance(origin, dict):
            raw_x = origin.get("x", origin.get("px"))
            raw_y = origin.get("y", origin.get("py"))
        elif isinstance(origin, str):
            parts = origin.replace(";", ",").split(",")
            if len(parts) >= 2:
                raw_x, raw_y = parts[0].strip(), parts[1].strip()
        elif isinstance(origin, (list, tuple)) and len(origin) >= 2:
            raw_x, raw_y = origin[0], origin[1]
    x = integer(raw_x, "墨内原点 X", 0, width - 1)
    y = integer(raw_y, "墨内原点 Y", 0, height - 1)
    angle_value = value.get(
        "angle", value.get("direction", value.get("stroke_direction",
        value.get("stroke_angle", value.get("theta", 0)))))
    angle = number(angle_value, "笔的大概方向", -360, 360) % 180
    reach_value = value.get(
        "reach", value.get("max_distance", value.get("max_reach",
        value.get("span", value.get("max_span",
        value.get("search_distance", value.get("along",
        value.get("length", value.get("max_length",
        value.get("distance_limit", value.get("along_limit", 120)))))))))))
    reach = integer(reach_value, "沿笔最多查多远", 0, max(width, height) * 2)
    ink_value = 128
    for key in ("ink_limit", "ink_max", "ink_threshold", "ink_cutoff",
                "ink_brightness", "ink_brightness_limit", "ink_max_brightness",
                "max_ink_brightness", "black_ink_limit",
                "brightness_limit", "brightness_threshold", "brightness_cutoff",
                "darkness_limit", "darkness_cutoff", "dark_threshold",
                "darkness", "threshold", "black_limit"):
        if key in value:
            ink_value = value[key]
            break
    ink_limit = number(ink_value, "黑墨亮度上限", 0, 255)
    strict_value = value.get("strict_clipped", value.get("reject_clipped_paper", True))
    if isinstance(strict_value, str):
        strict_clipped = strict_value.strip().lower() not in {"0", "false", "no", "off"}
    else:
        strict_clipped = bool(strict_value)
    return {"x": x, "y": y, "angle": angle, "reach": reach,
            "ink_limit": ink_limit, "strict_clipped": strict_clipped}


def _pixel(image, brightness, clipped, x, y, *, missing=None):
    rgb = image[y, x][:3]
    return {
        "x": int(x),
        "y": int(y),
        "rgb": [int(v) for v in rgb],
        "brightness": float(brightness[y, x]),
        "clipped": bool(clipped[y, x]),
        "missing": (x, y) in missing,
    }


def _paper(point: dict, end: dict, ink_limit: float, strict_clipped: bool) -> bool:
    """A real, brighter, unsaturated source pixel immediately outside ink."""
    if point is None or point.get("missing"):
        return False
    if strict_clipped and point["clipped"]:
        return False
    return point["brightness"] > ink_limit and point["brightness"] > end["brightness"]


def _normal_section(image, brightness, clipped, missing, origin, tangent,
                    u, n, ink_limit, strict_clipped):
    """Find the one contiguous ink run containing ``tangent`` along ``n``."""
    height, width = image.shape[:2]
    ox, oy = origin
    qx, qy = tangent
    limit = int(math.ceil(math.hypot(width, height))) + 2
    seen = {(qx, qy)}

    def proj(x, y):
        return float((x - qx) * n[0] + (y - qy) * n[1])

    center = _pixel(image, brightness, clipped, qx, qy, missing=missing)
    if center["missing"] or center["brightness"] > ink_limit:
        return None, "origin_not_ink"

    sides = []
    for sign in (-1.0, 1.0):
        ink_chain = []
        paper = None
        reason = None
        last = (qx, qy)
        for step in range(1, limit + 1):
            p = _nearest_pixel(qx + sign * step * n[0],
                               qy + sign * step * n[1], width, height)
            if p is None:
                reason = "outside_frame"
                break
            if p == last or p in seen:
                # Oblique projections can land on one source pixel repeatedly.
                continue
            seen.add(p)
            last = p
            point = _pixel(image, brightness, clipped, *p, missing=missing)
            if point["missing"]:
                reason = "missing_original"
                paper = point
                break
            if point["brightness"] <= ink_limit:
                ink_chain.append(point)
                continue
            # The first non-ink pixel must itself be the adjacent paper witness.
            endpoint = ink_chain[-1] if ink_chain else center
            if not _paper(point, endpoint, ink_limit, strict_clipped):
                reason = "paper_not_clear"
            paper = point
            break

        if reason is not None and paper is None:
            return None, reason
        if paper is None:
            reason = reason or "no_paper_neighbour"
            return None, reason

        endpoint = ink_chain[-1] if ink_chain else center
        contrast = paper["brightness"] - endpoint["brightness"]
        sides.append({
            "sign": int(sign),
            "ink_chain": ink_chain,
            "endpoint": endpoint,
            "paper": paper,
            "contrast": float(contrast),
            "valid": reason is None and contrast > 0,
            "reason": reason,
        })

    negative, positive = sides
    if not negative["valid"] or not positive["valid"]:
        reasons = [side["reason"] for side in sides if side["reason"]]
        return None, reasons[0] if reasons else "paper_not_clear"

    # Build an ordered, duplicate-free actual-pixel profile for the chart.
    profile = []
    for point in reversed(negative["ink_chain"]):
        profile.append({**point, "role": "ink", "projection": proj(point["x"], point["y"])})
    profile.append({**center, "role": "cut", "projection": 0.0})
    for point in positive["ink_chain"]:
        profile.append({**point, "role": "ink", "projection": proj(point["x"], point["y"])})

    end_a = negative["endpoint"]
    end_b = positive["endpoint"]
    end_a = {**end_a, "role": "ink_end", "projection": proj(end_a["x"], end_a["y"]) if end_a is not center else 0.0}
    end_b = {**end_b, "role": "ink_end", "projection": proj(end_b["x"], end_b["y"]) if end_b is not center else 0.0}
    paper_a = {**negative["paper"], "role": "paper",
               "projection": proj(negative["paper"]["x"], negative["paper"]["y"])}
    paper_b = {**positive["paper"], "role": "paper",
               "projection": proj(positive["paper"]["x"], positive["paper"]["y"])}
    # Replace endpoint entries in profile with their endpoint role/projection.
    for row in profile:
        if (row["x"], row["y"]) == (end_a["x"], end_a["y"]):
            row.update(role="ink_end", projection=end_a["projection"])
        if (row["x"], row["y"]) == (end_b["x"], end_b["y"]):
            row.update(role="ink_end", projection=end_b["projection"])
    profile.insert(0, {**paper_a, "role": "paper_outer"})
    profile.append({**paper_b, "role": "paper_outer"})
    for row in profile:
        reading = hatch_point(image, row["x"], row["y"], {"cutoff": 8})
        row["strength"] = reading["strength"]
        row["direction"] = reading["direction"]

    width_px = projection_distance(end_a, end_b, n) + 1.0
    min_contrast = min(negative["contrast"], positive["contrast"])
    along = (qx - ox) * u[0] + (qy - oy) * u[1]
    candidate = {
        "tangent": {"x": qx, "y": qy},
        "angle": float(math.degrees(math.atan2(u[1], u[0])) % 180),
        "normal": [float(n[0]), float(n[1])],
        "distance": float(abs(along)),
        "signed_distance": float(along),
        "width": float(width_px),
        "ends": [end_a, end_b],
        "paper": [paper_a, paper_b],
        "contrasts": [negative["contrast"], positive["contrast"]],
        "min_contrast": float(min_contrast),
        "average_contrast": float(sum(c["contrast"] for c in sides) / 2),
        "profile": profile,
    }
    return candidate, None


def trace_tangents(image, brightness, clipped, ink_limit, missing, x, y, u, reach):
    """Unique source pixels on the unbroken ink trail in both axial directions."""
    height, width = image.shape[:2]
    origin = (x, y)
    origin_point = _pixel(image, brightness, clipped, x, y, missing=missing)
    if origin_point["missing"] or origin_point["brightness"] > ink_limit:
        return []

    tangents = [origin]
    seen = {origin}
    for sign in (-1.0, 1.0):
        last = origin
        for step in range(1, reach + 1):
            p = _nearest_pixel(x + sign * step * u[0], y + sign * step * u[1], width, height)
            if p is None:
                break
            if p == last or p in seen:
                continue
            seen.add(p)
            last = p
            px, py = p
            if (px, py) in missing or brightness[py, px] > ink_limit:
                # First interruption ends this ray; never jump to another stroke.
                break
            tangents.append(p)
    return tangents


def _score(candidate: dict, reach: int) -> float:
    """Equal-scale balance of nearness and clarity on both paper edges."""
    proximity = 1.0 - min(1.0, candidate["distance"] / max(1, reach))
    clarity = min(1.0, candidate["min_contrast"] / 100.0)
    return 0.5 * proximity + 0.5 * clarity


def width_report(image: np.ndarray, x: int, y: int, angle: Optional[float] = None,
                 reach: Optional[int] = None, ink_limit: Optional[float] = None,
                 missing: Optional[Iterable[tuple[int, int]]] = None,
                 strict_clipped: bool = True,
                 select: bool = True, **aliases) -> dict:
    """Return all measurable crosscuts and the balanced selected crosscut."""
    if angle is None:
        angle = aliases.get("direction", aliases.get("stroke_direction",
                            aliases.get("stroke_angle", aliases.get("theta", 0))))
    if reach is None:
        reach = aliases.get("max_distance", aliases.get("max_reach",
                            aliases.get("span", aliases.get("max_span",
                            aliases.get("max_length",
                            aliases.get("search_distance",
                            aliases.get("distance_limit", 120)))))))
    if ink_limit is None:
        for key in ("ink_threshold", "ink_cutoff", "ink_brightness",
                    "ink_brightness_limit", "ink_max_brightness",
                    "max_ink_brightness", "black_ink_limit",
                    "brightness_limit", "brightness_threshold",
                    "brightness_cutoff", "darkness_limit", "darkness_cutoff",
                    "dark_threshold", "darkness", "threshold", "black_limit"):
            if key in aliases:
                ink_limit = aliases[key]
                break
        if ink_limit is None:
            ink_limit = 128
    if missing is None:
        missing = aliases.get("missing_mask", aliases.get("absent", aliases.get("invalid_mask")))
    if "reject_clipped_paper" in aliases:
        strict_clipped = aliases["reject_clipped_paper"]
    if hasattr(image, "convert"):
        image = np.asarray(image.convert("RGB"))
    elif not isinstance(image, np.ndarray):
        image = np.asarray(image)
    if isinstance(angle, dict):
        config = angle
        angle = config.get("angle", config.get("direction", config.get("stroke_direction")))
        if reach is None:
            reach = config.get("reach", config.get("max_distance", config.get("max_reach")))
        if ink_limit is None:
            ink_limit = config.get("ink_limit", config.get("ink_threshold",
                                  config.get("ink_cutoff",
                                  config.get("ink_brightness"))))
        strict_clipped = config.get("strict_clipped",
                             config.get("reject_clipped_paper", strict_clipped))
        missing = config.get("missing", config.get("missing_mask", missing))
    if isinstance(missing, bool):
        # Forgiving positional compatibility: seventh argument may be strictness.
        strict_clipped = missing
        missing = None
    angle = float(angle) % 180
    reach = int(reach)
    ink_limit = float(ink_limit)

    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] < 3:
        raise Invalid("原照像素缺失，不能补造笔宽证据")
    height, width = image.shape[:2]
    if not (0 <= x < width and 0 <= y < height):
        raise Invalid("墨内原点在框外")

    missing_set = _missing_set(missing)
    brightness = image[:, :, :3] @ LUMA
    clipped = np.any((image[:, :, :3] == 0) | (image[:, :, :3] == 255), axis=2)
    theta = math.radians(angle % 180)
    u = np.array([math.cos(theta), math.sin(theta)], dtype=float)
    n = np.array([-math.sin(theta), math.cos(theta)], dtype=float)

    origin = _pixel(image, brightness, clipped, x, y, missing=missing_set)
    report = {
        "x": x, "y": y, "origin": origin, "angle": float(angle % 180),
        "direction": float(angle % 180),
        "stroke_vector": [float(u[0]), float(u[1])],
        "normal": [float(n[0]), float(n[1])],
        "reach": int(reach), "ink_limit": float(ink_limit),
        "unit": "source_pixel",
        "ink": origin["brightness"] <= ink_limit and not origin["missing"],
        "tangents": [],
        "candidates": [], "crosscuts": [], "selected": None, "best": None,
        "chosen": None, "index": None,
        "width": None, "width_px": None, "stroke_width": None,
        "measured_width": None, "value": None,
        "ends": None, "endpoints": None,
        "ink_ends": None, "end_a": None, "end_b": None, "a": None, "b": None,
        "x1": None, "y1": None, "x2": None, "y2": None,
        "profile": [], "pixel_trace": [],
    }
    if report["origin"]["missing"]:
        report["reason"] = "origin_missing"
        return report
    if not report["ink"]:
        report["reason"] = "origin_not_ink"
        return report

    tangents = trace_tangents(image, brightness, clipped, ink_limit, missing_set,
                              x, y, u, reach)
    report["tangents"] = [{"x": int(px), "y": int(py)} for px, py in tangents]
    candidates = []
    for tangent in tangents:
        candidate, reason = _normal_section(
            image, brightness, clipped, missing_set, (x, y), tangent,
            u, n, ink_limit, strict_clipped,
        )
        if candidate is not None:
            candidate["score"] = float(_score(candidate, reach))
            candidates.append(candidate)

    natural_candidates = list(candidates)
    ranked = sorted(candidates, key=lambda c: (-c["score"], c["distance"],
                                               -c["min_contrast"],
                                               c["tangent"]["y"],
                                               c["tangent"]["x"]))
    chosen = ranked[0] if ranked and select else None
    selected_index = next((i for i, candidate in enumerate(natural_candidates)
                           if candidate is chosen), None)
    report["candidates"] = ranked
    report["ranked_candidates"] = ranked
    report["crosscuts"] = ranked
    report["all_candidates"] = natural_candidates
    report["path_candidates"] = natural_candidates
    report["selected_index"] = selected_index
    report["natural_index"] = selected_index
    if chosen is not None:
        report["selected"] = chosen
        report["best"] = chosen
        report["chosen"] = chosen
        report["index"] = 0
        report["width"] = chosen["width"]
        report["width_px"] = chosen["width"]
        report["stroke_width"] = chosen["width"]
        report["measured_width"] = chosen["width"]
        report["value"] = chosen["width"]
        report["ends"] = chosen["ends"]
        report["endpoints"] = chosen["ends"]
        report["ink_ends"] = chosen["ends"]
        report["end_a"] = chosen["ends"][0]
        report["end_b"] = chosen["ends"][1]
        report["first_end"] = chosen["ends"][0]
        report["second_end"] = chosen["ends"][1]
        report["a"] = chosen["ends"][0]
        report["b"] = chosen["ends"][1]
        report["x1"] = chosen["ends"][0]["x"]
        report["y1"] = chosen["ends"][0]["y"]
        report["x2"] = chosen["ends"][1]["x"]
        report["y2"] = chosen["ends"][1]["y"]
        report["paper"] = chosen["paper"]
        report["contrasts"] = chosen["contrasts"]
        report["edge_contrasts"] = chosen["contrasts"]
        report["min_contrast"] = chosen["min_contrast"]
        report["profile"] = chosen["profile"]
        report["pixel_trace"] = chosen["profile"]
        report["trace"] = chosen["profile"]
        report["tangent"] = chosen["tangent"]
        report["distance"] = chosen["distance"]
        report["score"] = chosen["score"]
    elif not candidates:
        report["reason"] = "no_measurable_crosscut"
    return report


# Descriptive aliases for callers/tests using the domain language.
measure_stroke_width = width_report
stroke_width_report = width_report


def measure_width(*args, **kwargs):
    """Return only the chosen candidate (or ``None``) for low-level callers."""
    return width_report(*args, **kwargs).get("selected")


def stroke_width(*args, **kwargs):
    return width_report(*args, **kwargs)


analyze_stroke_width = width_report
find_stroke_width = width_report
measure = width_report
width_at = width_report
line_width = width_report
measure_line_width = width_report
