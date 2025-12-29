import numpy as np
import pandas as pd
from typing import Union, Dict, Tuple


def latlon_to_meshcode(
    lat: Union[float, np.ndarray, pd.Series],
    lon: Union[float, np.ndarray, pd.Series],
    level: int = 3
) -> Union[str, pd.Series]:
    """
    緯度経度をメッシュコードに変換する。レベル1〜6に対応。

    Args:
        lat: 緯度
        lon: 経度
        level: メッシュ階層 (1-6)

    Returns:
        mesh_code: メッシュコード（文字列またはSeries）
    """
    # NumPy配列に変換して一括処理
    lat = np.array(lat)
    lon = np.array(lon)

    # --- 1次メッシュ ---
    t_lat1 = lat * 1.5
    t_lon1 = lon - 100.0
    m1_lat = t_lat1.astype(int)
    m1_lon = t_lon1.astype(int)
    
    # 1次メッシュコード: "lat(2)lon(2)"
    mesh_code = m1_lat.astype(str) + np.char.zfill(m1_lon.astype(str), 2)
    if level == 1:
        return mesh_code if isinstance(mesh_code, np.ndarray) else str(mesh_code)

    # --- 2次メッシュ ---
    rem_lat1 = t_lat1 - m1_lat
    rem_lon1 = t_lon1 - m1_lon
    t_lat2 = rem_lat1 * 8
    t_lon2 = rem_lon1 * 8
    m2_lat = t_lat2.astype(int)
    m2_lon = t_lon2.astype(int)
    
    mesh_code = mesh_code + m2_lat.astype(str) + m2_lon.astype(str)
    if level == 2:
        return mesh_code

    # --- 3次メッシュ ---
    rem_lat2 = t_lat2 - m2_lat
    rem_lon2 = t_lon2 - m2_lon
    t_lat3 = rem_lat2 * 10
    t_lon3 = rem_lon2 * 10
    m3_lat = t_lat3.astype(int)
    m3_lon = t_lon3.astype(int)
    
    mesh_code = mesh_code + m3_lat.astype(str) + m3_lon.astype(str)
    if level == 3:
        return mesh_code

    # --- 4次〜6次メッシュ ---
    # 分割数はすべて2x2。コード割り当てロジックは共通。
    curr_t_lat = t_lat3
    curr_t_lon = t_lon3
    curr_m_lat = m3_lat
    curr_m_lon = m3_lon

    for _ in range(4, level + 1):
        rem_lat = curr_t_lat - curr_m_lat
        rem_lon = curr_t_lon - curr_m_lon
        
        t_lat = rem_lat * 2
        t_lon = rem_lon * 2
        
        m_lat = t_lat.astype(int)
        m_lon = t_lon.astype(int)
        
        # コード = m_lat * 2 + m_lon + 1
        code = (m_lat * 2 + m_lon + 1).astype(str)
        mesh_code = mesh_code + code
        
        # 次のループ用の更新
        curr_t_lat, curr_t_lon = t_lat, t_lon
        curr_m_lat, curr_m_lon = m_lat, m_lon

    return mesh_code


def meshcode_to_latlon(
    mesh_code: Union[str, int, pd.Series],
    mode: str = "sw"
) -> Union[Dict[str, float], pd.DataFrame]:
    """
    メッシュコードを緯度経度に変換する。レベル1〜6に対応。

    Args:
        mesh_code: メッシュコード（文字列、数値、またはSeries）
        mode: 位置指定 ("sw": 南西端, "center": 中心点, "bbox": 境界ボックス)

    Returns:
        Dict または DataFrame (lat, lon, または min_lat, min_lon, max_lat, max_lon)
    """
    if isinstance(mesh_code, pd.Series):
        return _meshcode_to_latlon_vectorized(mesh_code.astype(str), mode)
    elif isinstance(mesh_code, (list, np.ndarray)):
        return _meshcode_to_latlon_vectorized(pd.Series(mesh_code).astype(str), mode)
    else:
        # スカラー処理
        res = _meshcode_to_latlon_vectorized(pd.Series([str(mesh_code)]), mode)
        return res.iloc[0].to_dict()


