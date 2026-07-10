const form = document.querySelector("#searchForm");
const ipInput = document.querySelector("#ipInput");
const singleModeButton = document.querySelector("#singleModeButton");
const batchModeButton = document.querySelector("#batchModeButton");
const multiTools = document.querySelector("#multiTools");
const batchInput = document.querySelector("#batchInput");
const batchButton = document.querySelector("#batchButton");
const clearBatchButton = document.querySelector("#clearBatchButton");
const copyBatchButton = document.querySelector("#copyBatchButton");
const batchResults = document.querySelector("#batchResults");
const historyList = document.querySelector("#historyList");
const ipv4Value = document.querySelector("#ipv4Value");
const ipv6Value = document.querySelector("#ipv6Value");
const basicIp = document.querySelector("#basicIp");
const basicLocation = document.querySelector("#basicLocation");
const basicAsn = document.querySelector("#basicAsn");
const basicIsp = document.querySelector("#basicIsp");
const basicCoords = document.querySelector("#basicCoords");
const basicBroadcast = document.querySelector("#basicBroadcast");
const riskScore = document.querySelector("#riskScore");
const riskNeedle = document.querySelector("#riskNeedle");
const riskSummary = document.querySelector("#riskSummary");
const analysisBody = document.querySelector("#analysisBody");
const mapNote = document.querySelector("#mapNote");

const HISTORY_KEY = "ipgeosearch.history";
const MAX_HISTORY = 8;

const COUNTRY_CENTROIDS = {
  US: { lat: 39.5, lon: -98.35, label: "United States" },
  CN: { lat: 35.86, lon: 104.19, label: "中国" },
  HK: { lat: 22.32, lon: 114.17, label: "中国香港" },
  AU: { lat: -25.27, lon: 133.77, label: "Australia" },
  JP: { lat: 36.2, lon: 138.25, label: "Japan" },
  KR: { lat: 36.5, lon: 127.8, label: "South Korea" },
  IN: { lat: 20.59, lon: 78.96, label: "India" },
  SG: { lat: 1.35, lon: 103.82, label: "Singapore" },
  GB: { lat: 55.38, lon: -3.44, label: "United Kingdom" },
  DE: { lat: 51.16, lon: 10.45, label: "Germany" },
  FR: { lat: 46.23, lon: 2.21, label: "France" },
  CA: { lat: 56.13, lon: -106.35, label: "Canada" },
  BR: { lat: -14.24, lon: -51.92, label: "Brazil" },
  RU: { lat: 61.52, lon: 105.32, label: "Russia" }
};

const state = {
  mode: "single",
  map: null,
  marker: null,
  markerLayer: null,
  chinaCoordinates: new Map(),
  chinaCoordinatesReady: null,
  mapReady: null,
  lastBatchRows: []
};

state.chinaCoordinatesReady = loadChinaCoordinates();
state.mapReady = initMap();
renderAnalysis();
renderHistory();

singleModeButton.addEventListener("click", () => setMode("single"));
batchModeButton.addEventListener("click", () => setMode("batch"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const ip = ipInput.value.trim();
  if (!ip) return;

  const requestMode = state.mode;
  form.querySelector("button").disabled = true;
  mapNote.textContent = "正在查询 IP 信息...";
  try {
    const { payload, data } = await lookupIp(ip);
    await Promise.all([state.chinaCoordinatesReady, state.mapReady]);
    if (requestMode !== state.mode) return;
    render(payload, data);
    addHistory(data);
  } catch (error) {
    if (requestMode !== state.mode) return;
    renderError(error);
  } finally {
    form.querySelector("button").disabled = false;
  }
});

batchButton.addEventListener("click", runBatchLookup);

clearBatchButton.addEventListener("click", () => {
  batchInput.value = "";
  state.lastBatchRows = [];
  renderBatchResults([]);
});

copyBatchButton.addEventListener("click", async () => {
  const text = state.lastBatchRows
    .map((row) => [row.ip, row.location || row.error || "-", row.coords || "-"].join("\t"))
    .join("\n");
  await copyText(text || "暂无批量结果", copyBatchButton);
});

document.querySelectorAll(".copy-button").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.querySelector(`#${button.dataset.copyTarget}`);
    await copyText(target?.textContent?.trim() || "", button);
  });
});

