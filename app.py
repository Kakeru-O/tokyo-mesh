import os
import sys
from typing import Optional, Dict, List, Tuple

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st
import plotly.graph_objects as go

# プロジェクトルートからのインポートを可能にする
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.mesh_utils import meshcode_to_latlon
from utils.adk_service import run_agent_chat, init_session
import uuid
import asyncio
import nest_asyncio
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# Streamlitのイベントループと競合しないようにパッチを適用
nest_asyncio.apply()
import nest_asyncio

# Streamlitのイベントループと競合しないようにパッチを適用
nest_asyncio.apply()

# --- Constants ---
DEFAULT_LAT = 35.6813489
DEFAULT_LON = 139.766029
MESH_LEVEL_MAP = {1: 4, 2: 6, 3: 8, 4: 9, 5: 10, 6: 11}
CSV_PATH = "data/processed/tblT001227E13.csv"

# --- Page Configuration ---
st.set_page_config(
    page_title="Tokyo Mesh Insight AI",
    page_icon="🗼",
    layout="wide",
    initial_sidebar_state="expanded",
)


def apply_custom_css():
    """カスタムCSSを適用してデザインを洗練させる"""
    st.html("""
    <style>
        .main {
            background-color: #0e1117;
        }
        .stApp {
            background: linear-gradient(135deg, #0e1117 0%, #161b22 100%);
        }
        .stSidebar {
            background-color: rgba(22, 27, 34, 0.8);
            border-right: 1px solid #30363d;
        }
        h1, h2, h3 {
            color: #58a6ff;
            font-family: 'Outfit', 'Inter', sans-serif;
            font-weight: 700;
        }
        .stMetric {
            background-color: #161b22;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #30363d;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .metric-label {
            color: #8b949e;
            font-size: 0.9rem;
        }
        .metric-value {
            color: #ffffff;
            font-size: 1.8rem;
            font-weight: 600;
        }
        /* Color Legend Styles */
        .legend-container {
            padding: 10px;
            background: rgba(22, 27, 34, 0.6);
            border-radius: 8px;
            border: 1px solid #30363d;
            margin-top: 10px;
        }
        .legend-bar {
            height: 12px;
            width: 100%;
            background: linear-gradient(to right, #0000ff, #00ffff, #00ff00, #ffff00, #ff0000);
            border-radius: 6px;
        }
        .legend-labels {
            display: flex;
            justify-content: space-between;
            margin-top: 5px;
            color: #8b949e;
            font-size: 0.8rem;
        }

    </style>
    """)


@st.cache_data
def load_base_data() -> Optional[pd.DataFrame]:
    """
    CSVからベースとなるデータを読み込み、基本的な型変換とクレンジングを行う。
    
    Returns:
        pd.DataFrame or None: 読み込み済みのDataFrame
    """
    if not os.path.exists(CSV_PATH):
        st.error(f"データファイルが見つかりません: {CSV_PATH}")
        return None
    
    df = pd.read_csv(CSV_PATH, low_memory=False)
    
    # 統計関連のカラムを数値型に変換
    stat_cols = [c for c in df.columns if any(k in c for k in ["人口", "平均年齢", "年齢中位数"])]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 人口が存在するメッシュのみに絞り込み
    if "人口（総数）" in df.columns:
        df = df[df["人口（総数）"] > 0].copy()
    
    df["KEY_CODE"] = df["KEY_CODE"].astype(str)
    return df