def _meshcode_to_latlon_vectorized(s_code: pd.Series, mode: str) -> pd.DataFrame:
    """内部用：ベクトル化された変換処理"""
    n = len(s_code)
    # 緯度・経度の増分（1次メッシュ基準）
    lat_delta = np.full(n, 2.0 / 3.0)
    lon_delta = np.full(n, 1.0)
    
    # 1次メッシュ部分 (1-4文字)
    lat = s_code.str[0:2].astype(float) * lat_delta
    lon = s_code.str[2:4].astype(float) + 100.0
    
    # 2次メッシュ部分 (5-6文字)
    # 2次は1次を8x8分割
    mask2 = s_code.str.len() >= 6
    if mask2.any():
        lat_delta = np.where(mask2, lat_delta / 8.0, lat_delta)
        lon_delta = np.where(mask2, lon_delta / 8.0, lon_delta)
        # s_code.str[4] が 緯度方向, [5] が 経度方向
        m2_lat = s_code.str[4:5].replace('', '0').astype(float)
        m2_lon = s_code.str[5:6].replace('', '0').astype(float)
        lat += np.where(mask2, m2_lat * lat_delta, 0)
        lon += np.where(mask2, m2_lon * lon_delta, 0)

    # 3次メッシュ部分 (7-8文字)
    # 3次は2次を10x10分割
    mask3 = s_code.str.len() >= 8
    if mask3.any():
        lat_delta = np.where(mask3, lat_delta / 10.0, lat_delta)
        lon_delta = np.where(mask3, lon_delta / 10.0, lon_delta)
        m3_lat = s_code.str[6:7].replace('', '0').astype(float)
        m3_lon = s_code.str[7:8].replace('', '0').astype(float)
        lat += np.where(mask3, m3_lat * lat_delta, 0)
        lon += np.where(mask3, m3_lon * lon_delta, 0)

    # 4次〜6次メッシュ部分 (9文字目以降)
    # 4次以降は1文字ずつ加算。各階層を2x2分割。
    max_len = s_code.str.len().max()
    for i in range(8, int(max_len)):
        mask_i = s_code.str.len() > i
        if not mask_i.any():
            continue
            
        lat_delta = np.where(mask_i, lat_delta / 2.0, lat_delta)
        lon_delta = np.where(mask_i, lon_delta / 2.0, lon_delta)
        
        # コード1-4のデコード
        # 1: (0,0), 2: (0,1), 3: (1,0), 4: (1,1) -> (lat_offset, lon_offset)
        code_i = s_code.str[i:i+1].replace('', '0').astype(int)
        
        # 緯度加算: 3 or 4 の場合に lat_delta を加算
        lat += np.where(mask_i & code_i.isin([3, 4]), lat_delta, 0)
        # 経度加算: 2 or 4 の場合に lon_delta を加算
        lon += np.where(mask_i & code_i.isin([2, 4]), lon_delta, 0)

    # モードに応じた緯度経度の調整
    if mode == "sw":
        return pd.DataFrame({"lat": lat, "lon": lon})
    elif mode == "center":
        return pd.DataFrame({
            "lat": lat + lat_delta / 2.0,
            "lon": lon + lon_delta / 2.0
        })
    elif mode == "bbox":
        return pd.DataFrame({
            "min_lat": lat,
            "min_lon": lon,
            "max_lat": lat + lat_delta,
            "max_lon": lon + lon_delta
        })
    else:
        raise ValueError(f"Invalid mode: {mode}")

if __name__ == "__main__":
    # データを読み込む
    df = pd.read_csv("data/processed/tblT001227E13.csv")
    # 1. メッシュコードから中心点の緯度経度を求める（図示用）
    coords = meshcode_to_latlon(df["KEY_CODE"], mode="center")
    df = pd.concat([df, coords], axis=1)
    # 2. 緯度経度から別の階層（例：5次メッシュ）のコードを生成する
    # 元が6次メッシュであっても、任意の階層のコードを取得できます
    df["mesh_level5"] = latlon_to_meshcode(df["lat"], df["lon"], level=5)
    print(df[["KEY_CODE", "lat", "lon", "mesh_level5"]].head())