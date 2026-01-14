import streamlit as st
import asyncio
import os
import requests
import pandas as pd
from typing import Dict, Any, Optional, List
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types

import math
import re
from utils.mesh_utils import latlon_to_meshcode
from utils.data_processor import load_base_data, aggregate_mesh_data

def safe_float(value):
    """NaNをNoneに変換する安全なfloat変換"""
    try:
        val = float(value)
        if math.isnan(val):
            return 0.0
        return val
    except (ValueError, TypeError):
        return 0.0

# --- Shared Data Loading ---
# Tools will access data via this cached function to avoid reloading CSV every time
@st.cache_data
def get_cached_dataframe():
    csv_path = "data/processed/tblT001227E13.csv"
    return load_base_data(csv_path)

# --- Tools Definition ---

def geocode_address(address: str) -> Dict[str, Any]:
    """
    住所や地名を緯度・経度に変換します。
    
    Args:
        address: 住所、駅名、施設名など (例: "渋谷駅", "東京都新宿区西新宿2-8-1")
        
    Returns:
        JSON形式の結果（緯度 lat、経度 lon を含む）
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        headers = {"User-Agent": "TokyoMeshInsight/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if data:
            return {
                "address": data[0]["display_name"],
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "status": "success"
            }
        return {"status": "error", "message": "Address not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    座標から住所を取得します（逆ジオコーディング）。
    注: 外部API (Nominatim) を使用するため、頻繁な呼び出しは避けてください。
    """
    try:
        import time
        # Nominatim Usage Policy遵守のため、呼び出し間隔を空ける
        time.sleep(1.1)
        
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "accept-language": "ja"
        }
        headers = {"User-Agent": "TokyoMeshInsight/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if data and "display_name" in data:
            # 住所全体を返す
            return data["display_name"]
        return None
    except Exception:
        return None

def get_population_stats(lat: float, lon: float, level: int = 6) -> Dict[str, Any]:
    """
    指定された座標（緯度・経度）の地域メッシュ統計（人口データ）を取得します。
    
    Args:
        lat: 緯度
        lon: 経度
        level: メッシュレベル（1:広域〜6:詳細）。デフォルトは6。
        
    Returns:
        地域名、総人口、年齢層別データなどの統計情報
    """
    try:
        # 座標からメッシュコードを取得
        mesh_code = str(latlon_to_meshcode(lat, lon, level=level))
        
        df = get_cached_dataframe()
        if df is None:
            return {"status": "error", "message": "Stat database not found"}
            
        # 指定レベルで集計
        # NOTE: data_processor.aggregate_mesh_data は全データ処理なので、ここだけの軽い処理を書く
        target_code_prefix = mesh_code # latlon_to_meshcodeが返すのはそのレベルのコード
        
        # 前方一致で抽出して集計
        mask = df["KEY_CODE"].str.startswith(target_code_prefix)
        subset = df[mask]
        
        if subset.empty:
            # データが存在しない場合は、人口0として扱う（夜間人口データのため、都心部商業地などは0になりうる）
            return {
                "mesh_code": mesh_code,
                "level": level,
                "total_population": 0,
                "male": 0,
                "female": 0,
                "average_age": 0.0,
                "median_age": 0.0,
                "status": "success",
                "note": "Data not found in dataset (assumed 0 population)"
            }
            
        # 集計
        total_pop = int(subset["人口（総数）"].sum())
        male = int(subset["人口（総数）　男"].sum())
        female = int(subset["人口（総数）　女"].sum())
        
        # 加重平均
        avg_age = 0.0
        median_age = 0.0
        if total_pop > 0:
            avg_age = safe_float((subset["平均年齢"] * subset["人口（総数）"]).sum() / total_pop)
            median_age = safe_float((subset["年齢中位数"] * subset["人口（総数）"]).sum() / total_pop)
            
        return {
            "mesh_code": mesh_code,
            "level": level,
            "total_population": total_pop,
            "male": male,
            "female": female,
            "average_age": avg_age,
            "median_age": median_age,
            "status": "success"
        }
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_area_ranking(metric: str, n: int = 5, ascending: bool = False, level: int = 4) -> List[Dict[str, Any]]:
    """
    指定された指標でエリアをランク付けし、上位（または下位）N件のエリア情報を返します。
    
    Args:
        metric: ランキングの基準となる指標 ("population", "average_age", "male_ratio", "female_ratio")
        n: 取得件数 (デフォルト5件)
        ascending: Trueなら昇順（値が小さい順）、Falseなら降順（値が大きい順）
        level: メッシュレベル (3:市区町村レベル〜5:街区レベル)。デフォルトは4。
        
    Returns:
        ランキング情報のリスト
    """
    df = get_cached_dataframe()
    if df is None:
        return []
        
    # 指定レベルで集計
    agg_df = aggregate_mesh_data(df, level)
    
    # 指標の計算
    if metric == "population":
        sort_col = "人口（総数）"
    elif metric == "average_age":
        sort_col = "平均年齢"
    elif metric == "male_ratio":
        # 0除算回避
        agg_df["male_ratio"] = (agg_df["人口（総数）　男"] / agg_df["人口（総数）"].replace(0, pd.NA)).fillna(0)
        sort_col = "male_ratio"
    elif metric == "female_ratio":
        agg_df["female_ratio"] = (agg_df["人口（総数）　女"] / agg_df["人口（総数）"].replace(0, pd.NA)).fillna(0)
        sort_col = "female_ratio"
    else:
        sort_col = "人口（総数）"
        
    # 無効値（0など）の除外
    # 特に平均年齢や比率で0が出るのはデータ欠損等のため、ランキングにおいてはノイズとなる
    valid_df = agg_df[agg_df[sort_col] > 0]
    
    # ソート
    result_df = valid_df.sort_values(by=sort_col, ascending=ascending).head(n)
    
    ranking = []
    # 順位付け
    for rank, (idx, row) in enumerate(result_df.iterrows(), 1):
        # 上位には住所情報を付与する (API負荷考慮)
        address = reverse_geocode(row["lat_center"], row["lon_center"])
        
        ranking.append({
            "rank": rank,
            "mesh_code": row["KEY_CODE"],
            "lat": row["lat_center"],
            "lon": row["lon_center"],
            "value": safe_float(row[sort_col]),
            "metric": metric,
            "address": address, # 逆引用住所
            "description": f"Level {level} Mesh Zone"
        })
        
    return ranking

def compare_points(address1: str, address2: str, level: int = 5) -> Dict[str, Any]:
    """
    2つの住所の統計情報を比較します。
    
    Args:
        address1: 比較対象の住所1
        address2: 比較対象の住所2
        level: メッシュレベル（デフォルト5）
        
    Returns:
        2地点の比較データ
    """
    # 1. 住所解決
    loc1 = geocode_address(address1)
    loc2 = geocode_address(address2)
    
    if loc1.get("status") == "error":
        return {"status": "error", "message": f"住所1が見つかりません: {address1}"}
    if loc2.get("status") == "error":
        return {"status": "error", "message": f"住所2が見つかりません: {address2}"}
        
    # 2. 統計取得
    stat1 = get_population_stats(loc1["lat"], loc1["lon"], level)
    stat2 = get_population_stats(loc2["lat"], loc2["lon"], level)
    
    return {
        "location1": {
            "name": address1,
            "coords": loc1,
            "stats": stat1
        },
        "location2": {
            "name": address2,
            "coords": loc2,
            "stats": stat2
        },
        "comparison": {
            "pop_diff": stat1.get("total_population", 0) - stat2.get("total_population", 0),
            "age_diff": safe_float(stat1.get("average_age", 0)) - safe_float(stat2.get("average_age", 0))
        },
        "level": level,
        "status": "success"
    }

# --- ADK Infrastructure ---

APP_NAME = "tokyo_mesh_analyst"
USER_ID = "user_streamlit"

@st.cache_resource
def get_session_service():
    return InMemorySessionService()

def create_adk_runner(session_service, api_key: str = None, model_name: str = "gemini-1.5-flash"):
    
    # 1. Search Agent (Tool Provider)
    search_agent = Agent(
        name="search_agent",
        model=model_name,
        description="住所からデータを取得したり、ランキング作成を行うエージェント。",
        instruction="""あなたはデータ検索のスペシャリストです。
        提供されたツールを使用して、住所を座標に変換し、その場所の人口統計データを正確に取得してください。
        
        **重要なルール**:
        1. **ランキング取得時** (`get_area_ranking`):
           - 結果に住所情報（`address`）が含まれている場合は、必ずそれを報告に含めてください。
           - 値が「0」のデータについては、「データなし（非居住エリア等）」として扱ってください。
           - 質問の粒度に応じて `level` を調整してください（広域=3/4, 詳細=5/6）。
        2. **比較時** (`compare_points`):
           - 2地点の差分データを正確に伝えてください。
           
        推測はせず、ツールから得られた生の数値をそのまま報告してください。""",
        tools=[geocode_address, get_population_stats, get_area_ranking, compare_points]
    )
    
    # 子エージェントをツールとしてラップする
    search_tool = AgentTool(agent=search_agent)
    
    # 2. Analyst Agent (Root)
    root_agent = Agent(
        name="analyst_agent",
        model=model_name,
        instruction="""あなたは「Tokyo Mesh Insight」の専属都市データアナリストです。
        ユーザーの問いかけに対し、search_agent を使って客観的なメッシュ統計データを収集し、都市構造や人口動態の観点から深く解説してください。
        
        ## データの前提
        使用するデータは「地域メッシュ統計（約125mごとの6次メッシュ）」です。
        
        ## 回答のガイドライン
        1. **積極的な姿勢（重要）**:
           - 「〜の特徴は？」のような抽象的な質問に対しても、**聞き返さず**にその地名（例：区役所周辺や代表地点）でデータを取得し、その結果から傾向を分析して回答してください。
           - ユーザーに詳細を聞くのは、地名が全く特定できない場合のみにしてください。
        2. **結論**: 質問に対する直接的な答えを簡潔に述べる。
        3. **データ詳細**:
            - ランキングの場合は、メッシュコードだけでなく「住所（〜付近）」を併記して場所を特定しやすくする。
            - 比較の場合は、具体的な数値差（＋〜人、〜歳若いなど）を示す。
        4. **インサイト（考察）**:
            - なぜその結果になったのか、都市の特性（住宅地、商業地、再開発エリアなど）から推察する。
            - 例：「平均年齢が低いのは、大学・学生街に近接しているためと考えられます。」
            - 例：「人口が0なのは、皇居や大規模公園、あるいは純粋なオフィスビルのためです。」
        5. **トーン**:
            - 知的で分析的だが、冷たくない。
        """,
        tools=[search_tool]
    )
    
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service
    )
    
    return runner