@st.cache_data
def get_aggregated_data(level: int) -> Optional[pd.DataFrame]:
    """
    選択されたメッシュレベルに合わせてデータを集約し、地理情報を付与する。
    
    Args:
        level (int): メッシュ階層 (1-6)
        
    Returns:
        pd.DataFrame or None: 集約済みのデータ
    """
    df = load_base_data()
    if df is None:
        return None
    
    code_len = MESH_LEVEL_MAP.get(level, 11)
    df["TARGET_CODE"] = df["KEY_CODE"].str[:code_len]
    
    # カラムの分類
    pop_cols = [c for c in df.columns if "人口" in c]
    age_cols = [c for c in df.columns if "平均年齢" in c or "年齢中位数" in c]
    
    # 加重平均用の重み計算
    weight_col = "人口（総数）"
    for col in age_cols:
        df[f"_{col}_weighted"] = df[col] * df[weight_col]
    
    # 集計実行
    agg_dict = {col: "sum" for col in pop_cols}
    for col in age_cols:
        agg_dict[f"_{col}_weighted"] = "sum"
        
    agg_df = df.groupby("TARGET_CODE").agg(agg_dict).reset_index()
    
    # 年齢関連の加重平均を算出
    for col in age_cols:
        agg_df[col] = (agg_df[f"_{col}_weighted"] / agg_df[weight_col].replace(0, np.nan)).fillna(0)
        agg_df.drop(columns=[f"_{col}_weighted"], inplace=True)
    
    # 地理情報の計算
    with st.spinner(f"Level {level} の地理情報を計算中..."):
        coords = meshcode_to_latlon(agg_df["TARGET_CODE"], mode="bbox")
        agg_df = pd.concat([agg_df, coords], axis=1)
        
        center_coords = meshcode_to_latlon(agg_df["TARGET_CODE"], mode="center")
        agg_df["lat_center"] = center_coords["lat"]
        agg_df["lon_center"] = center_coords["lon"]
        
        # ポリゴン作成の最適化
        agg_df["polygon"] = agg_df.apply(
            lambda r: [
                [r["min_lon"], r["min_lat"]],
                [r["max_lon"], r["min_lat"]],
                [r["max_lon"], r["max_lat"]],
                [r["min_lon"], r["max_lat"]],
                [r["min_lon"], r["min_lat"]]
            ], axis=1
        )
        agg_df = agg_df.rename(columns={"TARGET_CODE": "KEY_CODE"})
        
    return agg_df


def get_heatmap_color(val: float, max_val: float) -> List[int]:
    """
    値をヒートマップカラー（青→緑→黄→赤）に変換する。
    """
    if max_val <= 0:
        return [0, 0, 255, 140]
    
    normalized = val / max_val
    if normalized < 0.25:
        return [0, int(255 * (normalized / 0.25)), 255, 140]
    elif normalized < 0.5:
        return [0, 255, int(255 * (1 - (normalized - 0.25) / 0.25)), 140]
    elif normalized < 0.75:
        return [int(255 * ((normalized - 0.5) / 0.25)), 255, 0, 140]
    else:
        return [255, int(255 * (1 - (normalized - 0.75) / 0.25)), 0, 160]


def render_sidebar():
    """サイドバーのUI描画と入力取得"""
    st.sidebar.title("🎮 操作パネル")
    
    with st.sidebar.form("filter_form"):
        st.subheader("🌐 メッシュ設定")
        mesh_level = st.slider(
            "メッシュ解像度 (レベル)", 1, 6, 6,
            help="1: 広域(約80km) 〜 6: 詳細(125m)"
        )
        
        st.divider()
        st.subheader("👥 属性フィルタ")
        gender_options = {"全体": "総数", "男": "男", "女": "女"}
        selected_gender = st.radio("性別", list(gender_options.keys()), horizontal=True)
        
        # 年代リスト（高速化のためベースデータから取得）
        cached_df = load_base_data()
        all_cols = cached_df.columns.tolist() if cached_df is not None else []
        age_groups = sorted(
            list(set([c.split("歳")[0] for c in all_cols if "歳人口" in c])),
            key=lambda x: int(x.split("〜")[0]) if "〜" in x else 95
        )
        
        selected_ages = st.multiselect("表示する年代選択", age_groups, placeholder="すべての年代を表示")
        
        st.divider()
        st.subheader("📊 表示モード")
        display_type = st.radio(
            "表示タイプ",
            ["実数 (人数)", "割合 (%)"],
            help="割合: 各メッシュ内での構成比を表示"
        )
        
        submitted = st.form_submit_button("✨ 設定を適用", width="stretch")
        
    return mesh_level, selected_gender, gender_options[selected_gender], selected_ages, display_type, age_groups