historyList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-ip]");
  if (!button) return;
  ipInput.value = button.dataset.ip;
  form.requestSubmit();
});

window.addEventListener("load", () => {
  setMode("single");
  form.requestSubmit();
});

function setMode(mode) {
  const isBatch = mode === "batch";
  state.mode = isBatch ? "batch" : "single";
  multiTools.classList.toggle("is-hidden", !isBatch);
  singleModeButton.classList.toggle("active", !isBatch);
  batchModeButton.classList.toggle("active", isBatch);
  singleModeButton.setAttribute("aria-selected", String(!isBatch));
  batchModeButton.setAttribute("aria-selected", String(isBatch));
  if (isBatch) {
    window.setTimeout(() => batchInput.focus(), 0);
  } else {
    window.setTimeout(() => ipInput.focus(), 0);
  }
}

async function lookupIp(ip) {
  const response = await fetch(`/lookup?ip=${encodeURIComponent(ip)}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "查询失败");
  await state.chinaCoordinatesReady;
  return { payload, data: normalize(payload) };
}

async function runBatchLookup() {
  const ips = uniqueItems(batchInput.value.split(/[\s,，;；]+/).map((item) => item.trim()).filter(Boolean)).slice(0, 30);
  if (!ips.length) {
    renderBatchResults([]);
    mapNote.textContent = "请输入要批量查询的 IP。";
    return;
  }

  batchButton.disabled = true;
  mapNote.textContent = `正在批量查询 ${ips.length} 个 IP...`;
  renderBatchResults(ips.map((ip) => ({ ip, loading: true })));
  try {
    await Promise.all([state.chinaCoordinatesReady, state.mapReady]);
    const rows = await Promise.all(ips.map(async (ip) => {
      try {
        const { data } = await lookupIp(ip);
        return toBatchRow(ip, data);
      } catch (error) {
        return { ip, error: error.message };
      }
    }));
    state.lastBatchRows = rows;
    renderBatchResults(rows);
    updateMapMany(rows.filter((row) => row.position));
    rows.filter((row) => !row.error).forEach(addHistory);
    const located = rows.filter((row) => row.position).length;
    mapNote.textContent = `批量查询完成：${rows.length} 个 IP，${located} 个已定位到地图。`;
  } finally {
    batchButton.disabled = false;
  }
}

async function initMap() {
  try {
    loadStyle("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
    await loadScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
    state.map = L.map("mapCanvas", {
      center: [30.65, 114.32],
      zoom: 7,
      zoomControl: true,
      attributionControl: false
    });
    L.tileLayer("https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}", {
      subdomains: ["1", "2", "3", "4"],
      minZoom: 3,
      maxZoom: 18
    }).addTo(state.map);
    state.markerLayer = L.layerGroup().addTo(state.map);
    mapNote.textContent = "查询 IP 后在地图中定位。";
  } catch (error) {
    mapNote.textContent = `地图加载失败：${error.message}`;
  }
}

function render(payload, data) {
  ipv4Value.textContent = payload.ip_version === 4 ? payload.ip : "-";
  ipv6Value.textContent = payload.ip_version === 6 ? payload.ip : "未检测到 IPv6";
  basicIp.textContent = payload.ip;
  basicLocation.textContent = data.locationDetail || data.location || "-";
  basicAsn.textContent = data.asn ? `ASN${data.asn}` : "-";
  basicIsp.textContent = data.isp || data.networkName || "-";
  basicCoords.textContent = data.position ? `${data.position.lon.toFixed(6)}, ${data.position.lat.toFixed(6)}` : "-";
  basicBroadcast.textContent = "N/A";
  renderRisk(data);
  renderAnalysis(data);

  if (data.position) {
    updateMap(data.position.lat, data.position.lon, data.locationDetail || payload.ip);
    mapNote.textContent = data.mapLabel;
  } else {
    mapNote.textContent = "未找到可用于地图定位的坐标。";
  }
}

function renderError(error) {
  basicIp.textContent = ipInput.value.trim() || "-";
  basicLocation.textContent = error.message;
  basicAsn.textContent = "-";
  basicIsp.textContent = "-";
  basicCoords.textContent = "-";
  mapNote.textContent = error.message;
}

function renderBatchResults(rows) {
  if (!rows.length) {
    batchResults.innerHTML = "";
    return;
  }
  batchResults.innerHTML = rows.map((row) => {
    if (row.loading) {
      return `<div class="batch-row"><strong>${escapeHtml(row.ip)}</strong><span>查询中...</span><span>-</span></div>`;
    }
    if (row.error) {
      return `<div class="batch-row error"><strong>${escapeHtml(row.ip)}</strong><span>${escapeHtml(row.error)}</span><span>-</span></div>`;
    }
    return `
      <div class="batch-row">
        <strong>${escapeHtml(row.ip)}</strong>
        <span>${escapeHtml(row.location || "-")}</span>
        <span>${escapeHtml(row.coords || "-")}</span>
      </div>
    `;
  }).join("");
}

function renderHistory() {
  const rows = readHistory();
  if (!rows.length) {
    historyList.innerHTML = `<div class="history-empty">暂无查询历史</div>`;
    return;
  }
  historyList.innerHTML = rows.map((row) => `
    <button type="button" data-ip="${escapeHtml(row.ip)}">
      <strong>${escapeHtml(row.ip)}</strong>
      <span>${escapeHtml(row.location || "-")}</span>
      <span>${escapeHtml(row.coords || "-")}</span>
    </button>
  `).join("");
}

function updateMap(lat, lon, label) {
  if (!state.map || !window.L) return;
  state.markerLayer?.clearLayers();
  const position = [lat, lon];
  state.marker = L.marker(position).addTo(state.markerLayer || state.map);
  state.marker.bindPopup(label).openPopup();
  state.map.setView(position, 8);
}

function updateMapMany(rows) {
  if (!state.map || !window.L || !rows.length) return;
  state.markerLayer?.clearLayers();
  const bounds = [];
  for (const row of rows) {
    const position = [row.position.lat, row.position.lon];
    bounds.push(position);
    L.marker(position)
      .addTo(state.markerLayer || state.map)
      .bindPopup(`${escapeHtml(row.ip)}<br>${escapeHtml(row.location || "-")}`);
  }
  if (bounds.length === 1) {
    state.map.setView(bounds[0], 8);
  } else {
    state.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 8 });
  }
}

function normalize(payload) {
  const locationResult = findResult(payload, "ip2region");
  const tableResult = findResult(payload, "ip-location-db");
  const precisionResult = findResult(payload, "geoip2");
  const region = locationResult?.data?.region || "";
  const parts = region.split("|");
  const country = clean(parts[0]);
  const province = clean(parts[1]);
  const city = clean(parts[2]);
  const isp = clean(parts[3]);
  const codeFromRegion = clean(parts[4]).toUpperCase();
  const network = findNetwork(tableResult?.data);
  const countryCode = network.countryCode || (/^[A-Z]{2}$/.test(codeFromRegion) ? codeFromRegion : "");
  const coordinates = findCoordinates(precisionResult?.data?.record);
  const chinaCoordinate = countryCode === "CN" ? findChinaCoordinate(city, province) : null;
  const centroid = countryCode ? COUNTRY_CENTROIDS[countryCode] : null;
  const position = coordinates || chinaCoordinate || centroid || null;
  const location = [country, province, city].filter(Boolean).join("/");
  const carrier = isp || network.name;
  const locationDetail = [location, carrier].filter(Boolean).join("/");

  return {
    ip: payload.ip,
    location,
    locationDetail,
    isp,
    asn: network.asn,
    networkName: network.name,
    countryCode,
    countryName: centroid?.label || country,
    position,
    coords: position ? `${position.lon.toFixed(6)}, ${position.lat.toFixed(6)}` : "",
    mapLabel: position
      ? `${locationDetail || countryCode || "IP"} - ${coordinates ? "精确坐标" : chinaCoordinate ? "城市级坐标" : "国家级坐标"}`
      : "无坐标"
  };
}

function toBatchRow(ip, data) {
  return {
    ip,
    location: data.locationDetail || data.location || data.countryName || "-",
    coords: data.coords || "",
    position: data.position || null
  };
}

function renderRisk(data = {}) {
  const carrier = `${data.networkName || data.isp || ""}`.toLowerCase();
  const score = /cloud|hosting|data|server|amazon|google|microsoft|aliyun|tencent|colo/.test(carrier) ? 12 : 0;
  riskScore.textContent = `${score}分`;
  riskNeedle.style.left = `${Math.min(98, score)}%`;
  riskSummary.textContent = score <= 20 ? "极低风险 - 安全可信" : "较低风险 - 建议复核";
}

function renderAnalysis(data = {}) {
  const commercial = data.asn ? "商业IP" : "未知";
  const rows = [
    ["local-ip", "否", "否", commercial, "否"],
    ["region-db", "否", "否", commercial, "否"],
    ["geo-check", "否", "否", commercial, "否"]
  ];
  analysisBody.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row[0])}</td>
      <td>${statusPill(row[1])}</td>
      <td>${statusPill(row[2])}</td>
      <td>${escapeHtml(row[3])}</td>
      <td>${statusPill(row[4])}</td>
    </tr>
  `).join("");
}

