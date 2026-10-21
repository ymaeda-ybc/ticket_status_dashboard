import streamlit as st
import pandas as pd
import numpy as np
import json
import streamlit.components.v1 as components

# ==========================================
# ページ設定
# ==========================================
st.set_page_config(
    page_title="座席ナビ",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 余白を詰めてスマホ画面に最適化
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; max-width: 1100px; }
    h1 { font-size: 1.6rem !important; margin-bottom: 0.2rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("🏀 座席ナビ")
st.caption("チケットに書かれた「階・エリア」「ブロック」「列」「番」を入れると、座席図であなたの席が光ります。")

# ==========================================
# データ読み込み＆斜め座席の整列補正
# ==========================================
@st.cache_data
def load_seat_master(csv_path):
    df = pd.read_csv(csv_path)
    valid_mask = df["SeatName"].astype(str).str.count("_") == 3
    df_valid = df[valid_mask].copy()
    
    parts = df_valid["SeatName"].str.split("_", expand=True)
    df_valid["Floor"] = parts[0]
    df_valid["Block"] = parts[1]
    df_valid["Row"] = parts[2]
    df_valid["Number"] = parts[3]
    
    df_valid["Row_num"] = pd.to_numeric(df_valid["Row"], errors="coerce").fillna(999).astype(int)
    df_valid["Number_num"] = pd.to_numeric(df_valid["Number"], errors="coerce").fillna(999).astype(int)

    # 斜め座標の判定と角度設定（左コーナー:+38度、右コーナー:-38度）
    is_diagonal = (df_valid["X_Col"] % 1 != 0) | (df_valid["Y_Row"] % 1 != 0)
    df_valid["Angle"] = np.where(
        ~is_diagonal, 0,
        np.where(df_valid["X_Col"] < 100, 38, -38)
    )

    # 2FメインコーナーCの同一列内の段差を一直線に補正
    for side_cond, angle_deg in [((df_valid["X_Col"] < 100), 38.0), ((df_valid["X_Col"] > 100), -38.0)]:
        mask_2fc = (df_valid["Floor"] == "2F") & (df_valid["Block"] == "メインコーナーC") & is_diagonal & side_cond
        if mask_2fc.any():
            sub = df_valid.loc[mask_2fc]
            rad = np.radians(angle_deg)
            cos_a, sin_a = np.cos(rad), np.sin(rad)
            u = sub["X_Col"] * cos_a + sub["Y_Row"] * sin_a
            v = -sub["X_Col"] * sin_a + sub["Y_Row"] * cos_a
            v_aligned = v.groupby(sub["Row_num"]).transform("mean")
            df_valid.loc[mask_2fc, "X_Col"] = u * cos_a - v_aligned * sin_a
            df_valid.loc[mask_2fc, "Y_Row"] = u * sin_a + v_aligned * cos_a

    df_valid["X_Col"] = df_valid["X_Col"].round(2)
    df_valid["Y_Row"] = df_valid["Y_Row"].round(2)
    return df_valid

# ファイルの読み込み（斜め変換後があれば優先、なければ通常マスタ）
try:
    df_seats = load_seat_master("座標マスタ_斜め変換後.csv")
except FileNotFoundError:
    try:
        df_seats = load_seat_master("座標マスタ.csv")
    except FileNotFoundError:
        st.error("⚠️ 座標マスタのCSVファイルが見つかりません。")
        st.stop()

# ==========================================
# 1. 座席選択UI（プルダウン）
# ==========================================
col1, col2, col3, col4 = st.columns(4)

floor_order = [f for f in ["1F", "2F", "3F", "VIP"] if f in df_seats["Floor"].unique()]
with col1:
    selected_floor = st.selectbox("区分（階・フロア）", floor_order)

df_floor = df_seats[df_seats["Floor"] == selected_floor]
block_list = sorted(df_floor["Block"].unique())
with col2:
    selected_block = st.selectbox("セクション（ブロック）", block_list)

df_block = df_floor[df_floor["Block"] == selected_block].sort_values("Row_num")
row_list = df_block["Row"].unique()
with col3:
    selected_row = st.selectbox("列", row_list, format_func=lambda x: f"{x} 列")

df_row = df_block[df_block["Row"] == selected_row].sort_values("Number_num")
num_list = df_row["Number"].unique()
with col4:
    selected_num = st.selectbox("席番", num_list, format_func=lambda x: f"{x} 番")

target_seat_key = f"{selected_floor}_{selected_block}_{selected_row}_{selected_num}"

# ==========================================
# 2. 川崎ブレイブサンダース風 インタラクティブSVGマップの生成
# ==========================================
# JSに渡す軽量データ作成
seats_records = df_seats[["SeatName", "Floor", "Block", "Row", "Number", "X_Col", "Y_Row", "Angle"]].to_dict(orient="records")
seats_json = json.dumps(seats_records, ensure_ascii=False)

# 各ブロックの中心座標（ブロック名ラベル表示＆タップでズーム用）
block_centers = (
    df_seats.groupby(["Floor", "Block"])[["X_Col", "Y_Row"]]
    .mean()
    .reset_index()
    .to_dict(orient="records")
)
blocks_json = json.dumps(block_centers, ensure_ascii=False)

html_code = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f8f9fa;
    user-select: none;
  }}
  .toolbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: #ffffff;
    border: 1px solid #dee2e6;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .seat-badge {{
    font-size: 15px;
    font-weight: bold;
    color: #c62828;
    background: #ffebee;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #ef9a9a;
  }}
  .btn-group {{
    display: flex;
    gap: 6px;
  }}
  .btn {{
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid #ced4da;
    background: #ffffff;
    color: #333;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
  }}
  .btn:hover {{ background: #f1f3f5; }}
  .btn-primary {{
    background: #d32f2f;
    color: #fff;
    border-color: #b71c1c;
  }}
  .btn-primary:hover {{ background: #b71c1c; }}
  
  #map-wrapper {{
    width: 100%;
    height: 620px;
    background: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 0 0 8px 8px;
    overflow: hidden;
    position: relative;
    touch-action: none;
    cursor: grab;
  }}
  #map-wrapper:active {{ cursor: grabbing; }}

  /* 座席の基本スタイル */
  .seat {{
    fill: #e0e0e0;
    stroke: #bdbdbd;
    stroke-width: 0.08;
    transition: fill 0.2s;
  }}
  .seat-block-active {{
    fill: #bbdefb;
    stroke: #64b5f6;
    stroke-width: 0.1;
  }}
  /* 選択された座席（赤く発光アニメーション） */
  @keyframes seatPulse {{
    0%   {{ fill: #ff1744; stroke: #ffffff; stroke-width: 0.25; }}
    50%  {{ fill: #ffeb3b; stroke: #d50000; stroke-width: 0.35; }}
    100% {{ fill: #ff1744; stroke: #ffffff; stroke-width: 0.25; }}
  }}
  .seat-target {{
    fill: #ff1744 !important;
    animation: seatPulse 1.2s infinite ease-in-out;
  }}

  /* ズーム前の円状の囲み（パルスアニメーション） */
  @keyframes haloPulse {{
    0%   {{ r: 4.2px; opacity: 0.85; stroke-width: 0.6px; }}
    50%  {{ r: 6.0px; opacity: 0.45; stroke-width: 0.9px; }}
    100% {{ r: 4.2px; opacity: 0.85; stroke-width: 0.6px; }}
  }}
  .target-halo {{
    fill: rgba(255, 235, 59, 0.35);
    stroke: #ff1744;
    animation: haloPulse 1.5s infinite ease-in-out;
    pointer-events: none;
  }}

  .seat-num-text {{
    font-size: 0.45px;
    fill: #ffffff;
    font-weight: bold;
    text-anchor: middle;
    dominant-baseline: central;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s;
  }}

  .hint-bar {{
    position: absolute;
    bottom: 10px;
    left: 12px;
    background: rgba(255,255,255,0.9);
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
    color: #555;
    border: 1px solid #ddd;
    pointer-events: none;
  }}
</style>
</head>
<body>

<div class="toolbar">
  <div class="seat-badge" id="seat-info-text">📍 選択中: -</div>
  <div class="btn-group">
    <button class="btn btn-primary" onclick="zoomToTargetSeat()">🔍 自分の席にズーム</button>
    <button class="btn" onclick="zoomToBlock()">📦 選択ブロックを表示</button>
    <button class="btn" onclick="resetView()">🗺️ 全体を表示</button>
  </div>
</div>

<div id="map-wrapper">
  <svg id="seat-svg" width="100%" height="100%" viewBox="0 0 220 150" preserveAspectRatio="xMidYMid meet">
    <!-- 中央コート・ベンチ案内描画 -->
    <g id="court-layer">
      <rect x="78" y="32" width="60" height="34" rx="1" fill="#fff8e1" stroke="#ffb300" stroke-width="0.5"/>
      <rect x="82" y="35" width="52" height="28" fill="none" stroke="#ffa000" stroke-width="0.3"/>
      <line x1="108" y1="35" x2="108" y2="63" stroke="#ffa000" stroke-width="0.3"/>
      <circle cx="108" cy="49" r="5" fill="none" stroke="#ffa000" stroke-width="0.3"/>
      <text x="108" y="50" font-size="3.2" fill="#ff8f00" font-weight="bold" text-anchor="middle" dominant-baseline="middle" opacity="0.6">COURT</text>
      
      <!-- 方向ラベル -->
      <text x="108" y="22" font-size="2.2" fill="#757575" font-weight="bold" text-anchor="middle">▲ バック側 (1F バックA)</text>
      <text x="108" y="69" font-size="2.2" fill="#757575" font-weight="bold" text-anchor="middle">▼ メイン側 (ベンチ向かい・メインC)</text>
      <text x="72" y="49" font-size="2.0" fill="#757575" font-weight="bold" text-anchor="middle" transform="rotate(-90 72 49)">◀ エンドD (HOME側)</text>
      <text x="145" y="49" font-size="2.0" fill="#757575" font-weight="bold" text-anchor="middle" transform="rotate(90 145 49)">◀ エンドB (AWAY側)</text>
    </g>

    <!-- ズーム時に「座席の裏」に回る円レイヤー -->
    <g id="halo-below-layer"></g>

    <!-- 全座席レイヤー -->
    <g id="seats-layer"></g>

    <!-- ズーム前に「座席の上」に被さる円レイヤー＆ピンラベル -->
    <g id="halo-above-layer"></g>
  </svg>
  <div class="hint-bar">💡 マウスホイールやピンチ操作で拡大縮小・ドラッグで移動できます（拡大すると円が座席の後ろに回ります）</div>
</div>

<script>
const seatsData = {seats_json};
const targetKey = "{target_seat_key}";
const selectedFloor = "{selected_floor}";
const selectedBlock = "{selected_block}";

const svg = document.getElementById("seat-svg");
const seatsLayer = document.getElementById("seats-layer");
const haloBelowLayer = document.getElementById("halo-below-layer");
const haloAboveLayer = document.getElementById("halo-above-layer");
const infoText = document.getElementById("seat-info-text");

let targetSeat = null;
let blockSeats = [];

// 1. 座席をSVGの<rect>として描画（斜め座席はtransform="rotate"で正確に傾ける）
const frag = document.createDocumentFragment();
let targetElem = null;

seatsData.forEach(s => {{
  const isBlock = (s.Floor === selectedFloor && s.Block === selectedBlock);
  const isTarget = (s.SeatName === targetKey);
  if (isBlock) blockSeats.push(s);
  if (isTarget) targetSeat = s;

  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  if (s.Angle !== 0) {{
    g.setAttribute("transform", `translate(${{s.X_Col}}, ${{s.Y_Row}}) rotate(${{s.Angle}})`);
  }} else {{
    g.setAttribute("transform", `translate(${{s.X_Col}}, ${{s.Y_Row}})`);
  }}

  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  const size = isTarget ? 0.95 : 0.82;
  rect.setAttribute("x", -size / 2);
  rect.setAttribute("y", -size / 2);
  rect.setAttribute("width", size);
  rect.setAttribute("height", size);
  rect.setAttribute("rx", 0.12);
  rect.setAttribute("class", isTarget ? "seat seat-target" : (isBlock ? "seat seat-block-active" : "seat"));

  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = `${{s.Floor}} ${{s.Block}} ${{s.Row}}列 ${{s.Number}}番`;
  rect.appendChild(title);
  g.appendChild(rect);

  // 該当席にはズーム時に見える席番テキストも付与
  if (isTarget) {{
    const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("class", "seat-num-text");
    txt.setAttribute("id", "target-seat-text");
    txt.textContent = s.Number;
    g.appendChild(txt);
    targetElem = g;
  }} else {{
    frag.appendChild(g);
  }}
}});

seatsLayer.appendChild(frag);
// 該当の赤い座席を一番最後（最前面）に追加
if (targetElem) seatsLayer.appendChild(targetElem);

// 2. 該当席の円状囲み（ハロー）と吹き出しを描画
let haloCircle = null;
let pinGroup = null;

if (targetSeat) {{
  infoText.textContent = `📍 選択中の座席： ${{targetSeat.Floor}} ${{targetSeat.Block}} ${{targetSeat.Row}}列 ${{targetSeat.Number}}番`;

  haloCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  haloCircle.setAttribute("cx", targetSeat.X_Col);
  haloCircle.setAttribute("cy", targetSeat.Y_Row);
  haloCircle.setAttribute("r", 4.5);
  haloCircle.setAttribute("class", "target-halo");
  haloAboveLayer.appendChild(haloCircle);

  // 吹き出しラベル
  pinGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  pinGroup.setAttribute("transform", `translate(${{targetSeat.X_Col}}, ${{targetSeat.Y_Row}})`);
  pinGroup.innerHTML = `
    <polygon points="0,-0.8 -1.2,-2.8 1.2,-2.8" fill="#d50000"/>
    <rect x="-7.5" y="-6.8" width="15" height="4.2" rx="1" fill="#d50000" stroke="#ffffff" stroke-width="0.25"/>
    <text x="0" y="-4.6" font-size="1.9" fill="#ffffff" font-weight="bold" text-anchor="middle" dominant-baseline="middle">
      ${{targetSeat.Row}}列 ${{targetSeat.Number}}番
    </text>
  `;
  haloAboveLayer.appendChild(pinGroup);
}}

// ==========================================
// 3. パン＆ズーム制御 ＋ ズーム倍率に応じた円の前後切り替え
// ==========================================
let vb = {{ x: 0, y: 0, w: 220, h: 150 }};

function updateViewBox() {{
  svg.setAttribute("viewBox", `${{vb.x}} ${{vb.y}} ${{vb.w}} ${{vb.h}}`);
  
  // ★ ズーム倍率の判定（vb.w が 90 未満＝拡大された状態なら、円を「座席の裏（haloBelowLayer）」へ移動！）
  const isZoomedIn = vb.w < 90;
  if (haloCircle) {{
    if (isZoomedIn && haloCircle.parentNode !== haloBelowLayer) {{
      haloBelowLayer.appendChild(haloCircle);
    }} else if (!isZoomedIn && haloCircle.parentNode !== haloAboveLayer) {{
      haloAboveLayer.insertBefore(haloCircle, pinGroup);
    }}
  }}
  const seatTxt = document.getElementById("target-seat-text");
  if (seatTxt) {{
    seatTxt.style.opacity = (vb.w < 45) ? "1" : "0";
  }}
}}

function animateViewBox(targetVb, duration = 350) {{
  const startVb = {{ ...vb }};
  const startTime = performance.now();
  function step(now) {{
    const t = Math.min((now - startTime) / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);
    vb.x = startVb.x + (targetVb.x - startVb.x) * ease;
    vb.y = startVb.y + (targetVb.y - startVb.y) * ease;
    vb.w = startVb.w + (targetVb.w - startVb.w) * ease;
    vb.h = startVb.h + (targetVb.h - startVb.h) * ease;
    updateViewBox();
    if (t < 1) requestAnimationFrame(step);
  }}
  requestAnimationFrame(step);
}}

function resetView() {{
  animateViewBox({{ x: 0, y: 0, w: 220, h: 150 }});
}}

function zoomToBlock() {{
  if (blockSeats.length === 0) return;
  const xs = blockSeats.map(s => s.X_Col);
  const ys = blockSeats.map(s => s.Y_Row);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 12;
  const w = Math.max(maxX - minX + pad * 2, 35);
  const h = Math.max(maxY - minY + pad * 2, 25);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  animateViewBox({{ x: cx - w / 2, y: cy - h / 2, w: w, h: h }});
}}

function zoomToTargetSeat() {{
  if (!targetSeat) return;
  const w = 32, h = 22;
  animateViewBox({{ x: targetSeat.X_Col - w / 2, y: targetSeat.Y_Row - h / 2, w: w, h: h }});
}}

// マウスホイールでのズーム（スムーズに円の前後が切り替わります）
const wrapper = document.getElementById("map-wrapper");
wrapper.addEventListener("wheel", e => {{
  e.preventDefault();
  const scale = e.deltaY < 0 ? 0.85 : 1.18;
  const rect = svg.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / rect.width;
  const my = (e.clientY - rect.top) / rect.height;
  
  const newW = Math.min(Math.max(vb.w * scale, 18), 240);
  const newH = Math.min(Math.max(vb.h * scale, 12), 165);
  vb.x += (vb.w - newW) * mx;
  vb.y += (vb.h - newH) * my;
  vb.w = newW;
  vb.h = newH;
  updateViewBox();
}}, {{ passive: false }});

// ドラッグ移動
let isDown = false, startX = 0, startY = 0;
wrapper.addEventListener("pointerdown", e => {{
  isDown = true;
  startX = e.clientX;
  startY = e.clientY;
  wrapper.setPointerCapture(e.pointerId);
}});
wrapper.addEventListener("pointermove", e => {{
  if (!isDown) return;
  const rect = svg.getBoundingClientRect();
  const dx = (e.clientX - startX) * (vb.w / rect.width);
  const dy = (e.clientY - startY) * (vb.h / rect.height);
  vb.x -= dx;
  vb.y -= dy;
  startX = e.clientX;
  startY = e.clientY;
  updateViewBox();
}});
wrapper.addEventListener("pointerup", () => {{ isDown = false; }});
</script>
</body>
</html>
"""

components.html(html_code, height=700, scrolling=False)
