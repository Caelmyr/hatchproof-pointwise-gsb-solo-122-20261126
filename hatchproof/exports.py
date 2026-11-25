"""Export source readings and the current drawing's direction proof."""
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile
import csv
import json

from PIL import Image, ImageDraw

from .photo import png


def trace_table(result):
    target = StringIO()
    writer = csv.writer(target)
    writer.writerow(("x_px","y_px","red","green","blue","luma","gradient","direction_deg"))
    for p in result["profile"]:
        gradient = "" if p["strength"] is None else f'{p["strength"]:.3f}'
        direction = "" if p["direction"] is None else f'{p["direction"]:.3f}'
        writer.writerow((p["x"],p["y"],*p["rgb"],f'{p["brightness"]:.3f}',gradient,direction))
    return target.getvalue().encode()


def proof(image, card, result):
    height, width = image.shape[:2]
    output = Image.new("RGB",(max(430,width),height+64),"#333044")
    output.paste(Image.fromarray(image),(0,0))
    draw=ImageDraw.Draw(output)
    c=card["settings"]
    draw.rectangle((c["left"],c["top"],c["right"],c["bottom"]),outline="#a691b8",width=2)
    if result["profile"]:
        draw.line((c["left"],c["focus"],c["right"],c["focus"]),fill="#bb9a84",width=1)
    for p in result["profile"]:
        if p["direction"] is not None:
            draw.point((p["x"],p["y"]),fill="#694a93")
    read=result["reading"]
    detail=(f'Source row {c["focus"]}: main direction {read["direction"]} deg / {read["dominant"]} supported points'
            if read else "This row has no supported orientation")
    draw.text((14,height+13),detail,fill="#f3eee8")
    draw.text((14,height+35),f'Region direction evidence: {result["qualified"]} source points',fill="#e2cbeb")
    return png(output)


def package(card, original, image, result):
    memory=BytesIO()
    with ZipFile(memory,"w",ZIP_DEFLATED) as stream:
        stream.writestr("drawing.png",original)
        stream.writestr("reading.json",json.dumps({"card":card,"reading":result["reading"],"histogram":result["histogram"]},
                                                  ensure_ascii=False,indent=2))
        stream.writestr("hatch-profile.csv",trace_table(result))
        stream.writestr("hatch-proof.png",proof(image,card,result))
    return memory.getvalue()