def render_metrics(df: pd.DataFrame, raw_val_col: str, gender_label: str):
    """主要なメトリクスをカード形式で表示"""
    m1, m2, m3, m4 = st.columns(4)
    
    total_pop = df[raw_val_col].sum()
    with m1:
        st.html(f"""
        <div class="stMetric">
            <div class="metric-label">👥 フィルター後の人口</div>
            <div class="metric-value">{total_pop:,.0f} <span style="font-size:1rem; font-weight:normal;">人</span></div>
            <div style="color: #8b949e; font-size: 0.8rem; margin-top: 4px;">選択した性別・年代の合計</div>
        </div>
        """)
        
    with m2:
        # ベースとなる総人口（その性別の全年代合計）を表示
        base_total = df["calculated_total"].sum()
        st.html(f"""
        <div class="stMetric">
            <div class="metric-label">🏠 エリア全人口 ({gender_label})</div>
            <div class="metric-value">{base_total:,.0f} <span style="font-size:1rem; font-weight:normal;">人</span></div>
            <div style="color: #8b949e; font-size: 0.8rem; margin-top: 4px;">選択した性別の全年代合計</div>
        </div>
        """)

    with m3:
        st.html(f"""
        <div class="stMetric">
            <div class="metric-label">🗺️ 描画メッシュ数</div>
            <div class="metric-value">{len(df):,} <span style="font-size:1rem; font-weight:normal;">件</span></div>
            <div style="color: #8b949e; font-size: 0.8rem; margin-top: 4px;">現在の解像度での区画数</div>
        </div>
        """)
        
    with m4:
        # 人口加重平均年齢を表示
        if "平均年齢" in df.columns and "calculated_total" in df.columns:
            total_weighted_age = (df["平均年齢"] * df["calculated_total"]).sum()
            total_pop_sum = df["calculated_total"].sum()
            avg_age = total_weighted_age / total_pop_sum if total_pop_sum > 0 else 0
        else:
            avg_age = 0
            
        st.html(f"""
        <div class="stMetric">
            <div class="metric-label">🎂 平均年齢</div>
            <div class="metric-value">{avg_age:.2f} <span style="font-size:1rem; font-weight:normal;">歳</span></div>
            <div style="color: #8b949e; font-size: 0.8rem; margin-top: 4px;">エリア全体の人口構成に基づく</div>
        </div>
        """)


def render_map_legend(unit: str):
    """地図の凡例を表示"""
    st.html(f"""
    <div class="legend-container">
        <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
            <span style="color:#58a6ff; font-weight:bold;">Heatmap Legend ({unit})</span>
        </div>
        <div class="legend-bar"></div>
        <div class="legend-labels">
            <span>低密度 / 小</span>
            <span>高密度 / 大</span>
        </div>
    </div>
    """)


