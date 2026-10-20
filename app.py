import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ==========================================
# ページ設定（スマホでも見やすいレイアウト）
# ==========================================
st.set_page_config(
    page_title="アリーナ座席検索マップ",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🏀 アリーナ 座席検索マップ")
st.caption("お手元のチケットに記載されている「階・エリア」「ブロック」「列」「番号」を選択してください。マップ上であなたの座席が光ります。")

# ==========================================
# データ読み込み＆整形（キャッシュで高速化）
# ==========================================
@st.cache_data
def load_seat_master(csv_path):
    df = pd.read_csv(csv_path)
    
    # "1F_バックA_7_1" のように「_」が3つある有効な座席データのみを抽出
    # （マスタ内の「コートエンドSS」「5列」などの文字ラベル行を除外）
    valid_mask = df["SeatName"].astype(str).str.count("_") == 3
    df_valid = df[valid_mask].copy()
    
    # アンダースコアで4つの要素に分割
    parts = df_valid["SeatName"].str.split("_", expand=True)
    df_valid["Floor"] = parts[0]
    df_valid["Block"] = parts[1]
    df_valid["Row"] = parts[2]
    df_valid["Number"] = parts[3]
    
    # 列と番号を数値順（1, 2, 3... 10）で綺麗に並べるためのソート用カラム
    df_valid["Row_num"] = pd.to_numeric(df_valid["Row"], errors="coerce").fillna(999).astype(int)
    df_valid["Number_num"] = pd.to_numeric(df_valid["Number"], errors="coerce").fillna(999).astype(int)
    
    # 表示用のわかりやすい座席名
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

# ① 階・フロアの選択（1F, 2F, 3F, VIPの順）
floor_order = [f for f in ["1F", "2F", "3F", "VIP"] if f in df_seats["Floor"].unique()]
with col1:
    selected_floor = st.selectbox("① 階・フロア", floor_order)

# ② ブロックの選択（選んだ階に存在するブロックのみ表示）
df_floor = df_seats[df_seats["Floor"] == selected_floor]
block_list = sorted(df_floor["Block"].unique())
with col2:
    selected_block = st.selectbox("② エリア・ブロック", block_list)

# ③ 列（Row）の選択（数値順にソート）
df_block = df_floor[df_floor["Block"] == selected_block].sort_values("Row_num")
row_list = df_block["Row"].unique()
with col3:
    selected_row = st.selectbox("③ 列", row_list, format_func=lambda x: f"{x} 列")

# ④ 席番号（Number）の選択（数値順にソート）
df_row = df_block[df_block["Row"] == selected_row].sort_values("Number_num")
num_list = df_row["Number"].unique()
with col4:
    selected_num = st.selectbox("④ 番", num_list, format_func=lambda x: f"{x} 番")

# 選択された1席を特定
target_seat_key = f"{selected_floor}_{selected_block}_{selected_row}_{selected_num}"
target_df = df_seats[df_seats["SeatName"] == target_seat_key]

# ==========================================
# 2. 選択結果の案内バナーと表示オプション
# ==========================================
opt_col1, opt_col2 = st.columns([3, 1])
with opt_col1:
    if not target_df.empty:
        disp_name = target_df.iloc[0]["DisplayName"]
        st.success(f"📍 選択中の座席： **{disp_name}** （マップ上の赤い星マークの場所です）")
with opt_col2:
    # 全体を見たいか、そのブロック周辺に拡大したいかを選べるスイッチ
    zoom_to_block = st.toggle("🔍 選んだブロック周辺を拡大する", value=False)

# ==========================================
# 3. マップ描画（3レイヤー構造で光らせる）
# ==========================================
fig = go.Figure()

# 【レイヤー1】会場全体の座席（薄いグレー）
other_blocks_df = df_seats[df_seats["SeatName"] != target_seat_key]
fig.add_trace(go.Scattergl(
    x=other_blocks_df["X_Col"],
    y=other_blocks_df["Y_Row"],
    mode="markers",
    marker=dict(symbol="square", size=7, color="#e0e0e0"),
    hoverinfo="text",
    text=other_blocks_df["DisplayName"],
    name="他エリアの座席"
))

# 【レイヤー2】選択中のブロック全体（水色でブロックの位置をわかりやすく表示）
fig.add_trace(go.Scattergl(
    x=df_block["X_Col"],
    y=df_block["Y_Row"],
    mode="markers",
    marker=dict(symbol="square", size=8, color="#90caf9", line=dict(width=0.5, color="#42a5f5")),
    hoverinfo="text",
    text=df_block["DisplayName"],
    name=f"{selected_floor} {selected_block}"
))

# 【レイヤー3】あなたの座席（光るハロー効果 ＋ 赤い星マーカー ＋ 吹き出し）
if not target_df.empty:
    tx = target_df.iloc[0]["X_Col"]
    ty = target_df.iloc[0]["Y_Row"]
    t_name = target_df.iloc[0]["DisplayName"]

    # 背後の光（半透明の黄色い大きな円）
    fig.add_trace(go.Scatter(
        x=[tx], y=[ty],
        mode="markers",
        marker=dict(symbol="circle", size=38, color="rgba(255, 215, 0, 0.45)", line=dict(width=2, color="#ff9800")),
        hoverinfo="skip",
        showlegend=False
    ))

    # 中心の座席マーカー（赤い星）
    fig.add_trace(go.Scatter(
        x=[tx], y=[ty],
        mode="markers",
        marker=dict(symbol="star", size=18, color="#ff1744", line=dict(width=1.5, color="white")),
        hoverinfo="text",
        text=[f"★ あなたの座席: {t_name}"],
        name="あなたの座席"
    ))

    # 吹き出しラベル（「あなたの席」と矢印で指す）
    fig.add_annotation(
        x=tx, y=ty,
        text=f"<b>★ {selected_row}列 {selected_num}番</b>",
        showarrow=True,
        arrowhead=2,
        arrowsize=1.2,
        arrowwidth=2,
        arrowcolor="#d50000",
        ax=0,
        ay=-40,
        bgcolor="#ff1744",
        font=dict(color="white", size=13),
        bordercolor="white",
        borderwidth=1.5,
        borderpad=4
    )

# 拡大モードがONのときは選択ブロックの周辺にフォーカスする
if zoom_to_block and not df_block.empty:
    pad = 15
    x_range = [df_block["X_Col"].min() - pad, df_block["X_Col"].max() + pad]
    y_range = [df_block["Y_Row"].max() + pad, df_block["Y_Row"].min() - pad] # Y軸は反転のためmaxが先
else:
    x_range = None
    y_range = None

# レイアウト調整（元のダッシュボードと同じ比率・Y軸反転を維持）
fig.update_yaxes(autorange="reversed" if not zoom_to_block else None, range=y_range, visible=False)
fig.update_xaxes(range=x_range, visible=False, scaleanchor="y", scaleratio=1)
fig.update_layout(
    plot_bgcolor="white",
    height=650,
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    dragmode="pan" # スマホで指でスワイプして移動しやすくする設定
)

st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "scrollZoom": True})