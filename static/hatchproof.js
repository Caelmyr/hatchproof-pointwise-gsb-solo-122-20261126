"use strict";

const get = (id) => document.getElementById(id);
const state = {card: null, result: null, photo: null, probe: null, mode: "probe", chart: "profile", busy: false};
const settings = [...document.querySelectorAll("[data-setting]")];

async function api(path, options) {
  const response = await fetch("/hatchproof" + path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "请求失败，请检查输入后重试。");
  return body;
}

function route(tail) {
  return "/cards/" + state.card.id + tail;
}

function savedQuery() {
  return "?revision=" + state.card.revision;
}

function notice(message, target = "notice") {
  const element = get(target);
  element.textContent = message;
  element.hidden = !message;
}

async function action(work, target = "notice") {
  if (state.busy) return;
  state.busy = true;
  document.querySelectorAll("button, select").forEach((node) => { node.disabled = true; });
  notice("", target);
  try {
    await work();
  } catch (error) {
    notice(error.message, target);
  } finally {
    state.busy = false;
    document.querySelectorAll("button, select").forEach((node) => { node.disabled = false; });
  }
}

async function library() {
  const {cards} = await api("/cards");
  const select = get("library");
  select.replaceChildren(new Option("选取已存卡片", ""));
  for (const card of cards) select.append(new Option(card.name, card.id));
  select.value = state.card?.id || "";
}

function paintSource() {
  const canvas = get("capture");
  const ctx = canvas.getContext("2d");
  const {photo, card, probe, result} = state;
  if (!photo) return;
  canvas.width = card.width;
  canvas.height = card.height;
  ctx.drawImage(photo, 0, 0);
  const cfg = card.settings;
  ctx.strokeStyle = "#aa91c0";
  ctx.lineWidth = 2;
  ctx.setLineDash([5,5]);
  ctx.strokeRect(cfg.left,cfg.top,cfg.right-cfg.left,cfg.bottom-cfg.top);
  ctx.setLineDash([]);
  if (result.profile.length) {
    ctx.strokeStyle = "#ba8270";
    ctx.beginPath();
    ctx.moveTo(cfg.left,result.focus);
    ctx.lineTo(cfg.right,result.focus);
    ctx.stroke();
  }
  ctx.strokeStyle = "#744fa4";
  ctx.lineWidth = 1.6;
  for (const p of result.profile.filter((point, index) => index % 4 === 0 && point.direction !== null)) {
    const angle = p.direction * Math.PI / 180;
    const dx = 4 * Math.cos(angle);
    const dy = 4 * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(p.x-dx,p.y-dy);
    ctx.lineTo(p.x+dx,p.y+dy);
    ctx.stroke();
  }
  if (probe) {
    ctx.strokeStyle = "#f8efa3";
    ctx.strokeRect(probe.x-5,probe.y-5,10,10);
  }
}

function paintChart() {
  const canvas = get("chart");
  const ctx = canvas.getContext("2d");
  const {width,height} = canvas;
  const {result,card} = state;
  const counts = state.chart === "coverage";
  const lo = counts ? 0 : card.settings.left;
  const hi = counts ? 175 : card.settings.right;
  const upper = counts ? Math.max(1,...result.histogram.map((bin) => bin.count)) : 180;
  const xAt = (x) => 51 + (width - 88) * (x - lo) / Math.max(1, hi - lo);
  const yAt = (y) => height - 26 - (height - 46) * y / upper;
  get("chart-title").textContent = counts ? "全框笔向计数" : "原行方向证据";
  get("chart-caption").textContent = counts ? "同轴5°箱 · 原像素计数" : "笔向度数 · 原片 X";
  ctx.fillStyle = "#faf8fb";
  ctx.fillRect(0,0,width,height);
  ctx.font = "12px monospace";
  ctx.fillStyle = "#4e4260";
  ctx.strokeStyle = "#e2d9e7";
  for (const level of [0,Math.round(upper / 2),upper]) {
    ctx.fillText(level,8,yAt(level)+3);
    ctx.beginPath();
    ctx.moveTo(xAt(lo),yAt(level));
    ctx.lineTo(xAt(hi),yAt(level));
    ctx.stroke();
  }
  ctx.fillText(String(lo),xAt(lo),height-7);
  ctx.fillText(String(hi),xAt(hi)-15,height-7);
  if (counts) {
    ctx.fillStyle = "#79608d";
    for (const bin of result.histogram) {
      const top = yAt(bin.count);
      ctx.fillRect(xAt(bin.direction)-5,top,10,yAt(0)-top);
    }
  } else {
    ctx.fillStyle = "#8d68a9";
    for (const p of result.profile) {
      if (p.direction !== null) ctx.fillRect(xAt(p.x),yAt(p.direction),2,2);
    }
  }
}

