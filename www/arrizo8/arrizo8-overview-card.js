/* Arrizo 8 owner dashboard v1. No network calls to Chery; reads HA state only. */
const FIELD_LABELS = {
  reportTime: "车辆上报时间",
  fetchTime: "HA 上次成功读取时间",
  expiry: "登录凭证到期时间",
  range: "剩余续航",
  fuel: "剩余油量",
  odometer: "总里程",
  consumption: "平均油耗",
  lock: "车锁状态",
  frontLeftDoor: "左前门",
  frontRightDoor: "右前门",
  backLeftDoor: "左后门",
  backRightDoor: "右后门",
  trunk: "后备厢门",
  hood: "机盖",
  frontLeftWindow: "左前车窗",
  frontRightWindow: "右前车窗",
  backLeftWindow: "左后车窗",
  backRightWindow: "右后车窗",
  sunroof: "天窗状态",
  air: "空调状态",
  leftTemp: "左侧空调温度",
  rightTemp: "右侧空调温度",
  frontLeftPressure: "左前胎压",
  frontRightPressure: "右前胎压",
  backLeftPressure: "左后胎压",
  backRightPressure: "右后胎压",
  location: "位置",
};

const DOORS = ["frontLeftDoor", "frontRightDoor", "backLeftDoor", "backRightDoor", "trunk"];
const WINDOWS = ["frontLeftWindow", "frontRightWindow", "backLeftWindow", "backRightWindow"];
// Coordinates are measured against the original 1200 px wide, 1520 px tall car viewport.
// Open/Close in the asset names describes the DOOR position, not the glass state.
// Glass1 matches the sedan/1_***** car images. Closed windows need no overlay.
const WINDOW_ART = {
  frontLeftWindow: { side: "leftFront", door: "frontLeftDoor", closedDoor: [342, 465, 54], openDoor: [85, 465, 256] },
  frontRightWindow: { side: "rightFront", door: "frontRightDoor", closedDoor: [805, 465, 54], openDoor: [850, 465, 250] },
  backLeftWindow: { side: "leftBack", door: "backLeftDoor", closedDoor: [342, 795, 52], openDoor: [0, 795, 276] },
  backRightWindow: { side: "rightBack", door: "backRightDoor", closedDoor: [810, 795, 50], openDoor: [865, 795, 275] },
};
const UNKNOWN = new Set(["unknown", "unavailable", "none", "null", ""]);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

