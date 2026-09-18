const NS = "http://www.w3.org/2000/svg";
const $ = (s, r = document) => r.querySelector(s);
const fmt = n => n.toLocaleString("en-US");
const tip = $("#tip");
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const SEQ_LIGHT = ["#e8f1fd","#cde2fb","#9ec5f4","#6da7ec","#3987e5","#2a78d6","#1c5cab","#104281"];
const SEQ_DARK  = ["#14243b","#16304f","#184f95","#1c5cab","#2a78d6","#3987e5","#6da7ec","#9ec5f4"];

let D, state = { list: "qgis-developer", y0: 0, y1: 0, metric: "n", tab: "top",
                 sort: "n", desc: true, q: "", hideBots: false, limit: 25, tlimit: 20 };

const el = (tag, attrs = {}, kids = []) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  for (const c of [].concat(kids)) e.appendChild(c);
  return e;
};
const text = (x, y, s, cls = {}) =>
  el("text", { x, y, "font-size": 11, fill: "var(--muted)", ...cls }, [document.createTextNode(s)]);
const root = (host, h) => {
  const w = Math.max(260, host.clientWidth);
  const s = el("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, role: "img" });
  host.replaceChildren(s);
  return [s, w];
};
const dark = () => matchMedia("(prefers-color-scheme: dark)").matches
  ? document.documentElement.dataset.theme !== "light"
  : document.documentElement.dataset.theme === "dark";

function showTip(e, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(e.clientX + 14, innerWidth - r.width - 8) + "px";
  tip.style.top = Math.max(8, Math.min(e.clientY + 14, innerHeight - r.height - 8)) + "px";
}
const hideTip = () => { tip.hidden = true; };

const inRange = y => y >= state.y0 && y <= state.y1;
const people = () => D.authors.filter(a => !(state.hideBots && a.bot));

/** Round axis ticks to 1/2/5 x 10^n so labels read as numbers, not noise. */
function niceTicks(max, count = 4) {
  const raw = max / count, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].find(m => m * mag >= raw) * mag;
  return Array.from({ length: Math.ceil(max / step) + 1 }, (_, i) => i * step);
}
const sumYears = (obj) => {
  let s = 0;
  for (const y in obj) if (inRange(+y)) s += obj[y];
  return s;
};

