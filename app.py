import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ==========================================
# ページ設定
# ==========================================
st.set_page_config(
    page_title="アリーナ座席検索マップ",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🏀 アリーナ 座席検索マップ")
st.caption("お手元のチケットに記載されている「階・エリア」「ブロック」「列」「番号」を選択してください。マップ上であなたの座席が赤く光ります。")

# ==========================================
# データ読み込み＆整形
# ==========================================
@st.cache_data
def load_seat_master(csv_path):
    df = pd.read_csv(csv_path)
    
    # "1F_バックA_7_1" のように「_」が3つある有効な座席データのみを抽出
    valid_mask = df["SeatName"].astype(str).str.count("_") == 3
    df_valid = df[valid_mask].copy()
    
    parts = df_valid["SeatName"].str.split("_", expand=True)
    df_valid["Floor"] = parts[0]
    df_valid["Block"] = parts[1]
    df_valid["Row"] = parts[2]
    df_valid["Number"] = parts[3]
    
    df_valid["Row_num"] = pd.to_numeric(df_valid["Row"], errors="coerce").fillna(999).astype(int)
    df_valid["Number_num"] = pd.to_numeric(df_valid["Number"], errors="coerce").fillna(999).astype(int)
    
    df_valid["DisplayName"] = (
        df_valid["Floor"] + " " + 
        df_valid["Block"] + " " + 
        df_valid["Row"] + "列 " + 
        df_valid["Number"] + "番"
    )
    return df_valid

try:
    df_seats = load_seat_master("座標マスタ.csv")
except FileNotFoundError:
    st.error("⚠️ 座席データ（座標マスタ.csv）が見つかりません。")
    st.stop()

# ==========================================
# 1. 座席の選択UI（連動型プルダウン）
# ==========================================
st.markdown("##### 🔍 座席をえらぶ")
col1, col2, col3, col4 = st.columns(4)

floor_order = [f for f in ["1F", "2F", "3F", "VIP"] if f in df_seats["Floor"].unique()]
with col1:
    selected_floor = st.selectbox("① 階・フロア", floor_order)

df_floor = df_seats[df_seats["Floor"] == selected_floor]
block_list = sorted(df_floor["Block"].unique())
with col2:
    selected_block = st.selectbox("② エリア・ブロック", block_list)

df_block = df_floor[df_floor["Block"] == selected_block].sort_values("Row_num")
row_list = df_block["Row"].unique()
with col3:
    selected_row = st.selectbox("③ 列", row_list, format_func=lambda x: f"{x} 列")

df_row = df_block[df_block["Row"] == selected_row].sort_values("Number_num")
num_list = df_row["Number"].unique()
with col4:
    selected_num = st.selectbox("④ 番", num_list, format_func=lambda x: f"{x} 番")

target_seat_key = f"{selected_floor}_{selected_block}_{selected_row}_{selected_num}"
target_df = df_seats[df_seats["SeatName"] == target_seat_key]

# ==========================================
# 2. 案内バナーと拡大スイッチ
# ==========================================
opt_col1, opt_col2 = st.columns([3, 1])
with opt_col1:
    if not target_df.empty:
        disp_name = target_df.iloc[0]["DisplayName"]
        st.success(f"📍 選択中の座席： **{disp_name}** （マップ上の赤い座席マスの場所です）")
with opt_col2:
    zoom_to_block = st.toggle("🔍 選んだブロック周辺を拡大する", value=False)

# ==========================================
# 3. マップ描画（全て通常のScatterで統一し、重なり順を完全制御）
# ==========================================
fig = go.Figure()

# ① 他ブロックの座席（薄いグレーの四角）
other_blocks_df = df_seats[df_seats["Block"] != selected_block]
fig.add_trace(go.Scatter(
    x=other_blocks_df["X_Col"],
    y=other_blocks_df["Y_Row"],
    mode="markers",
    marker=dict(symbol="square", size=7, color="#e8e8e8", line=dict(width=0.5, color="#cccccc")),
    hoverinfo="text",
    text=other_blocks_df["DisplayName"],
    name="他エリアの座席"
))

# ② 選択中のブロックの座席（水色の四角 ※選択された1席を除く）
same_block_others = df_block[df_block["SeatName"] != target_seat_key]
fig.add_trace(go.Scatter(
    x=same_block_others["X_Col"],
    y=same_block_others["Y_Row"],
    mode="markers",
    marker=dict(symbol="square", size=8, color="#bbdefb", line=dict(width=0.5, color="#64b5f6")),
    hoverinfo="text",
    text=same_block_others["DisplayName"],
    name=f"{selected_floor} {selected_block}"
))

# ③ 該当の1席（真っ赤な四角マス ＋ 円状の囲み）
if not target_df.empty:
    tx = float(target_df.iloc[0]["X_Col"])
    ty = float(target_df.iloc[0]["Y_Row"])
    t_name = target_df.iloc[0]["DisplayName"]

    # 該当の座席マス自体を「赤色（#ff1744）」にする
    fig.add_trace(go.Scatter(
        x=[tx],
        y=[ty],
        mode="markers",
        marker=dict(
            symbol="square",
            size=14 if zoom_to_block else 11,
            color="#ff1744",  # 鮮やかな赤色
            line=dict(width=2, color="#ffffff")
        ),
        hoverinfo="text",
        text=[f"★ あなたの座席: {t_name}"],
        name="あなたの座席"
    ))

    # 円状の囲み（ズーム前は座席より上 "above"、ズーム時は座席の裏 "below" に自動切り替え）
    radius = 4.5  # マップ座標上の半径（約4〜5席分の広がり）
    fig.add_shape(
        type="circle",
        xref="x", yref="y",
        x0=tx - radius, y0=ty - radius,
        x1=tx + radius, y1=ty + radius,
        fillcolor="rgba(255, 235, 59, 0.35)" if not zoom_to_block else "rgba(255, 235, 59, 0.45)",
        line=dict(color="#ff1744", width=2.5),
        layer="above" if not zoom_to_block else "below"
    )

    # 吹き出しラベル
    fig.add_annotation(
        x=tx, y=ty,
        text=f"<b>{selected_row}列 {selected_num}番</b>",
        showarrow=True,
        arrowhead=2,
        arrowsize=1.2,
        arrowwidth=2,
        arrowcolor="#d50000",
        ax=0,
        ay=-38,
        bgcolor="#ff1744",
        font=dict(color="white", size=13),
        bordercolor="white",
        borderwidth=1.5,
        borderpad=4
    )

# 拡大モードONのときは選択ブロックの周辺にフォーカス
if zoom_to_block and not df_block.empty:
    pad = 12
    x_range = [df_block["X_Col"].min() - pad, df_block["X_Col"].max() + pad]
    y_range = [df_block["Y_Row"].max() + pad, df_block["Y_Row"].min() - pad]
else:
    x_range = None
    y_range = None

# レイアウト調整（元のダッシュボードと同じ座標系・アスペクト比固定）
fig.update_yaxes(autorange="reversed" if not zoom_to_block else None, range=y_range, visible=False)
fig.update_xaxes(range=x_range, visible=False, scaleanchor="y", scaleratio=1)
fig.update_layout(
    plot_bgcolor="white",
    height=680,
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    dragmode="pan"
)

st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "scrollZoom": True})