def render_age_gender_chart(df: pd.DataFrame, age_groups: List[str]):
    """性年代別の人口ピラミッドを表示"""
    st.markdown("### 📊 エリア全体の性年代別構成")
    
    chart_container = st.container()
    with chart_container:
        chart_col1, chart_col2 = st.columns([1, 3])
        
        with chart_col1:
            st.markdown("表示設定")
            chart_mode = st.radio(
                "単位を選択",
                ["実数 (人)", "割合 (%)"],
                key="chart_mode",
                horizontal=False,
                label_visibility="collapsed"
            )
            
            # 統計サマリー
            male_total = sum([df[f"{age}歳人口　男"].sum() for age in age_groups])
            female_total = sum([df[f"{age}歳人口　女"].sum() for age in age_groups])
            total_pop = male_total + female_total
            
            if total_pop > 0:
                m_ratio = male_total / total_pop * 100
                f_ratio = female_total / total_pop * 100
                st.html(f"""
                <div style="margin-top: 20px;">
                    <div style="font-size: 0.8rem; color: #8b949e;">性別比率</div>
                    <div style="display: flex; height: 10px; border-radius: 5px; overflow: hidden; margin: 5px 0;">
                        <div style="width: {m_ratio}%; background-color: #58a6ff;"></div>
                        <div style="width: {f_ratio}%; background-color: #ff7f0e;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.75rem;">
                        <span style="color: #58a6ff;">男: {m_ratio:.1f}%</span>
                        <span style="color: #ff7f0e;">女: {f_ratio:.1f}%</span>
                    </div>
                </div>
                """)
        
        # データの集計
        male_counts = []
        female_counts = []
        for age in age_groups:
            male_counts.append(df[f"{age}歳人口　男"].sum())
            female_counts.append(df[f"{age}歳人口　女"].sum())
        
        if chart_mode == "割合 (%)" and total_pop > 0:
            male_plot = [m / total_pop * 100 for m in male_counts]
            female_plot = [f / total_pop * 100 for f in female_counts]
            x_label = "全体人口に対する割合 (%)"
            hover_suffix = "%"
        else:
            male_plot = male_counts
            female_plot = female_counts
            x_label = "人口 (人)"
            hover_suffix = "人"

        fig = go.Figure()
        
        # 男性を左側（負の値）に
        fig.add_trace(go.Bar(
            y=age_groups,
            x=[-x for x in male_plot],
            name="男",
            orientation='h',
            marker=dict(color='#58a6ff', line=dict(color='rgba(255, 255, 255, 0.2)', width=1)),
            hovertemplate='%{y} (男): %{customdata:,.1f}' + hover_suffix,
            customdata=male_plot
        ))
        
        # 女性を右側（正の値）に
        fig.add_trace(go.Bar(
            y=age_groups,
            x=female_plot,
            name="女",
            orientation='h',
            marker=dict(color='#ff7f0e', line=dict(color='rgba(255, 255, 255, 0.2)', width=1)),
            hovertemplate='%{y} (女): %{x:,.1f}' + hover_suffix
        ))
        
        # レイアウト調整
        max_val = max(max(male_plot), max(female_plot)) if male_plot else 0
        
        fig.update_layout(
            barmode='relative',
            height=500,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(
                title=x_label,
                tickvals=[-max_val, -max_val/2, 0, max_val/2, max_val],
                ticktext=[f"{max_val:,.1f}" if chart_mode == "割合 (%)" else f"{max_val:,.0f}", 
                          f"{max_val/2:,.1f}" if chart_mode == "割合 (%)" else f"{max_val/2:,.0f}", 
                          "0", 
                          f"{max_val/2:,.1f}" if chart_mode == "割合 (%)" else f"{max_val/2:,.0f}", 
                          f"{max_val:,.1f}" if chart_mode == "割合 (%)" else f"{max_val:,.0f}"],
                gridcolor="#30363d",
                zerolinecolor="#8b949e",
            ),
            yaxis=dict(
                gridcolor="#30363d",
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            font=dict(color="#8b949e"),
            hoverlabel=dict(bgcolor="#161b22", font_size=13, font_family="Inter")
        )
        
        with chart_col2:
            st.plotly_chart(fig, width="stretch")


def main():
    apply_custom_css()
    
    # メインヘッダー
    st.html("""
        <div style="text-align: left; padding-bottom: 20px;">
            <h1 style="font-size: 2.5rem; margin-bottom: 0;">🗼 Tokyo Mesh Insight AI</h1>
            <p style="color: #8b949e; font-size: 1.1rem;">東京都の地域メッシュ統計を可視化し、都市構造の深層を分析する。</p>
        </div>
    """)
    
    # 1. サイドバー設定 & データ表示設定 (これらを先に実行)
    # 操作パネルからの入力取得
    mesh_level, gender_label, gender_suffix, selected_ages, display_type, age_groups = render_sidebar()

    # --- AI設定 (サイドバーに追加) ---
    with st.sidebar:
        st.divider()
        st.subheader("🤖 AI設定")
        # API Key Input
        api_key = st.text_input("Google AI API Key", type="password", help="Geminiを利用するためのAPIキーを入力してください。")
        
        # Model Selection
        model_name = st.selectbox(
            "モデル選択",
            [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-3-flash",
            ],
            index=0, 
            help="使用するAIモデルを選択してください。"
        )

        # セッション管理
        if "adk_session_id" not in st.session_state:
            st.session_state.adk_session_id = str(uuid.uuid4())
            try:
                asyncio.run(init_session(st.session_state.adk_session_id))
            except Exception as e:
                st.error(f"セッション初期化エラー: {e}")
        
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # チャット履歴クリア
        if st.button("🗑️ 会話履歴をクリア", width="stretch"):
            st.session_state.messages = []
            st.rerun()

    # 2. データのロードと集計・可視化 (AIより先に実行して表示をブロックしない)
    df = get_aggregated_data(mesh_level)
    
    # データがある場合のみ描画
    if df is not None:
        # 1. 秘匿データ対応の分母再計算
        age_cols_to_sum = [f"{age}歳人口　{gender_suffix}" for age in age_groups]
        if gender_suffix == "総数":
             age_cols_to_sum = [f"{age}歳人口　総数" for age in age_groups]
        
        df["calculated_total"] = df[age_cols_to_sum].sum(axis=1)

        # 2. 表示値（分子）の決定
        if selected_ages:
            target_cols = [f"{age}歳人口　{gender_suffix}" for age in selected_ages]
            if gender_suffix == "総数":
                 target_cols = [f"{age}歳人口　総数" for age in selected_ages]
            
            display_name = f"{gender_label}: {', '.join(selected_ages)}"
            df["raw_value"] = df[target_cols].sum(axis=1)
        else:
            display_name = f"{gender_label}: 全年代"
            df["raw_value"] = df["calculated_total"]

        # 表示モードに応じた値の計算 (実数 or 割合)
        if display_type == "割合 (%)":
            df["display_value"] = (df["raw_value"] / df["calculated_total"].replace(0, np.nan) * 100).fillna(0)
            df["formatted_value"] = df["display_value"].map(lambda x: f"{x:.2f}%")
            unit_label = "%"
        else:
            df["display_value"] = df["raw_value"]
            df["formatted_value"] = df["display_value"].map(lambda x: f"{x:,.0f} 人")
            unit_label = "人"
            
        # メトリクス表示
        render_metrics(df, "raw_value", gender_label)

        # 性年代別チャートの表示
        st.divider()
        render_age_gender_chart(df, age_groups)

        # 地図セクション
        st.divider()
        st.markdown(f"### 🗺️ {display_name} の分布 ({display_type})")
        
        max_val = df["display_value"].max()
        df["fill_color"] = df["display_value"].apply(lambda v: get_heatmap_color(v, max_val))

        df["formatted_age"] = df["平均年齢"].map(lambda x: f"{x:.2f}")

        map_data = df[[
            "polygon", "fill_color", "display_value", "formatted_value", "formatted_age", "KEY_CODE", "lat_center", "lon_center"
        ]]

        # 地図レイヤーの設定
        layer = pdk.Layer(
            "PolygonLayer",
            data=map_data,
            get_polygon="polygon",
            get_fill_color="fill_color",
            get_line_color=[255, 255, 255, 0],
            pickable=True,
            auto_highlight=True,
        )

        view_state = pdk.ViewState(
            latitude=df["lat_center"].mean() if not df.empty else DEFAULT_LAT,
            longitude=df["lon_center"].mean() if not df.empty else DEFAULT_LON,
            zoom=9,
            pitch=0,
        )

        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={
                "html": "メッシュコード: {KEY_CODE}<br/>"
                        f"<b>{display_name}:</b> {{formatted_value}}<br/>"
                        "平均年齢: {formatted_age} 歳",
                "style": {"backgroundColor": "#161b22", "color": "white", "border": "1px solid #30363d"}
            },
            map_style=None
        ))
        render_map_legend(unit_label)

    # 3. AI Assistant (メインエリア下部に配置)
    st.divider()
    st.subheader("🤖 AI Assistant")
    st.caption("地図に表示されているエリアについて質問したり、分析を依頼できます。")

    # チャット履歴の表示
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"]) # Markdownとしてレンダリングされる

    # チャット入力
    if prompt := st.chat_input("渋谷駅周辺の30代の人口は？"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        
        # AI応答の取得と表示
        with st.chat_message("assistant"):
            if not api_key:
                st.error("左側のサイドバーでAPIキーを設定してください。")
            else:
                with st.spinner("AIが分析中..."):
                    try:
                        # 非同期関数を同期的に実行
                        response = asyncio.run(run_agent_chat(prompt, st.session_state.adk_session_id, api_key, model_name))
                        st.write(response) # ストリーミング風に表示したい場合は別途実装が必要だが、まずはwriteで一括表示
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.error(f"AIエラー: {str(e)}")


if __name__ == "__main__":
    main()
