import streamlit as st
import asyncio
import os
import requests
import pandas as pd
from typing import Dict, Any, Optional
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types

import math

import re
from utils.mesh_utils import latlon_to_meshcode

def safe_float(value):
    """NaNをNoneに変換する安全なfloat変換"""
    try:
        val = float(value)
        if math.isnan(val):
            return 0.0 # または None だが、数値計算するなら0の方が安全かもしれない。ここでは0とする。
        return val
    except (ValueError, TypeError):
        return 0.0

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

@st.cache_data
def load_data_for_tools():
    """ツール用のデータをロードしてキャッシュします。"""
    csv_path = "data/processed/tblT001227E13.csv"
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path, low_memory=False)
    return None

def get_population_stats(lat: float, lon: float) -> Dict[str, Any]:
    """
    指定された座標（緯度・経度）の地域メッシュ統計（人口データ）を取得します。
    
    Args:
        lat: 緯度
        lon: 経度
        
    Returns:
        地域名、総人口、年齢層別データなどの統計情報
    """
    try:
        # メッシュコード（6次メッシュ）に変換
        mesh_code = str(latlon_to_meshcode(lat, lon, level=6))
        
        df = load_data_for_tools()
        if df is None:
            return {"status": "error", "message": "Stat database not found"}
            
        # KEY_CODEは文字列として比較
        match = df[df["KEY_CODE"].astype(str) == mesh_code]
        
        if not match.empty:
            row = match.iloc[0]
            stats = {
                "mesh_code": mesh_code,
                "total_population": int(row.get("人口（総数）", 0)),
                "male": int(row.get("人口（総数）　男", 0)),
                "female": int(row.get("人口（総数）　女", 0)),
                "average_age": safe_float(row.get("平均年齢", 0)),
                "median_age": safe_float(row.get("年齢中位数", 0)),
                "status": "success"
            }
            return stats
        
        return {"status": "error", "message": f"No data found for mesh {mesh_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- ADK Infrastructure ---

APP_NAME = "tokyo_mesh_analyst"
USER_ID = "user_streamlit"

@st.cache_resource
def get_session_service():
    """
    セッションサービス（会話履歴の保存場所）のみをキャッシュします。
    RunnerやAgentはキャッシュせず、毎回このSessionServiceを使って動かします。
    """
    return InMemorySessionService()

def create_adk_runner(session_service, api_key: str = None, model_name: str = "gemini-1.5-flash"):
    """
    実行のたびに新しいRunnerとAgentを作成します。
    これにより、常に現在の有効なイベントループにバインドされます。
    """
    
    # 1. 検索専用エージェント (Data Fetcher)
    search_agent = Agent(
        name="search_agent",
        model=model_name,
        description="住所から座標を特定し、その場所の人口統計データを取得します。",
        instruction="""あなたはデータ収集の専門家です。
        提供されたツールを使用して、住所を座標に変換し、その場所の人口統計データを正確に取得してください。
        生データをそのまま報告することに徹してください。""",
        tools=[geocode_address, get_population_stats]
    )
    
    # 子エージェントをツールとしてラップする
    search_tool = AgentTool(agent=search_agent)
    
    # 2. 分析・対話エージェント (Analyst)
    root_agent = Agent(
        name="analyst_agent",
        model=model_name,
        instruction="""あなたは「Tokyo Mesh Insight」のメインアナリストです。
        ユーザーの要望に応じて search_agent にデータ取得を依頼し、得られた結果を分析して報告してください。
        
        回答のガイドライン:
        1. 統計データに基づき、そのエリアの特性（例：若者が多い、単身世帯が多いなど）を推察してください。
        2. エリアに対して、統計的特徴を捉えたユニークで魅力的な名前を付けてください（例: "クリエイティブ・ハブ・渋谷"）。
        3. 専門用語は避け、親しみやすく知的なトーンで話してください。""",
        tools=[search_tool]
    )
    
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service
    )
    
    return runner

async def init_session(session_id: str):
    """ セッションを初期化します（存在しない場合は作成）。 """
    session_service = get_session_service()
    try:
        # まずセッションを作成してみる
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id
        )
    except Exception:
        # 作成に失敗した場合（既に存在するなど）は無視して取得確認へ
        pass
    
    # 念のため存在確認（なければここでエラーになるのでキャッチ可能）
    try:
        await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    except Exception as e:
        # ここで失敗する場合は本当に作成できていない
        raise RuntimeError(f"Failed to initialize session {session_id}: {str(e)}")

async def run_agent_chat(user_msg: str, session_id: str, api_key: str = None, model_name: str = "gemini-1.5-flash"):
    """ エージェントを実行し、最終的な回答を返します。 """
    # 実行直前にセッションの存在を保証する
    await init_session(session_id)
    
    session_service = get_session_service()
    
    # Session APIKeyの設定
    if api_key:
        api_key = api_key.strip()
        try:
            api_key.encode('ascii')
        except UnicodeEncodeError:
            return "エラー: APIキーに無効な文字が含まれています。半角英数であることを確認してください。"
            
        os.environ["GOOGLE_API_KEY"] = api_key
        
    try:
        runner = create_adk_runner(session_service, api_key, model_name) # create_adk_runnerのシグネチャ変更に伴い引数は不要かもしれないが、念のため残すか除去するか。ここではEnvVar設定済みなので引数不要だが、前の変更で残っている。
        # create_adk_runnerはEnvVar設定を除去したので、単にRunnerを返すだけになる。
        # 引数は無視される（前のステップで定義変更が必要）。
        
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
                
                # 成功したらループを抜ける
                break
                
            except Exception as e:
                error_str = str(e)
                # 429 RESOURCE_EXHAUSTED の場合のみリトライ
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if attempt < max_retries:
                        # エラーメッセージから待機時間を抽出
                        # "Please retry in 31.817954139s." のようなパターンを探す
                        wait_time = retry_delay
                        match = re.search(r"Please retry in (\d+(\.\d+)?)s", error_str)
                        if match:
                            wait_time = float(match.group(1)) + 1.0 # バッファとして1秒追加
                        
                        # 待機時間が長すぎる場合はUIで通知したほうがいいかもしれないが、
                        # ここでは最大60秒程度まで待機してリトライする方針とする
                        if wait_time > 60:
                            wait_time = 60
                            
                        st.warning(f"APIレート制限にかかりました。{wait_time:.1f}秒後に再試行します... ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        
                        # 指数バックオフも併用（解析できなかった場合用）
                        retry_delay *= 2
                        continue
                
                # その他のエラー、またはリトライ回数上限の場合はエラーを返す
                return f"申し訳ありません、処理中にエラーが発生しました: {error_str}"
                    
        return final_text
    finally:
        # 実行終了後に必ず削除
        if api_key and "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