function statusPill(value) {
  return `<span class="pill${value === "无" ? " gray" : ""}">${escapeHtml(value)}</span>`;
}

function addHistory(data) {
  const row = {
    ip: data.ip || data.ipAddress || "",
    location: data.locationDetail || data.location || "-",
    coords: data.coords || ""
  };
  if (!row.ip) return;
  const rows = readHistory().filter((item) => item.ip !== row.ip);
  rows.unshift(row);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(rows.slice(0, MAX_HISTORY)));
  renderHistory();
}

function readHistory() {
  try {
    const rows = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

async function copyText(text, button) {
  if (!text || text === "-") return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  const oldText = button.textContent;
  button.textContent = "已复制";
  button.classList.add("copied");
  window.setTimeout(() => {
    button.textContent = oldText;
    button.classList.remove("copied");
  }, 1200);
}

function uniqueItems(items) {
  return [...new Set(items)];
}

function clean(value) {
  if (!value || value === "0") return "";
  return String(value).trim();
}

function findResult(payload, source) {
  return (payload.results || []).find((result) => result.source === source && result.ok);
}

function findNetwork(data) {
  const result = { countryCode: "", asn: "", name: "" };
  if (!data) return result;

  for (const row of Object.values(data)) {
    if (!row) continue;
    if (!result.countryCode && row.country_code) result.countryCode = String(row.country_code).toUpperCase();
    if (!result.asn && row.autonomous_system_number) result.asn = String(row.autonomous_system_number);
    if (!result.name && row.autonomous_system_organization) result.name = String(row.autonomous_system_organization);
  }
  return result;
}

function findCoordinates(value) {
  if (!value || typeof value !== "object") return null;
  if (Number.isFinite(value.latitude) && Number.isFinite(value.longitude)) {
    return { lat: value.latitude, lon: value.longitude };
  }
  for (const item of Object.values(value)) {
    const result = findCoordinates(item);
    if (result) return result;
  }
  return null;
}

async function loadChinaCoordinates() {
  try {
    const response = await fetch("/static/assets/china-coordinates.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const rows = await response.json();
    for (const row of rows) {
      const point = { lat: Number(row.lat), lon: Number(row.lon), level: row.level || "" };
      for (const key of chinaNameKeys(row.name)) state.chinaCoordinates.set(key, point);
    }
  } catch (error) {
    console.warn("China coordinates failed to load", error);
  }
}

function findChinaCoordinate(city, province) {
  for (const name of [city, province]) {
    for (const key of chinaNameKeys(name)) {
      const point = state.chinaCoordinates.get(key);
      if (point) return point;
    }
  }
  return null;
}

function chinaNameKeys(value) {
  const name = clean(value);
  if (!name) return [];
  const keys = new Set([name]);
  for (const item of ["北京", "天津", "上海", "重庆"]) {
    if (name === item || name === `${item}市`) {
      keys.add(item);
      keys.add(`${item}市`);
    }
  }
  for (const suffix of ["省", "市", "自治区", "特别行政区", "地区", "盟"]) {
    if (name.endsWith(suffix)) keys.add(name.slice(0, -suffix.length));
  }
  if (!/[省市区盟]$/.test(name)) {
    keys.add(`${name}市`);
    keys.add(`${name}省`);
  }
  return [...keys].filter(Boolean);
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Cannot load ${src}`));
    document.head.appendChild(script);
  });
}

function loadStyle(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}