function pointLabel(point) {
  const evidence = point.direction === null ? "无方向证据" : point.direction.toFixed(2) + "°";
  const strength = point.strength === null ? "—" : point.strength.toFixed(2);
  return "(" + point.x + ", " + point.y + ") · RGB " + point.rgb.join("/") +
    " · 亮度 " + point.brightness.toFixed(2) + " · 强度 " + strength + " · " + evidence;
}

function show() {
  const {card, result} = state;
  get("workspace").hidden = false;
  get("empty").hidden = true;
  get("origin").textContent = (card.synthetic ? "合成练习图" : "导入原片") + " · 修订 " + card.revision;
  get("card-title").textContent = card.name;
  get("dimensions").textContent = card.width + " × " + card.height + " px · " + card.photo_name;
  get("name").value = card.name;
  for (const field of settings) field.value = card.settings[field.dataset.setting];
  get("probe-x").max = card.width - 1;
  get("probe-y").max = card.height - 1;
  get("probe-x").value = state.probe?.x ?? Math.round((card.settings.left + card.settings.right) / 2);
  get("probe-y").value = state.probe?.y ?? result.focus;
  get("probe-result").textContent = state.probe ? pointLabel(state.probe) : "选择原片像素";
  const reading = result.reading;
  get("direction-value").textContent = reading ? reading.direction.toFixed(0) : "—";
  get("direction-unit").textContent = "°";
  get("measurement-state").textContent = "原片 Y " + result.focus;
  get("selected-level").textContent = reading
    ? "主要箱 " + reading.dominant + " 点 · 有证 " + reading.qualified + " / " + reading.samples
    : "本行没有足够的方向证据";
  get("area-level").textContent = "全框 " + result.qualified + " 个源像素有方向证据";
  for (const [id, filename] of Object.entries({proof: "proof.png", csv: "profile.csv", zip: "observation.zip"})) {
    get(id).href = "/hatchproof" + route("/export/" + filename) + savedQuery();
  }
  paintSource();
  paintChart();
}

async function open(card) {
  const base = "/cards/" + card.id;
  const photo = new Image();
  photo.src = "/hatchproof" + base + "/capture.png";
  const [result] = await Promise.all([api(base + "/measurement?revision=" + card.revision), photo.decode()]);
  Object.assign(state, {card, result, photo, probe: null});
  get("library").value = card.id;
  show();
}

async function probe(x, y) {
  state.probe = await api(route("/probe") + savedQuery() + "&x=" + x + "&y=" + y);
  get("probe-x").value = x;
  get("probe-y").value = y;
  get("probe-result").textContent = pointLabel(state.probe);
  paintSource();
}

get("practice").addEventListener("click", () => action(async () => {
  await open(await api("/practice", {method: "POST"}));
  await library();
}));

get("library").addEventListener("change", () => {
  if (get("library").value) action(async () => open(await api("/cards/" + get("library").value)));
});
get("open-import").addEventListener("click", () => {
  notice("", "import-notice");
  get("import").showModal();
});
get("cancel-import").addEventListener("click", () => get("import").close());
get("upload").addEventListener("submit", (event) => {
  event.preventDefault();
  action(async () => {
    const card = await api("/cards", {method: "POST", body: new FormData(event.target)});
    await open(card);
    await library();
    get("import").close();
    event.target.reset();
  }, "import-notice");
});
document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
  state.mode = button.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach((item) =>
    item.setAttribute("aria-pressed", String(item === button)));
}));
get("capture").addEventListener("click", (event) => {
  if (!state.card) return;
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const x = Math.max(0, Math.min(canvas.width - 1, Math.floor((event.clientX - rect.left) * canvas.width / rect.width)));
  const y = Math.max(0, Math.min(canvas.height - 1, Math.floor((event.clientY - rect.top) * canvas.height / rect.height)));
  action(async () => {
    await probe(x, y);
    if (state.mode === "mark") {
      settings.find((field) => field.dataset.setting === "focus").value = y;
      notice("已填入实际原片截线。");
    }
  });
});
get("probe-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(() => probe(get("probe-x").value, get("probe-y").value));
});
get("calibration").addEventListener("submit", (event) => {
  event.preventDefault();
  action(async () => {
    const fields = Object.fromEntries(settings.map((field) => [
      field.dataset.setting, Number(field.value),
    ]));
    const card = await api(route(""), {
      method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({revision: state.card.revision, name: get("name").value, settings: fields}),
    });
    await open(card);
    await library();
  });
});
get("prepare").addEventListener("click", () => action(async () => {
  const {url} = await api(route("/prepare") + savedQuery(), {method: "POST"});
  location.assign(url);
}));
document.querySelectorAll("[data-chart]").forEach((button) => button.addEventListener("click", () => {
  state.chart = button.dataset.chart;
  document.querySelectorAll("[data-chart]").forEach((item) =>
    item.setAttribute("aria-pressed", String(item === button)));
  if (state.card) paintChart();
}));
action(library);
