"""Export source readings and the current drawing's direction proof."""
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile
import csv
import json

from PIL import Image, ImageDraw

from .photo import png


GROUP_COLORS = ("#744fa4", "#1f8079")


def trace_table(result):
    """Original angle, strength and RGB for every origin on the cut line, adopted or not."""
    target = StringIO()
    writer = csv.writer(target)
    writer.writerow(("x_px", "y_px", "red", "green", "blue", "luma", "gradient", "direction_deg",
                     "group", "axis_deg", "axis_offset_deg", "status"))
    for p in result["row"]:
        gradient = "" if p["strength"] is None else f'{p["strength"]:.3f}'
        direction = "" if p["direction"] is None else f'{p["direction"]:.3f}'
        axis = "" if p["axis"] is None else f'{p["axis"]:.3f}'
        offset = "" if p["offset"] is None else f'{p["offset"]:.3f}'
        detail = p["status"] if p["status"] == "采用" else p["reason"] or p["status"]
        writer.writerow((p["x"], p["y"], *p["rgb"], f'{p["brightness"]:.3f}', gradient, direction,
                         "" if p["group"] is None else p["group"], axis, offset, detail))
    return target.getvalue().encode()


def axis_gap(groups):
    gap = abs(groups[0]["direction"] - groups[1]["direction"]) % 180
    return round(min(gap, 180 - gap), 1)


def proof(image, card, result):
    height, width = image.shape[:2]
    output = Image.new("RGB",(max(430,width),height+64),"#333044")
    output.paste(Image.fromarray(image),(0,0))
    draw=ImageDraw.Draw(output)
    c=card["settings"]
    draw.rectangle((c["left"],c["top"],c["right"],c["bottom"]),outline="#a691b8",width=2)
    if result["row"]:
        draw.line((c["left"],c["focus"],c["right"],c["focus"]),fill="#bb9a84",width=1)
    for p in result["row"]:
        if p["group"] is not None:
            draw.rectangle((p["x"] - 1, p["y"] - 1, p["x"] + 1, p["y"] + 1),
                           outline=GROUP_COLORS[(p["group"] - 1) % 2])
    groups = (result["reading"] or {}).get("groups") or []
    detail = " / ".join(f'group {g["group"]}: {g["direction"]:.1f} deg · {g["points"]} points'
                        for g in groups) or "this row has no adopted pair of directions"
    if len(groups) == 2:
        detail += f' · {axis_gap(groups)} deg apart'
    draw.text((14,height+13),f'Source row {c["focus"]} · {detail}',fill="#f3eee8")
    draw.text((14,height+35),f'Adopted {sum(1 for p in result["row"] if p["group"] is not None)}'
                             f' of {len(result["row"])} origins · region evidence {result["qualified"]}',
              fill="#e2cbeb")
    return png(output)


def package(card, original, image, result):
    memory=BytesIO()
    with ZipFile(memory,"w",ZIP_DEFLATED) as stream:
        stream.writestr("drawing.png",original)
        stream.writestr("reading.json",json.dumps({"card":card,"reading":result["reading"],
                                                   "histogram":result["histogram"],
                                                   "row":result["row"]},
                                                  ensure_ascii=False,indent=2))
        stream.writestr("hatch-profile.csv",trace_table(result))
        stream.writestr("hatch-proof.png",proof(image,card,result))
    return memory.getvalue()
