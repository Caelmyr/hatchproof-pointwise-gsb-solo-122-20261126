"use strict";

const get = (id) => document.getElementById(id);
const state = {card: null, result: null, photo: null, probe: null, mode: "probe", chart: "profile",
  busy: false, widthReport: null, widthIndex: 0, adoptedWidth: null};
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
  const controls = [...document.querySelectorAll("button, select")];
  const wasDisabled = new Set(controls.filter((node) => node.disabled));
  controls.forEach((node) => { node.disabled = true; });
  notice("", target);
  try {
    await work();
  } catch (error) {
    notice(error.message, target);
  } finally {
    state.busy = false;
    controls.forEach((node) => { node.disabled = wasDisabled.has(node); });
    const candidateSelect = get("width-candidate");
    if (candidateSelect && state.card) {
      candidateSelect.disabled = !state.widthReport?.candidates?.length;
    }
  }
}

async function library() {
  const {cards} = await api("/cards");
  const select = get("library");
  select.replaceChildren(new Option("选取已存卡片", ""));
  for (const card of cards) select.append(new Option(card.name, card.id));
  select.value = state.card?.id || "";
}

function activeWidthCandidate() {
  if (state.adoptedWidth) return state.adoptedWidth;
  return state.widthReport?.candidates?.[state.widthIndex] || null;
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
    ctx.lineWidth = 2;
    ctx.strokeRect(probe.x-5,probe.y-5,10,10);
  }
  const widthReport = state.widthReport;
  if (widthReport?.candidates?.length) {
    ctx.fillStyle = "rgba(111, 231, 190, .75)";
    for (const candidate of widthReport.candidates) {
      ctx.beginPath();
      ctx.arc(candidate.tangent.x,candidate.tangent.y,1.7,0,Math.PI*2);
      ctx.fill();
    }
  }
  const cut = activeWidthCandidate();
  if (cut && widthReport) {
    const [paperA, paperB] = cut.paper;
    const [endA, endB] = cut.ends;
    ctx.lineCap = "round";
    ctx.strokeStyle = state.adoptedWidth ? "#65f0c0" : "rgba(101, 240, 192, .72)";
    ctx.lineWidth = state.adoptedWidth ? 2.4 : 1.6;
    ctx.setLineDash([7,5]);
    ctx.beginPath();
    ctx.moveTo(paperA.x,paperA.y);
    ctx.lineTo(paperB.x,paperB.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = "#ffd166";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(endA.x,endA.y);
    ctx.lineTo(endB.x,endB.y);
    ctx.stroke();
    for (const [point, label] of [[endA,"A"],[endB,"B"]]) {
      ctx.fillStyle = "#4a2f14";
      ctx.strokeStyle = "#ffd166";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(point.x,point.y,5.5,0,Math.PI*2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#fff4cf";
      ctx.font = "bold 11px monospace";
      ctx.fillText(label,point.x+7,point.y-7);
    }
    ctx.strokeStyle = "#55c7ff";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cut.tangent.x,cut.tangent.y,3.5,0,Math.PI*2);
    ctx.stroke();
  }
}