class Arrizo8OverviewCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._resolved = {};
    this._locationDialog = null;
  }

  setConfig(config) {
    this._config = { image_base: "/local/arrizo8", entities: {}, ...config };
    this._resolved = {};
    if (this._hass) this._render();
  }

  set hass(value) {
    this._hass = value;
    this._render();
  }

  disconnectedCallback() { this._locationDialog?.remove(); this._locationDialog = null; }

  getCardSize() { return 12; }

  _find(key) {
    const direct = this._config.entities?.[key];
    if (direct) return this._hass.states[direct] ? direct : null;
    if (this._resolved[key] && this._hass.states[this._resolved[key]]) return this._resolved[key];
    const label = FIELD_LABELS[key];
    const domain = key === "location" ? "device_tracker." : "sensor.";
    const candidates = Object.entries(this._hass.states).filter(([id, state]) => {
      if (!id.startsWith(domain)) return false;
      const name = state.attributes.friendly_name || "";
      if (!name.includes("艾瑞泽8")) return false;
      return new RegExp("(?:^|\\s)(?:\\d{2}\\s*)?" + label.replace(/[.*+?^$\{\}()|[\]\\]/g, "\\$&") + "$").test(name);
    });
    if (candidates.length === 1) {
      this._resolved[key] = candidates[0][0];
      return candidates[0][0];
    }
    if (key === "location") {
      // The tracker can be renamed in HA. Its integration entity id is a safer
      // fallback than silently ignoring a click when the friendly name changes.
      const trackers = Object.entries(this._hass.states).filter(([id, state]) =>
        id.startsWith("device_tracker.") &&
        Number.isFinite(Number(state.attributes.latitude)) &&
        Number.isFinite(Number(state.attributes.longitude)));
      const matches = [
        trackers.filter(([id, state]) => /arrizo.?8|chery|airuize/i.test(id) || /艾瑞泽8|奇瑞汽车/.test(state.attributes.friendly_name || "")),
        trackers.filter(([, state]) => /(?:^|\s)(?:\d{2}\s*)?位置$/.test(state.attributes.friendly_name || "")),
      ];
      for (const group of matches) if (group.length === 1) {
        this._resolved[key] = group[0][0];
        return group[0][0];
      }
    }
    return null;
  }

  _state(key) {
    const entity = this._find(key);
    return entity ? this._hass.states[entity] : null;
  }

  _value(key) {
    const value = this._state(key)?.state;
    return value && !UNKNOWN.has(String(value).toLowerCase()) ? value : null;
  }

  _number(key) {
    const value = this._value(key);
    if (value == null) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  _status(key) {
    const value = this._value(key);
    return value == null ? "未知" : String(value);
  }

  _open(key) {
    const status = this._status(key);
    if (status === "未知") return null;
    if (["开启", "已解锁", "运行", "通风", "完全开启", "翘起"].includes(status)) return true;
    if (["关闭", "已锁", "熄火"].includes(status)) return false;
    return null;
  }

  _summary(keys) {
    const values = keys.map((key) => this._open(key));
    const open = values.filter((value) => value === true).length;
    const unknown = values.filter((value) => value === null).length;
    if (open) return `开启 ${open} 处${unknown ? " · 部分未知" : ""}`;
    if (unknown) return "状态未知";
    return "已关";
  }

  _reading(key, unit = "") {
    const number = this._number(key);
    return number == null ? "—" : `${Math.round(number).toLocaleString("zh-CN")}${unit}`;
  }

  _date(key) {
    const value = this._value(key);
    if (!value) return "暂无";
    if (/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d/.test(value) && !/[Z+]\d*$/.test(value)) {
      return value.slice(0, 16).replace("T", " ");
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 20);
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(date);
  }

  _carImage() {
    const values = DOORS.map((key) => this._open(key));
    const unknown = values.some((value) => value === null);
    const bits = values.map((value) => value === true ? "1" : "0").join("");
    return { url: `${this._config.image_base}/status/sedan/1_${bits}.png`, unknown, bits };
  }

  _pressure(position) {
    const pressure = this._number(position + "Pressure");
    return pressure == null
      ? '<div class="tyre-val"><strong>—</strong></div>'
      : `<div class="tyre-val"><strong>${Math.round(pressure)}<span>kPa</span></strong></div>`;
  }

  _windowLayers(imgBase) {
    return WINDOWS.map((key) => {
      const art = WINDOW_ART[key];
      const doorOpen = this._open(art.door);
      if (doorOpen === null) return "";
      if (this._open(key) !== true) return "";
      const [x, y, width] = doorOpen ? art.openDoor : art.closedDoor;
      const filename = `${art.side}${doorOpen ? "Open" : "Close"}Glass1.png`;
      return `<img class="window-layer"
        src="${imgBase}/status/overlays/${filename}"
        style="left:${(x / 1200 * 100).toFixed(3)}%;top:${(y / 1520 * 100).toFixed(3)}%;width:${(width / 1200 * 100).toFixed(3)}%"
        alt="">`;
    }).join("");
  }

  _render() {
    if (!this._hass || !this.shadowRoot) return;
    const car = this._carImage();
    const fuel = this._number("fuel");
    const fuelWidth = fuel == null ? 0 : Math.max(0, Math.min(100, fuel));
    const lock = this._status("lock");
    const temp = this._number("leftTemp") ?? this._number("rightTemp");
    const air = this._status("air");
    const imgBase = esc(this._config.image_base);
    const hoodOpen = this._open("hood");
    const sunroofState = this._status("sunroof");
    const sunroofImage = sunroofState === "开启" ? "1_T6.png" :
      sunroofState === "翘起" ? "1_T1.png" : null;
    this.shadowRoot.innerHTML = `
      <style>${Arrizo8OverviewCard.css}</style>
      <ha-card>
        <div class="canvas" style="--sky:url('${imgBase}/backgrounds/car_position_0.png')">
          <div class="left-column">
          <div class="header">
            <div class="eyebrow">艾瑞泽8 <span>2022款 雅</span></div>
            <div class="topline">
              <div><div class="range">${this._reading("range")}<small> km</small></div></div>
              <div class="lock ${lock === "已解锁" ? "unlocked" : ""}">${esc(lock)}</div>
            </div>
            <div class="fuelrow"><span>油 ${this._reading("fuel", "%")}</span><div class="fuelbar"><i style="width:${fuelWidth}%"></i></div></div>
          </div>

          <div class="vehicle">
            <div class="tyres left">
              ${this._pressure("frontLeft")}
              ${this._pressure("backLeft")}
            </div>
            <div class="car-frame">
              <img class="car" src="${esc(car.url)}" alt="车辆俯视图，车门及后备厢按状态切换">
              ${sunroofImage ? `<img class="roof-layer" src="${imgBase}/status/sedan/${sunroofImage}" alt="">` : ""}
              ${this._windowLayers(imgBase)}
              <span class="tire-mark fl"></span><span class="tire-mark fr"></span>
              <span class="tire-mark bl"></span><span class="tire-mark br"></span>
              ${hoodOpen === true ? `<img class="hood-layer" src="${imgBase}/status/overlays/frontEngineUrl1.png" alt="机盖开启">` : ""}
            </div>
            <div class="tyres right">
              ${this._pressure("frontRight")}
              ${this._pressure("backRight")}
            </div>
          </div>
          ${car.unknown ? '<div class="image-note">部分车门状态未知，对应车窗图层暂不显示</div>' : ""}
          </div>

          <div class="right-column">
          <div class="info-pair">
            <div class="glass-panel climate">
              <div class="panel-label"><span class="icon">✳</span> 智能空调</div>
              <div class="panel-main">${esc(air)} ${temp == null ? "" : `<span>· ${Math.round(temp)}°C</span>`}</div>
              <div class="panel-sub">仅显示车况，暂不控制</div>
            </div>
            <div class="glass-panel location" id="location-panel" role="button" tabindex="0" aria-label="打开车辆地图">
              <div class="map-host" style="background-image:url('${imgBase}/backgrounds/map-preview.svg')" aria-hidden="true"></div>
              <span class="map-nav" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m21 3-8.2 18-2.2-7.6L3 11.2 21 3Z"/><path d="m10.6 13.4 4.3-4.3"/></svg></span>
            </div>
          </div>

          <div class="timestamps">
            <div><span>车辆上报</span><strong>${esc(this._date("reportTime"))}</strong></div>
            <div><span>登录凭证到期</span><strong>${esc(this._date("expiry"))}</strong></div>
          </div>

          <div class="glass-panel status-panel">
            <div class="section-heading">车辆状态</div>
            <div class="status-grid">
              <div><span>车门</span><strong>${esc(this._summary(DOORS.slice(0, 4)))}</strong></div>
              <div><span>车窗</span><strong>${esc(this._summary(WINDOWS))}</strong></div>
              <div><span>天窗</span><strong>${esc(this._status("sunroof"))}</strong></div>
              <div><span>后备厢</span><strong>${esc(this._status("trunk"))}</strong></div>
              <div><span>前车盖</span><strong>${esc(this._status("hood"))}</strong></div>
            </div>
          </div>

          <div class="glass-panel metrics">
            <div><span>总行驶里程</span><strong>${this._reading("odometer", " km")}</strong></div>
            <div><span>平均油耗</span><strong>${this._reading("consumption", " L/100km")}</strong></div>
          </div>
          </div>
        </div>
      </ha-card>`;
    const panel = this.shadowRoot.getElementById("location-panel");
    panel?.addEventListener("click", () => this._openLocationInfo());
    panel?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this._openLocationInfo(); }
    });
  }

  _openLocationInfo() {
    if (this._locationDialog?.open) return;
    const entityId = this._find("location");
    this._locationDialog?.remove();
    const dialog = document.createElement("dialog");
    dialog.setAttribute("aria-label", "车辆地图");
    dialog.style.cssText = "width:min(900px,calc(100vw - 32px));max-height:calc(100vh - 32px);padding:0;border:0;border-radius:16px;box-shadow:0 24px 80px #0005;overflow:hidden;background:#fff;color:#222";
    const header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;padding:14px 18px;font:500 18px -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif";
    const title = document.createElement("span");
    title.textContent = "车辆位置";
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "关闭";
    close.style.cssText = "border:0;background:#edf2f5;border-radius:8px;padding:7px 13px;font:inherit;cursor:pointer";
    close.addEventListener("click", () => dialog.close());
    header.append(title, close);
    const mapHost = document.createElement("div");
    mapHost.style.cssText = "position:relative;height:min(65vh,620px);min-height:300px;overflow:hidden;background:#e8eff1;display:flex;align-items:center;justify-content:center";
    mapHost.textContent = "地图正在加载…";
    dialog.append(header, mapHost);
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", () => { dialog.remove(); if (this._locationDialog === dialog) this._locationDialog = null; });
    document.body.append(dialog);
    this._locationDialog = dialog;
    dialog.showModal();
    if (!entityId) {
      mapHost.textContent = "未找到车辆位置实体。请在卡片配置中指定 location 对应的 device_tracker 实体。";
      return;
    }
    const attrs = this._hass.states[entityId]?.attributes || {};
    const latitude = attrs.latitude;
    const longitude = attrs.longitude;
    if (typeof latitude !== "number" || typeof longitude !== "number" ||
        !Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      mapHost.textContent = "车辆位置实体目前没有有效经纬度，请先在 HA 地图中确认车辆定位。";
      return;
    }
    // Give the embedded map an explicit bounding box. This avoids the HA map
    // component's fallback city and the context loop seen in a nested dialog.
    const halfLat = 0.0035;
    const halfLon = 0.006 / Math.max(Math.cos(latitude * Math.PI / 180), 0.25);
    const bbox = [longitude - halfLon, latitude - halfLat,
      longitude + halfLon, latitude + halfLat].map((n) => n.toFixed(6)).join(",");
    const params = new URLSearchParams({ bbox, layer: "mapnik",
      marker: `${latitude.toFixed(6)},${longitude.toFixed(6)}` });
    const mapUrl = `https://www.openstreetmap.org/export/embed.html?${params}`;
    const makeFrame = () => {
      const frame = document.createElement("iframe");
      frame.title = "车辆位置地图";
      frame.referrerPolicy = "no-referrer";
      frame.style.cssText = "display:block;width:100%;height:100%;border:0";
      frame.src = mapUrl;
      return frame;
    };
    const returnButton = document.createElement("button");
    returnButton.type = "button";
    returnButton.innerHTML = '<svg viewBox="0 0 24 24" width="23" height="23" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/></svg>';
    returnButton.setAttribute("aria-label", "返回车辆位置");
    returnButton.title = "返回车辆位置";
    returnButton.style.cssText = "position:absolute;right:7px;top:78px;z-index:1;display:grid;place-items:center;width:36px;height:36px;border:0;border-radius:50%;padding:0;background:#b6ddeb;color:#14202a;box-shadow:0 2px 9px #0002;cursor:pointer";
    returnButton.addEventListener("click", () => {
      const currentFrame = mapHost.querySelector("iframe");
      currentFrame?.replaceWith(makeFrame());
    });
    mapHost.replaceChildren(makeFrame(), returnButton);
  }
}

