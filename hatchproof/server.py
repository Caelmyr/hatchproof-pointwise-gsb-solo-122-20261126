"""Serve stroke direction evidence and photographic preparation."""

from io import BytesIO
import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file, url_for

from image_lab import create_app as preparation_app
from image_lab.validation import Invalid, integer, object_value

from . import exports, hatch, width as width_mod
from .photo import pixels_and_missing
from .store import Cards


def download(data, mime, filename):
    return send_file(BytesIO(data), mimetype=mime, max_age=0, download_name=filename, as_attachment=True)


def create_app(directory=None):
    root = Path(directory or os.environ.get("HATCHPROOF_DATA", ".hatchproof-data")).resolve()
    desk = preparation_app(root / "prepare")
    cards = Cards(root / "cards")
    api = Blueprint("hatchproof", __name__, url_prefix="/hatchproof")

    @desk.get("/")
    def home():
        return render_template("hatchproof.html")

    @api.get("/health")
    def health():
        return jsonify(status="ok", app="hatchproof")

    @api.get("/cards")
    def listing():
        return jsonify(cards=cards.list())

    @api.post("/cards")
    def create():
        request.max_content_length = 20 * 1024 * 1024
        upload = request.files.get("photo")
        if not upload or not upload.filename:
            raise Invalid("请选择排线原照")
        size, image = hatch.decode(upload.stream.read(hatch.MAX_IMAGE_BYTES + 1))
        return jsonify(cards.create(request.form.get("name", ""), Path(upload.filename).name[:140],
                                    size, image, hatch.defaults(size))), 201

    @api.post("/practice")
    def practice():
        return jsonify(cards.demo()), 201

    @api.route("/cards/<key>", methods=["GET", "PATCH"])
    def card(key):
        return jsonify(cards.update(key, object_value(request.get_json(silent=True), "排线卡设置"))
                       if request.method == "PATCH" else cards.read(key))

    @api.get("/cards/<key>/capture.png")
    def capture(key):
        return send_file(cards.photo(key), mimetype="image/png", conditional=True)

    def measurement(key):
        card = cards.read(key, request.args.get("revision"))
        image = hatch.pixels(cards.photo(key))
        return card, image, hatch.report(image, card["settings"])

    @api.get("/cards/<key>/measurement")
    def measurement_json(key):
        card, _, result = measurement(key)
        return jsonify(revision=card["revision"], **result)

    @api.get("/cards/<key>/probe")
    def probe(key):
        card = cards.read(key, request.args.get("revision"))
        x = integer(request.args.get("x"), "X", 0, card["width"] - 1)
        y = integer(request.args.get("y"), "Y", 0, card["height"] - 1)
        return jsonify(hatch.point(hatch.pixels(cards.photo(key)), x, y, card["settings"]))

    def width_request_payload():
        if request.method == "GET":
            return request.args
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            nested = body.get("width") or body.get("measurement") or body.get("query")
            if isinstance(nested, dict):
                return {**request.args, **body, **nested}
            return {**request.args, **body}
        return {**request.args, **request.form}

    @api.route("/cards/<key>/width", methods=["GET", "POST"])
    @api.route("/cards/<key>/width/", methods=["GET", "POST"])
    @api.route("/cards/<key>/stroke-width", methods=["GET", "POST"])
    @api.route("/cards/<key>/stroke_width", methods=["GET", "POST"])
    @api.route("/cards/<key>/measure-width", methods=["GET", "POST"])
    @api.route("/cards/<key>/measure", methods=["GET", "POST"])
    @api.route("/cards/<key>/width-measurement", methods=["GET", "POST"])
    @api.route("/cards/<key>/width_measurement", methods=["GET", "POST"])
    @api.route("/cards/<key>/stroke-width-measurement", methods=["GET", "POST"])
    @api.route("/cards/<key>/width-measure", methods=["GET", "POST"])
    @api.route("/cards/<key>/stroke", methods=["GET", "POST"])
    @api.route("/cards/<key>/measurement/width", methods=["GET", "POST"])
    @api.route("/cards/<key>/probe/width", methods=["GET", "POST"])
    def stroke_width(key):
        payload = width_request_payload()
        card = cards.read(key, payload.get("revision"))
        photo_path = cards.photo(key)
        if not photo_path.is_file():
            from werkzeug.exceptions import NotFound
            raise NotFound("原照文件缺失，不能补造框外或缺失像素")
        image, missing = pixels_and_missing(photo_path)
        params = width_mod.width_settings(payload, (card["width"], card["height"]))
        result = width_mod.width_report(image, missing=missing, **params)
        return jsonify(revision=card["revision"], **result)

    @api.get("/cards/<key>/export/profile.csv")
    def profile(key):
        _, _, result = measurement(key)
        return download(exports.trace_table(result), "text/csv", "hatch-profile.csv")

    @api.get("/cards/<key>/export/proof.png")
    def proof(key):
        card, image, result = measurement(key)
        return download(exports.proof(image, card, result), "image/png", "hatch-proof.png")

    @api.get("/cards/<key>/export/observation.zip")
    def bundle(key):
        card, image, result = measurement(key)
        package = exports.package(card, cards.photo(key).read_bytes(), image, result)
        return download(package, "application/zip", f"hatchproof-r{card['revision']}.zip")

    @api.post("/cards/<key>/prepare")
    def prepare(key):
        card = cards.read(key, request.args.get("revision"))
        image = hatch.pixels(cards.photo(key)).astype("float32") / 255
        services = desk.extensions
        asset = services["assets"].put(image, card["photo_name"])
        project = services["store"].create(f'{card["name"]} · 原片准备')
        services["frames"].add(project["id"], project["revision"], [asset["id"]])
        return jsonify(url=url_for("index", project=project["id"])), 201

    desk.register_blueprint(api)
    return desk