function paintWidthChart(ctx, width, height) {
  ctx.canvas.style.cursor = "crosshair";
  ctx.canvas.setAttribute("aria-label", "斜截笔宽的真实原像素证据；点击可点读对应原片像素");
  get("chart-title").textContent = "斜截笔宽 · 实际原像素";
  get("chart-caption").textContent = "法线投影 px · 点图表可点读原片 RGB";
  ctx.fillStyle = "#faf8fb";
  ctx.fillRect(0,0,width,height);
  const cut = state.adoptedWidth || activeWidthCandidate();
  if (!cut?.profile?.length) {
    ctx.fillStyle = "#68576e";
    ctx.font = "14px sans-serif";
    ctx.fillText("先测量笔宽，再采用一道可量横切。",58,78);
    return;
  }
  const profile = cut.profile;
  const projections = profile.map((p) => p.projection);
  const lo = Math.min(...projections) - 1;
  const hi = Math.max(...projections) + 1;
  const xAt = (p) => 51 + (width - 88) * (p - lo) / Math.max(0.001, hi - lo);
  const yAt = (b) => height - 26 - (height - 46) * b / 255;
  ctx.font = "12px monospace";
  ctx.strokeStyle = "#e2d9e7";
  ctx.fillStyle = "#4e4260";
  for (const level of [0,128,255]) {
    ctx.fillText(level,8,yAt(level)+3);
    ctx.beginPath(); ctx.moveTo(xAt(lo),yAt(level)); ctx.lineTo(xAt(hi),yAt(level)); ctx.stroke();
  }
  ctx.fillText(lo.toFixed(1),xAt(lo)-8,height-7);
  ctx.fillText("0",xAt(0)-3,height-7);
  ctx.fillText(hi.toFixed(1),xAt(hi)-18,height-7);
  ctx.strokeStyle = "#8d68a9";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  profile.forEach((p,index) => {
    const x=xAt(p.projection), y=yAt(p.brightness);
    if (index === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();
  for (const p of profile) {
    const x=xAt(p.projection), y=yAt(p.brightness);
    ctx.fillStyle = `rgb(${p.rgb[0]},${p.rgb[1]},${p.rgb[2]})`;
    ctx.fillRect(x-3,y-3,6,6);
    ctx.strokeStyle = p.role === "ink_end" ? "#d97706" : "#4e4260";
    ctx.lineWidth = p.role === "ink_end" ? 2 : 0.8;
    ctx.strokeRect(x-3,y-3,6,6);
  }
  const [a,b] = cut.ends;
  ctx.fillStyle = "#7c2d12";
  ctx.font = "bold 12px sans-serif";
  ctx.fillText(`A (${a.x},${a.y})`,xAt(a.projection)-20,18);
  ctx.fillText(`B (${b.x},${b.y})`,xAt(b.projection)-20,18);
  ctx.fillStyle = "#4e4260";
  ctx.font = "12px monospace";
  ctx.fillText(`width ${cut.width.toFixed(2)} px · click a pixel`,58,36);
}

function paintChart() {
  const canvas = get("chart");
  const ctx = canvas.getContext("2d");
  const {width,height} = canvas;
  if (state.chart === "width") {
    paintWidthChart(ctx, width, height);
    return;
  }
  canvas.style.cursor = "default";
  canvas.setAttribute("aria-label", "截线方向与全框分布");
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
  const evidence = point.direction == null ? "无方向证据" : point.direction.toFixed(2) + "°";
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
  get("width-x").max = card.width - 1;
  get("width-y").max = card.height - 1;
  get("width-reach").max = Math.max(card.width, card.height) * 2;
  if (!state.widthReport) {
    get("width-x").value = "";
    get("width-y").value = "";
  }
  get("probe-x").value = state.probe?.x ?? Math.round((card.settings.left + card.settings.right) / 2);
  get("probe-y").value = state.probe?.y ?? result.focus;
  get("probe-result").textContent = state.probe ? pointLabel(state.probe) : "选择原片像素";
  const reading = result.reading;
  if (!state.widthReport) {
    get("width-angle").value = reading ? reading.direction : 0;
  }
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
  renderWidthReport();
  paintSource();
  paintChart();
}

async function open(card) {
  const base = "/cards/" + card.id;
  const photo = new Image();
  photo.src = "/hatchproof" + base + "/capture.png";
  const [result] = await Promise.all([api(base + "/measurement?revision=" + card.revision), photo.decode()]);
  Object.assign(state, {card, result, photo, probe: null, widthReport: null,
    widthIndex: 0, adoptedWidth: null, chart: "profile"});
  document.querySelectorAll("[data-chart]").forEach((item) =>
    item.setAttribute("aria-pressed", String(item.dataset.chart === "profile")));
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

const widthReasons = {
  origin_missing: "原点原像素缺失，不能补点；请改点另一处墨内位置。",
  origin_not_ink: "原点亮度高于黑墨上限，或该原像素缺失；请点在墨内。",
  no_measurable_crosscut: "没有找到两端外紧邻都是合格亮纸点的连续墨段。",
  outside_frame: "横切会落到框外，不能补点。",
  missing_original: "该处原照像素缺失，不能补点。",
  paper_not_clear: "墨段外第一点不够亮，或含 0/255 截断通道。",
};

async function requestWidth() {
  if (get("width-x").value === "" || get("width-y").value === "") {
    throw new Error("请先在原片点一个墨内原点。");
  }
  const x = Number(get("width-x").value);
  const y = Number(get("width-y").value);
  const params = new URLSearchParams({
    revision: String(state.card.revision),
    x: String(x), y: String(y),
    angle: get("width-angle").value,
    reach: get("width-reach").value,
    ink_limit: get("width-ink").value,
  });
  state.widthReport = await api(route("/width") + "?" + params.toString());
  state.widthIndex = 0;
  state.adoptedWidth = null;
  renderWidthReport();
  paintSource();
  if (state.chart === "width") paintChart();
}

function renderWidthReport() {
  const report = state.widthReport;
  const select = get("width-candidate");
  const result = get("width-result");
  const adopt = get("adopt-width");
  const actions = get("width-endpoint-actions");
  result.hidden = false;
  select.replaceChildren();
  if (!report) {
    select.disabled = true;
    select.append(new Option("尚未测量", ""));
    result.textContent = "用“量笔宽”在原片墨内点一下，再填笔向和上限。暗线一中断就停止，不会跳到另一笔。";
    adopt.hidden = true;
    actions.hidden = true;
    return;
  }
  if (!report.candidates?.length) {
    select.disabled = true;
    select.append(new Option("无可量横切", ""));
    result.textContent = widthReasons[report.reason] || ("无法测量：" + (report.reason || "未知原因"));
    adopt.hidden = true;
    actions.hidden = true;
    return;
  }
  select.disabled = false;
  report.candidates.forEach((candidate, index) => {
    select.append(new Option(
      `#${index + 1} · 距原点 ${candidate.distance.toFixed(1)} px · 宽 ${candidate.width.toFixed(2)} · 双侧对比 ${candidate.min_contrast.toFixed(1)}`,
      String(index)));
  });
  select.value = String(state.widthIndex);
  const cut = report.candidates[state.widthIndex];
  const prefix = state.widthIndex === 0 ? "兼顾近原点与双侧对比，推荐第 1 道：" : `正在查看第 ${state.widthIndex + 1} 道：`;
  result.textContent = prefix +
    `笔宽 ${cut.width.toFixed(2)} px；切点 (${cut.tangent.x}, ${cut.tangent.y})，` +
    `距原点 ${cut.distance.toFixed(1)} px；两端对比 ${cut.contrasts[0].toFixed(1)} / ${cut.contrasts[1].toFixed(1)}。`;
  adopt.hidden = false;
  actions.hidden = false;
}

function selectedWidthCandidate() {
  return state.adoptedWidth || state.widthReport?.candidates?.[state.widthIndex] || null;
}

function adoptWidth() {
  const cut = state.widthReport?.candidates?.[state.widthIndex];
  if (!cut) return;
  state.adoptedWidth = cut;
  state.chart = "width";
  document.querySelectorAll("[data-chart]").forEach((item) =>
    item.setAttribute("aria-pressed", String(item.dataset.chart === "width")));
  get("chart-title").scrollIntoView({block: "nearest", behavior: "smooth"});
  paintSource();
  paintChart();
  notice(`已采用：笔宽 ${cut.width.toFixed(2)} px。证据图已换成这道斜截的真实原像素；点击图中像素或下面按钮可点读两个真墨端。`,
    "width-result");
}

async function probeWidthEnd(which) {
  const cut = selectedWidthCandidate();
  if (!cut) return;
  const point = cut.ends[which === "a" ? 0 : 1];
  await probe(point.x, point.y);
  notice(`墨端 ${which.toUpperCase()}：(${point.x}, ${point.y}) · RGB ${point.rgb.join("/")}`, "width-result");
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
  let x = Math.max(0, Math.min(canvas.width - 1, Math.floor((event.clientX - rect.left) * canvas.width / rect.width)));
  let y = Math.max(0, Math.min(canvas.height - 1, Math.floor((event.clientY - rect.top) * canvas.height / rect.height)));
  if (state.mode === "width") {
    const cut = activeWidthCandidate();
    const endpoint = cut?.ends?.find((point) => Math.hypot(point.x - x, point.y - y) <= 7);
    if (endpoint) {
      x = endpoint.x;
      y = endpoint.y;
    }
  }
  action(async () => {
    await probe(x, y);
    get("width-x").value = x;
    get("width-y").value = y;
    if (state.mode === "mark") {
      settings.find((field) => field.dataset.setting === "focus").value = y;
      notice("已填入实际原片截线。");
    } else if (state.mode === "width") {
      notice(`已记录墨内原点 (${x}, ${y})；请确认笔向、最远距离和黑墨上限后测量。`, "width-result");
    }
  });
});
get("probe-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(() => probe(get("probe-x").value, get("probe-y").value));
});
get("width-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(requestWidth, "width-result");
});
get("width-candidate").addEventListener("change", (event) => {
  state.widthIndex = Number(event.target.value);
  state.adoptedWidth = null;
  paintSource();
  if (state.chart === "width") paintChart();
  renderWidthReport();
});
get("adopt-width").addEventListener("click", () => action(async () => adoptWidth(), "width-result"));
get("width-end-a").addEventListener("click", () => action(() => probeWidthEnd("a")));
get("width-end-b").addEventListener("click", () => action(() => probeWidthEnd("b")));
get("chart").addEventListener("click", (event) => {
  if (state.chart !== "width") return;
  const cut = activeWidthCandidate();
  if (!cut?.profile?.length) return;
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const cx = (event.clientX - rect.left) * canvas.width / rect.width;
  const projections = cut.profile.map((p) => p.projection);
  const lo = Math.min(...projections) - 1;
  const hi = Math.max(...projections) + 1;
  const projection = lo + (cx - 51) * (hi - lo) / Math.max(1, canvas.width - 88);
  const point = cut.profile.reduce((best, candidate) =>
    Math.abs(candidate.projection - projection) < Math.abs(best.projection - projection) ? candidate : best);
  action(() => probe(point.x, point.y));
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