Arrizo8OverviewCard.css = `
  :host { display:block; width:100%; container-type:inline-size; }
  ha-card { display:block; width:100%; margin:0; border:0; border-radius:0; overflow:hidden; background:transparent; box-shadow:none; }
  .canvas { box-sizing:border-box; width:100%; min-height:100%; padding:30px clamp(22px,4vw,64px) 34px; color:#171717; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.4; background-image:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.48) 78%,rgba(250,252,255,.72)),var(--sky); background-size:cover; background-position:center top; }
  .left-column,.right-column { min-width:0; }
  .eyebrow { font-size:17px; font-weight:500; letter-spacing:0; color:#222; }
  .eyebrow span { margin-left:6px; font-size:13px; color:#666; font-weight:400; }
  .topline { display:flex; justify-content:space-between; align-items:flex-start; margin-top:20px; gap:16px; }
  .range { font-size:66px; line-height:1.1; letter-spacing:-1.5px; font-weight:400; font-variant-numeric:tabular-nums; }
  .range small { margin-left:4px; font-size:19px; letter-spacing:0; font-weight:400; }
  .lock { margin-top:6px; flex:none; background:rgba(255,255,255,.65); padding:7px 14px; border-radius:999px; font-size:14px; font-weight:400; }
  .lock.unlocked { color:#b34149; }
  .fuelrow { margin-top:16px; display:flex; gap:14px; align-items:center; font-size:17px; }
  .fuelbar { width:116px; height:7px; background:rgba(49,75,111,.13); border-radius:99px; overflow:hidden; }
  .fuelbar i { display:block; height:100%; background:#5bb9dc; border-radius:inherit; }
  .vehicle { display:grid; grid-template-columns:minmax(0,.9fr) minmax(0,2.2fr) minmax(0,.9fr); align-items:stretch; gap:2px; margin:28px 0 0; }
  .car-frame { position:relative; width:100%; aspect-ratio:1200/1520; overflow:hidden; filter:drop-shadow(0 12px 10px rgba(23,36,55,.18)); }
  .car { display:block; width:100%; height:auto; }
  .tyres { display:flex; flex-direction:column; justify-content:space-around; padding:19% 6px 14%; position:relative; z-index:1; }
  .tyres.right { text-align:right; }
  .tyre-val strong { display:block; font-size:clamp(20px,2vw,28px); line-height:1.12; font-weight:400; white-space:nowrap; font-variant-numeric:tabular-nums; letter-spacing:-.4px; }
  .tyre-val strong span { display:inline-block; margin-left:5px; font-size:.58em; font-weight:400; letter-spacing:0; vertical-align:baseline; }
  .roof-layer { position:absolute; inset:0; display:block; width:100%; height:auto; pointer-events:none; z-index:2; }
  .window-layer { position:absolute; display:block; height:auto; pointer-events:none; z-index:3; }
  .window-layer { opacity:.8; }
  .hood-layer { position:absolute; top:2%; left:28%; width:44%; height:auto; opacity:.7; z-index:3; pointer-events:none; }
  .tire-mark { position:absolute; z-index:4; width:14%; height:17%; border-radius:10px; background:rgba(52,178,228,.43); box-shadow:0 0 9px rgba(42,170,216,.1); }
  .tire-mark.fl { top:26%; left:20%; }.tire-mark.fr { top:26%; right:20%; }
  .tire-mark.bl { top:67%; left:20%; }.tire-mark.br { top:67%; right:20%; }
  .image-note { margin:0 0 7px; text-align:center; color:#9a4c42; font-size:11px; }
  .info-pair { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:2px; }
  .glass-panel { background:rgba(255,255,255,.74); border-radius:16px; }
  .info-pair .glass-panel { min-height:132px; padding:18px 20px; box-sizing:border-box; overflow:hidden; }
  .panel-label { font-size:17px; font-weight:500; display:flex; gap:8px; align-items:center; }
  .icon { font-size:21px; line-height:1; color:#4b7597; }
  .panel-main { font-size:22px; margin-top:14px; font-weight:400; }
  .panel-main span { font-size:17px; }
  .panel-sub { margin-top:6px; font-size:12px; color:#777; }
  .location { position:relative; cursor:pointer; padding:0 !important; }
  .location:focus-visible { outline:2px solid #3ba9d5; }
  .map-host { position:absolute; inset:0; background-color:#f5f6f5; background-position:center; background-size:cover; pointer-events:none; }
  .map-nav { position:absolute; z-index:1; top:13px; right:13px; width:40px; height:40px; border-radius:50%; display:grid; place-items:center; color:#222; background:rgba(255,255,255,.88); box-shadow:0 2px 12px #0001; pointer-events:none; }
  .map-nav svg { width:24px; height:24px; }
  .timestamps { display:flex; justify-content:center; gap:14px; flex-wrap:wrap; margin:23px 0; font-size:12px; color:#777; }
  .timestamps div { display:flex; gap:5px; }.timestamps strong { color:#555; font-weight:400; }
  .status-panel { padding:22px 18px 24px; }
  .section-heading { font-size:19px; font-weight:500; margin:0 0 18px 2px; }
  .status-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); }
  .status-grid > * { text-align:center; border-right:1px solid rgba(102,123,150,.18); }
  .status-grid > *:last-child { border-right:none; }
  .status-grid span,.status-grid strong { display:block; }
  .status-grid span { font-size:15px; color:#252525; }
  .status-grid strong { font-size:14px; font-weight:400; color:#777; margin-top:11px; min-height:20px; }
  .metrics { padding:4px 22px; margin-top:14px; }
  .metrics > div { display:flex; align-items:center; justify-content:space-between; padding:20px 2px; font-size:16px; }
  .metrics > div + div { border-top:1px solid rgba(91,113,136,.14); }
  .metrics strong { font-size:17px; font-weight:400; font-variant-numeric:tabular-nums; }
  @container (min-width: 1050px) {
    .canvas { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(450px,.8fr); align-items:center; gap:clamp(36px,4vw,76px); min-height:calc(100dvh - 88px); padding-top:20px; padding-bottom:20px; }
    .left-column { width:100%; max-width:850px; margin:auto; }
    .right-column { width:100%; max-width:690px; margin:auto; }
    .vehicle { max-width:min(680px,75dvh); margin:8px auto 0; }
    .tyres.left { text-align:right; padding-right:17px; }
    .tyres.right { text-align:left; padding-left:17px; }
    .info-pair { grid-template-columns:1fr 1fr; }
    .info-pair .glass-panel { min-height:180px; }
    .timestamps { justify-content:flex-start; margin:17px 0; }
  }
  @media(max-width:480px) {
    .canvas { padding:17px 18px 18px; }
    .eyebrow { font-size:15px; }
    .topline { margin-top:12px; }
    .range { font-size:54px; }
    .fuelrow { margin-top:8px; }
    .vehicle { margin:12px 0 0; grid-template-columns:minmax(0,1fr) minmax(0,2.2fr) minmax(0,1fr); }
    .tyres { padding-left:2px; padding-right:2px; }
    .tyre-val strong { font-size:24px; }.tyre-val strong span { font-size:13px; margin-left:3px; }
    .info-pair { gap:9px; }.info-pair .glass-panel { padding:10px; min-height:150px; }
    .panel-label { font-size:13px; }.panel-main { font-size:18px; }
    .map-nav { width:34px; height:34px; top:9px; right:9px; }
    .map-nav svg { width:21px; height:21px; }
    .status-panel { padding:12px 10px 13px; }.status-grid span,.status-grid strong { font-size:12px; }
    .section-heading { font-size:16px; margin-bottom:11px; }
    .metrics { margin-top:8px; }.metrics > div { padding:12px 2px; }
    .timestamps { gap:3px; flex-direction:column; align-items:center; margin:10px 0; }
  }
  @media(max-width:350px) {
    .tyre-val strong { font-size:16px; }.tyre-val strong span { font-size:10px; }
    .vehicle { grid-template-columns:minmax(0,1fr) minmax(0,2fr) minmax(0,1fr); }
    .status-grid span,.status-grid strong { font-size:10px; }
  }
  @media(max-width:480px) and (max-height:850px) {
    .canvas { padding-top:8px; padding-bottom:8px; }
    .vehicle { max-width:295px; margin:5px auto 0; }
    .info-pair .glass-panel { min-height:125px; padding:8px 10px; }
    .panel-main { margin-top:8px; }
    .status-panel { padding-top:9px; padding-bottom:10px; }
    .metrics > div { padding:7px 2px; }
    .timestamps { margin:7px 0; }
  }
  @media(max-width:480px) and (max-height:750px) {
    .canvas { padding-top:5px; padding-bottom:5px; }
    .eyebrow { font-size:13px; }.topline { margin-top:6px; }
    .range { font-size:46px; }.fuelrow { margin-top:3px; font-size:14px; }
    .vehicle { max-width:270px; margin:3px auto 0; }
    .tyre-val strong { font-size:17px; }
    .info-pair .glass-panel { min-height:108px; }
    .panel-sub { font-size:10px; margin-top:2px; }
    .status-panel { padding-top:7px; padding-bottom:8px; }
    .section-heading { margin-bottom:6px; }
    .metrics > div { padding:6px 2px; }
  }
`;

customElements.define("arrizo8-overview-card", Arrizo8OverviewCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "arrizo8-overview-card",
  name: "艾瑞泽8俯视车况",
  description: "白色艾瑞泽8的动态俯视车况卡片",
});