async def init_session(session_id: str):
    session_service = get_session_service()
    try:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id
        )
    except Exception:
        pass
    
    try:
        await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize session {session_id}: {str(e)}")

async def run_agent_chat(user_msg: str, session_id: str, api_key: str = None, model_name: str = "gemini-2.5-flash"):
    await init_session(session_id)
    session_service = get_session_service()
    
    if api_key:
        api_key = api_key.strip()
        os.environ["GOOGLE_API_KEY"] = api_key
        
    try:
        runner = create_adk_runner(session_service, api_key, model_name)
        
        content = genai_types.Content(
            role='user',
            parts=[genai_types.Part(text=user_msg)]
        )
        
        final_text = ""
        max_retries = 5
        retry_delay = 5.0
        
        for attempt in range(max_retries + 1):
            try:
                async for event in runner.run_async(
                    user_id=USER_ID,
                    session_id=session_id,
                    new_message=content
                ):
                    if event.is_final_response():
                        if event.content and event.content.parts:
                            final_text = event.content.parts[0].text
                break
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if attempt < max_retries:
                        match = re.search(r"Please retry in (\d+(\.\d+)?)s", error_str)
                        wait_time = float(match.group(1)) + 1.0 if match else retry_delay
                        if wait_time > 60: wait_time = 60
                        
                        st.warning(f"APIレート制限。{wait_time:.1f}秒後に再試行... ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        retry_delay *= 2
                        continue
                return f"エラーが発生しました: {error_str}"
                    
        return final_text
    finally:
        if api_key and "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
