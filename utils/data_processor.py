import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Literal
from utils.mesh_utils import meshcode_to_latlon

MESH_LEVEL_MAP = {1: 4, 2: 6, 3: 8, 4: 9, 5: 10, 6: 11}

def process_census_txt_to_csv(
    input_path: str, output_path: str, encoding: str = "shift_jis"
) -> None:
    """
    国勢調査のテキストファイル(Shift-JIS)をCSV(UTF-8)に変換する。
    1行目のコードと2行目のラベルを組み合わせてヘッダーを作成する。

    Args:
        input_path (str): 入力テキストファイルのパス
        output_path (str): 出力CSVファイルのパス
        encoding (str): 入力ファイルのエンコーディング。デフォルトは "shift_jis"
    """
    input_file = Path(input_path)
    output_file = Path(output_path)

    # 入力ファイルが存在するか確認
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # ヘッダーの処理
    with open(input_file, "r", encoding=encoding) as f:
        # 1行目: コード名 (KEY_CODE, HTKSYORI, etc.)
        line1 = f.readline().strip().split(",")
        # 2行目: 日本語ラベル (人口（総数）, etc.)
        line2 = f.readline().strip().split(",")

    # ヘッダーの結合
    # 2行目にラベルがある場合はそれを使用し、ない場合は1行目のコードを使用する
    headers = []
    for code, label in zip(line1, line2):
        clean_label = label.strip()
        if clean_label:
            headers.append(clean_label)
        else:
            headers.append(code.strip())

    # データの読み込み
    # 最初の2行はヘッダーとして処理済みなのでスキップ
    # '*' は欠損値として扱う
    df = pd.read_csv(
        input_file,
        encoding=encoding,
        skiprows=2,
        names=headers,
        na_values="*",
        dtype={
            headers[0]: str,  # KEY_CODE
            headers[1]: str,  # HTKSYORI
            headers[2]: str,  # HTKSAKI
            headers[3]: str,  # GASSAN
        },
        low_memory=False,
    )

    # 出力ディレクトリの作成
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # CSVとして保存
    df.to_csv(output_file, index=False, encoding="utf-8")
    print(f"Successfully processed and saved to: {output_path}")

def load_base_data(csv_path: str) -> Optional[pd.DataFrame]:
    """
    CSVからベースとなるデータを読み込み、基本的な型変換とクレンジングを行う。
    app.py と adk_service.py で共通利用。
    """
    if not os.path.exists(csv_path):
        return None
    
    df = pd.read_csv(csv_path, low_memory=False)
    
    # 統計関連のカラムを数値型に変換
    stat_cols = [c for c in df.columns if any(k in c for k in ["人口", "平均年齢", "年齢中位数"])]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 人口が存在するメッシュのみに絞り込み
    if "人口（総数）" in df.columns:
        df = df[df["人口（総数）"] > 0].copy()
    
    df["KEY_CODE"] = df["KEY_CODE"].astype(str)
    return df

def aggregate_mesh_data(df: pd.DataFrame, level: int) -> pd.DataFrame:
    """
    指定されたメッシュレベルに合わせてデータを集約し、地理情報を付与する。
    """
    code_len = MESH_LEVEL_MAP.get(level, 11)
    df = df.copy()
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
    center_coords = meshcode_to_latlon(agg_df["TARGET_CODE"], mode="center")
    agg_df["lat_center"] = center_coords["lat"]
    agg_df["lon_center"] = center_coords["lon"]
    
    agg_df = agg_df.rename(columns={"TARGET_CODE": "KEY_CODE"})
        
    return agg_df

if __name__ == "__main__":
    # プロジェクトルートからの相対パス
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_PATH = BASE_DIR / "data" / "raw" / "tblT001227E13.txt"
    PROCESSED_PATH = BASE_DIR / "data" / "processed" / "tblT001227E13.csv"

    process_census_txt_to_csv(str(RAW_PATH), str(PROCESSED_PATH))