/* ---------------------------------------------------------- stat tiles */
function renderTiles() {
  const yrs = D.yearly.filter(y => inRange(y.y));
  const msgs = yrs.reduce((a, y) => a + y.n, 0);
  const threads = yrs.reduce((a, y) => a + y.threads, 0);
  const peak = yrs.slice().sort((a, b) => b.n - a.n)[0];
  const tiles = [
    [fmt(msgs), "messages"],
    [fmt(threads), "threads started"],
    [fmt(people().filter(a => sumYears(a.years)).length), "people writing"],
    [peak ? peak.y : "—", "busiest year"],
    [`${state.y0}–${state.y1}`, "period shown"],
  ];
  $("#tiles").innerHTML = tiles
    .map(([v, k]) => `<div class="tile"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
}

/* ----------------------------------------------------------- timeline */
function renderTimeline() {
  const host = $("#timeline"), H = 250, P = { t: 12, r: 12, b: 26, l: 44 };
  const [svg, W] = root(host, H);
  const data = D.monthly, key = state.metric;
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const ticks = niceTicks(Math.max(...data.map(d => d[key])));
  const max = ticks.at(-1);
  const x = i => P.l + (iw * i) / (data.length - 1);
  const y = v => P.t + ih - (ih * v) / max;
  for (const v of ticks) {
    svg.appendChild(el("line", { x1: P.l, x2: W - P.r, y1: y(v), y2: y(v), stroke: "var(--grid)", "stroke-width": 1 }));
    svg.appendChild(text(P.l - 8, y(v) + 4, fmt(v), { "text-anchor": "end" }));
  }

  const area = data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d[key])}`).join("") +
    `L${x(data.length - 1)},${y(0)}L${x(0)},${y(0)}Z`;
  svg.appendChild(el("path", { d: area, fill: "var(--s1)", "fill-opacity": .16 }));
  svg.appendChild(el("path", {
    d: data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d[key])}`).join(""),
    fill: "none", stroke: "var(--s1)", "stroke-opacity": .45, "stroke-width": 1,
  }));

  const roll = data.map((_, i) => {
    const s = Math.max(0, i - 11), w = data.slice(s, i + 1);
    return w.reduce((a, d) => a + d[key], 0) / w.length;
  });
  svg.appendChild(el("path", {
    d: roll.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(""),
    fill: "none", stroke: "var(--s1)", "stroke-width": 2, "stroke-linejoin": "round",
  }));

  // dim everything outside the selected period
  const first = data.findIndex(d => +d.m.slice(0, 4) >= state.y0);
  let last = data.length - 1;
  while (last > 0 && +data[last].m.slice(0, 4) > state.y1) last--;
  const dim = (x1, x2) => x2 > x1 && svg.appendChild(el("rect", {
    x: x1, y: P.t, width: x2 - x1, height: ih, fill: "var(--surface)", "fill-opacity": .66,
  }));
  dim(P.l, x(Math.max(0, first)));
  dim(x(last), W - P.r);

  let prevYear = null;
  data.forEach((d, i) => {
    const yr = +d.m.slice(0, 4);
    if (yr !== prevYear && yr % 2 === 0) {
      svg.appendChild(text(x(i), H - 8, yr, { "text-anchor": "middle" }));
      prevYear = yr;
    }
  });
  svg.appendChild(el("line", { x1: P.l, x2: W - P.r, y1: y(0), y2: y(0), stroke: "var(--axis)" }));

  const cross = el("line", { y1: P.t, y2: P.t + ih, stroke: "var(--axis)", "stroke-width": 1, opacity: 0 });
  const dot = el("circle", { r: 4, fill: "var(--s1)", stroke: "var(--surface)", "stroke-width": 2, opacity: 0 });
  const sel = el("rect", { y: P.t, height: ih, fill: "var(--s1)", "fill-opacity": .14, opacity: 0 });
  svg.append(sel, cross, dot);

  const label = { n: "messages", p: "people", t: "threads" }[key];
  const idxAt = e => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(data.length - 1, Math.round(((px - P.l) / iw) * (data.length - 1))));
  };
  let anchor = null;
  svg.addEventListener("pointermove", e => {
    const i = idxAt(e), d = data[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", 1);
    dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(d[key])); dot.setAttribute("opacity", 1);
    if (anchor !== null) {
      sel.setAttribute("x", Math.min(x(anchor), x(i)));
      sel.setAttribute("width", Math.abs(x(i) - x(anchor)));
      sel.setAttribute("opacity", 1);
    }
    const [yy, mm] = d.m.split("-");
    showTip(e, `<b>${MONTHS[+mm - 1]} ${yy}</b><br>${fmt(d.n)} messages<br>
      <span class="k">${fmt(d.p)} people · ${fmt(d.t)} threads</span>`);
  });
  svg.addEventListener("pointerleave", () => {
    cross.setAttribute("opacity", 0); dot.setAttribute("opacity", 0); hideTip();
  });
  svg.addEventListener("pointerdown", e => { anchor = idxAt(e); svg.setPointerCapture(e.pointerId); });
  svg.addEventListener("pointerup", e => {
    if (anchor === null) return;
    const i = idxAt(e);
    sel.setAttribute("opacity", 0);
    if (Math.abs(i - anchor) > 1) {
      const a = +data[Math.min(anchor, i)].m.slice(0, 4), b = +data[Math.max(anchor, i)].m.slice(0, 4);
      setRange(a, b);
    }
    anchor = null;
  });
  svg.appendChild(el("title", {}, [document.createTextNode(`Monthly ${label} on qgis-developer`)]));
}

/* ------------------------------------------------------ people (bars) */
function topPeople(n) {
  return people()
    .map(a => ({ ...a, sum: sumYears(a.years) }))
    .filter(a => a.sum > 0)
    .sort((x, y) => y.sum - x.sum)
    .slice(0, n);
}

function renderPeopleChart() {
  const host = $("#peopleChart"), rows = topPeople(16);
  const RH = 21, H = rows.length * RH + 24, P = { t: 6, r: 52, l: 140 };
  const [svg, W] = root(host, H);
  if (!rows.length) return host.replaceChildren(Object.assign(document.createElement("p"),
    { className: "hint", textContent: "No messages in this period." }));
  const max = rows[0].sum, iw = W - P.l - P.r;
  rows.forEach((a, i) => {
    const y = P.t + i * RH, w = Math.max(2, (iw * a.sum) / max);
    const name = a.name.length > 18 ? a.name.slice(0, 17) + "…" : a.name;
    svg.appendChild(text(P.l - 10, y + 13, name, { "text-anchor": "end", fill: "var(--ink-2)", "font-size": 12 }));
    const bar = el("rect", { x: P.l, y: y + 3, width: w, height: 13, rx: 4, fill: "var(--s1)" });
    bar.addEventListener("pointermove", e => showTip(e,
      `<b>${a.name}</b><br>${fmt(a.sum)} messages in ${state.y0}–${state.y1}<br>
       <span class="k">@${a.domain} · ${fmt(a.started)} threads started (all time)</span>`));
    bar.addEventListener("pointerleave", hideTip);
    svg.appendChild(bar);
    svg.appendChild(text(P.l + w + 7, y + 14, fmt(a.sum), { fill: "var(--ink-2)", "font-size": 11.5 }));
  });
}

/* --------------------------------------------------------- heatmap */
function renderHeatmap() {
  const host = $("#heatmap");
  const grid = Array.from({ length: 7 }, () => Array(24).fill(0));
  for (const y in D.heatmapByYear) {
    if (!inRange(+y)) continue;
    D.heatmapByYear[y].forEach((row, d) => row.forEach((v, h) => { grid[d][h] += v; }));
  }
  const H = 196, P = { t: 14, r: 8, l: 34, b: 26 };
  const [svg, W] = root(host, H);
  const cw = (W - P.l - P.r) / 24, ch = (H - P.t - P.b) / 7;
  const max = Math.max(1, ...grid.flat());
  const ramp = dark() ? SEQ_DARK : SEQ_LIGHT;
  const color = v => v === 0 ? "var(--grid)" : ramp[Math.min(ramp.length - 1, Math.floor((v / max) ** .55 * ramp.length))];
  const total = grid.flat().reduce((a, b) => a + b, 0) || 1;

  grid.forEach((row, d) => {
    svg.appendChild(text(P.l - 7, P.t + d * ch + ch / 2 + 4, DAYS[d], { "text-anchor": "end" }));
    row.forEach((v, h) => {
      const r = el("rect", {
        x: P.l + h * cw + 1, y: P.t + d * ch + 1, width: Math.max(1, cw - 2), height: Math.max(1, ch - 2),
        rx: 2, fill: color(v),
      });
      r.addEventListener("pointermove", e => showTip(e,
        `<b>${DAYS[d]} ${String(h).padStart(2, "0")}:00</b><br>${fmt(v)} messages
         <span class="k">(${(v / total * 100).toFixed(1)}%)</span>`));
      r.addEventListener("pointerleave", hideTip);
      svg.appendChild(r);
    });
  });
  for (let h = 0; h < 24; h += 3)
    svg.appendChild(text(P.l + h * cw + cw / 2, H - 8, String(h).padStart(2, "0"), { "text-anchor": "middle" }));

  host.insertAdjacentHTML("beforeend",
    `<div class="legend scale"><span>fewer</span>${ramp.map(c =>
      `<i style="background:${c}"></i>`).join("")}<span>more messages</span></div>`);
}

/* ------------------------------------------------------ orgs (stack) */
function renderOrgs() {
  const host = $("#orgs");
  const years = D.years.filter(inRange);
  const tot = D.domains.map(d => ({ ...d, sum: sumYears(d.years) })).filter(d => d.sum);
  tot.sort((a, b) => b.sum - a.sum);
  const top = tot.slice(0, 7), rest = tot.slice(7);
  const series = [...top.map((d, i) => ({ name: d.d, color: `var(--s${i + 1})`, d })),
                  { name: "other domains", color: "var(--axis)", d: null }];
  const H = 230, P = { t: 10, r: 10, l: 36, b: 26 };
  const [svg, W] = root(host, H);
  if (years.length < 2) return host.replaceChildren(Object.assign(document.createElement("p"),
    { className: "hint", textContent: "Pick at least two years to see the trend." }));
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const x = i => P.l + (iw * i) / (years.length - 1);
  const y = v => P.t + ih - ih * v;

  const share = years.map(yr => {
    const all = D.yearly.find(a => a.y === yr).n || 1;
    const vals = series.map(s => s.d ? (s.d.years[yr] || 0) / all
      : rest.reduce((a, d) => a + (d.years[yr] || 0), 0) / all);
    return vals;
  });
  let base = years.map(() => 0);
  series.forEach((s, si) => {
    const up = years.map((_, i) => base[i] + share[i][si]);
    const path = up.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("") +
      base.map((v, i) => `L${x(base.length - 1 - i)},${y(base[base.length - 1 - i])}`).join("") + "Z";
    const p = el("path", { d: path, fill: s.color, "fill-opacity": .9, stroke: "var(--surface)", "stroke-width": 2 });
    p.addEventListener("pointermove", e => {
      const i = Math.max(0, Math.min(years.length - 1,
        Math.round(((e.clientX - svg.getBoundingClientRect().left) / svg.getBoundingClientRect().width * W - P.l) / iw * (years.length - 1))));
      showTip(e, `<b>${s.name}</b><br>${(share[i][si] * 100).toFixed(1)}% of ${years[i]} messages`);
    });
    p.addEventListener("pointerleave", hideTip);
    svg.appendChild(p);
    const mid = Math.round(years.length * .62);
    const band = y(base[mid]) - y(up[mid]);
    if (band > 15)
      svg.appendChild(text(x(mid), (y(base[mid]) + y(up[mid])) / 2 + 4, s.name,
        { "text-anchor": "middle", fill: "var(--ink)", "font-size": 11, "paint-order": "stroke",
          stroke: "var(--surface)", "stroke-width": 3 }));
    base = up;
  });
  [0, .25, .5, .75, 1].forEach(v => svg.appendChild(text(P.l - 7, y(v) + 4, `${v * 100}%`, { "text-anchor": "end" })));
  years.forEach((yr, i) => {
    if (years.length <= 12 || yr % (years.length > 24 ? 4 : 2) === 0)
      svg.appendChild(text(x(i), H - 7, yr,
        { "text-anchor": i === 0 ? "start" : i === years.length - 1 ? "end" : "middle" }));
  });
  host.insertAdjacentHTML("beforeend", `<div class="legend">${series
    .map(s => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join("")}</div>`);
}

/* ----------------------------------------------------- churn (bars) */
function renderChurn() {
  const host = $("#churn");
  const years = D.yearly.filter(y => inRange(y.y));
  const H = 230, P = { t: 10, r: 10, l: 34, b: 26 };
  const [svg, W] = root(host, H);
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const ticks = niceTicks(Math.max(1, ...years.map(y => Math.max(y.newcomers, y.returning))), 3);
  const max = ticks.at(-1), bw = iw / years.length;
  const y = v => P.t + ih - (ih * v) / max;
  for (const v of ticks) {
    svg.appendChild(el("line", { x1: P.l, x2: W - P.r, y1: y(v), y2: y(v), stroke: "var(--grid)" }));
    svg.appendChild(text(P.l - 7, y(v) + 4, v, { "text-anchor": "end" }));
  }
  years.forEach((yr, i) => {
    [["newcomers", "var(--s1)", 0], ["returning", "var(--s2)", 1]].forEach(([k, c, s]) => {
      const w = Math.max(2, bw * .36), bx = P.l + i * bw + bw * .12 + s * (w + 2);
      const r = el("rect", { x: bx, y: y(yr[k]), width: w, height: Math.max(1, y(0) - y(yr[k])), rx: 3, fill: c });
      r.addEventListener("pointermove", e => showTip(e,
        `<b>${yr.y}</b><br>${fmt(yr.newcomers)} first-time posters<br>${fmt(yr.returning)} also posted the year before<br>
         <span class="k">${fmt(yr.people)} people active, ${fmt(yr.n)} messages</span>`));
      r.addEventListener("pointerleave", hideTip);
      svg.appendChild(r);
    });
    if (years.length <= 12 || yr.y % (years.length > 24 ? 4 : 2) === 0)
      svg.appendChild(text(P.l + i * bw + bw / 2, H - 7, yr.y, { "text-anchor": "middle" }));
  });
  svg.appendChild(el("line", { x1: P.l, x2: W - P.r, y1: y(0), y2: y(0), stroke: "var(--axis)" }));
  host.insertAdjacentHTML("beforeend",
    `<div class="legend"><span><i style="background:var(--s1)"></i>first-time posters</span>
     <span><i style="background:var(--s2)"></i>returning from last year</span></div>`);
}

/* ----------------------------------------------------------- tables */
function spark(years) {
  const vals = D.years.map(y => years[y] || 0), max = Math.max(1, ...vals);
  const w = 3, h = 16;
  return `<svg width="${vals.length * w}" height="${h}" viewBox="0 0 ${vals.length * w} ${h}">` +
    vals.map((v, i) => {
      const bh = Math.max(v ? 1 : 0, (v / max) * h);
      return `<rect x="${i * w}" y="${h - bh}" width="${w - 1}" height="${bh}" rx="1"
        fill="var(--s1)" fill-opacity="${inRange(D.years[i]) ? .95 : .25}"/>`;
    }).join("") + "</svg>";
}

function renderPeopleTable() {
  const cols = [
    ["rank", "#", r => r.rank, "num"],
    ["name", "Person", r => `<span class="l">${esc(r.name)}</span>`, "l"],
    ["domain", "Domain", r => `<span class="dim">${esc(r.domain)}${r.domains > 1 ? ` +${r.domains - 1}` : ""}</span>`, "l dim"],
    ["sum", "Messages", r => fmt(r.sum), "num"],
    ["started", "Threads started", r => fmt(r.started), "num"],
    ["threads", "Threads joined", r => fmt(r.threads), "num"],
    ["first", "First", r => r.first, "num dim"],
    ["last", "Last", r => r.last, "num dim"],
    ["spark", "Per year", r => spark(r.years), "l"],
  ];
  let rows = people().map(a => ({ ...a, sum: sumYears(a.years) })).filter(a => a.sum > 0);
  if (state.q) {
    const q = state.q.toLowerCase();
    rows = rows.filter(a => a.name.toLowerCase().includes(q) || a.domain.includes(q));
  }
  const k = state.sort === "n" ? "sum" : state.sort;
  rows.sort((a, b) => {
    const [x, y] = [a[k], b[k]];
    const c = typeof x === "string" ? x.localeCompare(y) : x - y;
    return state.desc ? -c : c;
  });
  const total = rows.length;
  rows = rows.slice(0, state.limit);
  rows.forEach((r, i) => { r.rank = i + 1; });
  $("#peopleTable").innerHTML =
    `<thead><tr>${cols.map(c => `<th data-k="${c[0]}" class="${c[3].includes("l") ? "l" : ""}">${c[1]}${
      (c[0] === state.sort || (c[0] === "sum" && state.sort === "n")) ? (state.desc ? " ↓" : " ↑") : ""}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map(r => `<tr>${cols.map(c => `<td class="${c[3]}">${c[2](r)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  $("#peopleMore").hidden = total <= state.limit;
  $("#peopleMore").textContent = `Show more (${fmt(total - rows.length)} left)`;
  $("#peopleTable").querySelectorAll("th").forEach(th => th.onclick = () => {
    const k = th.dataset.k === "sum" ? "n" : th.dataset.k;
    state.desc = state.sort === k ? !state.desc : true;
    state.sort = k;
    renderPeopleTable();
  });
}

const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function renderThreadTable() {
  const src = state.tab === "top" ? D.topThreads : D.longestThreads;
  const all = src.filter(t => inRange(+t.start.slice(0, 4)));
  const rows = all.slice(0, state.tlimit);
  const head = `<thead><tr><th class="l">Thread</th><th class="l">Started by</th>
    <th>Messages</th><th>People</th><th>Ran for</th><th class="l">Started</th></tr></thead>`;
  $("#threadTable").innerHTML = head + `<tbody>${rows.map(t => `<tr>
    <td class="l subj"><a href="${t.url}" target="_blank" rel="noopener">${esc(t.subject)}</a></td>
    <td class="l dim">${esc(t.starter)}</td>
    <td class="num">${fmt(t.n)}</td><td class="num">${fmt(t.people)}</td>
    <td class="num">${t.days === 0 ? "same day" : t.days + " days"}</td>
    <td class="l num dim">${t.start}</td></tr>`).join("")}</tbody>` +
    (rows.length ? "" : `<tbody><tr><td class="l dim">No threads in this period.</td></tr></tbody>`);
  $("#threadMore").hidden = all.length <= rows.length;
  $("#threadMore").textContent = `Show more (${fmt(all.length - rows.length)} left)`;
}

/* -------------------------------------------------------- plumbing */
function setRange(a, b) {
  state.y0 = Math.max(D.years[0], Math.min(a, b));
  state.y1 = Math.min(D.years.at(-1), Math.max(a, b));
  $("#y0").value = state.y0; $("#y1").value = state.y1;
  renderAll();
}

function renderAll() {
  state.limit = Math.max(25, state.limit);
  const yrs = D.yearly.filter(y => inRange(y.y));
  $("#rangeNote").textContent =
    `${fmt(yrs.reduce((a, y) => a + y.n, 0))} messages in ${state.y1 - state.y0 + 1} year${state.y1 > state.y0 ? "s" : ""}`;
  renderTiles(); renderTimeline(); renderPeopleChart(); renderHeatmap();
  renderOrgs(); renderChurn(); renderPeopleTable(); renderThreadTable();
}

function boot(data, keepRange) {
  D = data;
  const y = [D.years[0], D.years.at(-1)];
  state.y0 = keepRange ? Math.max(y[0], state.y0) : y[0];
  state.y1 = keepRange ? Math.min(y[1], state.y1) : y[1];
  if (state.y0 > state.y1) [state.y0, state.y1] = y;
  state.limit = 25; state.tlimit = 20;
  $("#subtitle").textContent =
    `${fmt(D.meta.messages)} messages · ${fmt(D.meta.threads)} threads · ${fmt(D.meta.people)} people · ${D.meta.first} to ${D.meta.last}`;
  $("#gen").textContent = `Data generated ${D.meta.generated}.`;
  $("#srcLink").href = D.meta.listUrl + "/";
  $("#srcLink").textContent = `lists.osgeo.org/pipermail/${D.meta.list}`;
  document.title = `${D.meta.list} — QGIS mailing list explorer`;
  for (const id of ["y0", "y1"]) {
    $("#" + id).innerHTML = D.years.map(y => `<option>${y}</option>`).join("");
    $("#" + id).value = state[id];
    $("#" + id).onchange = () => setRange(+$("#y0").value, +$("#y1").value);
  }
  const last = D.years.at(-1);
  const presets = [["All", D.years[0], last], ["Last 5 years", last - 4, last],
                   ["2020s", 2020, last], ["2010s", 2010, 2019], ["2006–2009", 2006, 2009]];
  $("#presets").innerHTML = presets.map((p, i) => `<button data-i="${i}">${p[0]}</button>`).join("");
  $("#presets").onclick = e => { const i = e.target.dataset.i; if (i) setRange(presets[i][1], presets[i][2]); };
  $("#metric").onclick = e => {
    if (!e.target.dataset.v) return;
    state.metric = e.target.dataset.v;
    $("#metric").querySelectorAll("button").forEach(b => b.classList.toggle("on", b === e.target));
    renderTimeline();
  };
  $("#threadTab").onclick = e => {
    if (!e.target.dataset.v) return;
    state.tab = e.target.dataset.v; state.tlimit = 20;
    $("#threadTab").querySelectorAll("button").forEach(b => b.classList.toggle("on", b === e.target));
    renderThreadTable();
  };
  $("#search").oninput = e => { state.q = e.target.value.trim(); state.limit = 25; renderPeopleTable(); };
  $("#peopleMore").onclick = () => { state.limit += 50; renderPeopleTable(); };
  $("#threadMore").onclick = () => { state.tlimit += 40; renderThreadTable(); };
  $("#bots").onchange = e => { state.hideBots = e.target.checked; state.limit = 25; renderAll(); };
  $("#app").hidden = false;
  renderAll();
}

let wired = false;
function wire() {
  if (wired) return;
  wired = true;
  let t;
  addEventListener("resize", () => { clearTimeout(t); t = setTimeout(renderAll, 150); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
  addEventListener("hashchange", () => load(listFromHash(), true));
  $("#listPick").onclick = e => {
    const v = e.target.dataset.v;
    if (!v || v === state.list) return;
    location.hash = v === LISTS[0] ? "" : v;
    load(v, true);
  };
}

const LISTS = ["qgis-developer", "qgis-user"];
const listFromHash = () => LISTS.includes(location.hash.slice(1)) ? location.hash.slice(1) : LISTS[0];

function load(list, keepRange) {
  state.list = list;
  $("#listPick").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === list));
  $("#subtitle").textContent = "Loading archives…";
  return fetch(`data/${list}.json`)
    .then(r => r.json())
    .then(d => { boot(d, keepRange); wire(); })
    .catch(e => { $("#subtitle").textContent = `Could not load ${list} data — ${e.message}`; });
}

$("#theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || "system";
  const next = { system: "light", light: "dark", dark: "system" }[cur];
  if (next === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch {}
  if (D) renderAll();
};
try {
  const s = localStorage.getItem("theme");
  if (s && s !== "system") document.documentElement.dataset.theme = s;
} catch {}

load(listFromHash(), false);
