# 地域メッシュ計算ロジック詳解：緯度経度⇔コード相互変換をPythonで実装してみた

## 1. はじめに
地理的情報の分析において重要な「地域メッシュコード」について、その定義、計算ロジック、およびPythonによる実装方法を解説した記事です。

## 2. 地域メッシュの概要
地域メッシュとは、日本全国を緯度・経度に基づいて格子状に分割したものです。総務省統計局が定める統一基準に基づいています。

### メリット
- 位置情報を定量的・効率的に管理できる。
- 行政区分（市町村合併など）の変化に影響されない恒久的な規格。
- 異なるデータ間や時系列での比較が容易。

### 階層構造
| 名称 | 大きさの目安 | 間隔（緯度 / 経度） | 分割方法 |
| :--- | :--- | :--- | :--- |
| 第1次地域区画（1次メッシュ） | 約80km四方 | 40′ / 1° | - |
| 第2次地域区画（2次メッシュ） | 約10km四方 | 5′ / 7′30″ | 1次を8×8分割 |
| 第3次地域区画（3次メッシュ） | 約1km四方 | 30″ / 45″ | 2次を10×10分割 |
| 2分の1地域メッシュ（4次） | 約500m四方 | 15″ / 22.5″ | 3次を2×2分割 |
| 4分の1地域メッシュ（5次） | 約250m四方 | 7.5″ / 11.25″ | 4次を2×2分割 |
| 8分の1地域メッシュ（6次） | 約125m四方 | 3.75″ / 5.625″ | 5次を2×2分割 |

---

## 3. 計算の全体像
- **緯度経度 → メッシュコード**: 各区画の何番目のマスにあるかを計算し、整数部をコードとし、余り（小数点以下）を次の階層の計算に回す。
- **メッシュコード → 緯度経度**: 基準点（南西端）からの「ズレ」を各階層の幅に掛けて加算していく。

### 具体的なステップ
1. **1次メッシュ**: 緯度を1.5倍、経度から100を引いた整数部。
2. **2次メッシュ**: 1次の余りを8倍した整数部。
3. **3次メッシュ**: 2次の余りを10倍した整数部。
4. **4次以降**: 前の余りを2倍し、その組み合わせ（0 or 1）で1〜4のコードを割り振る。

---

## 4. Pythonによる実装例

### 緯度経度からメッシュコードを求める
```python
def latlon_to_meshcode(lat, lon, level):
    # --- 1次メッシュ ---
    t_lat = lat * 1.5
    t_lon = lon - 100.0
    m1_lat, m1_lon = int(t_lat), int(t_lon)
    mesh_code = [f"{m1_lat}{m1_lon:02}"]
    if level == 1: return "".join(mesh_code)

    # --- 2次メッシュ ---
    t_lat = (t_lat - m1_lat) * 8
    t_lon = (t_lon - m1_lon) * 8
    m2_lat, m2_lon = int(t_lat), int(t_lon)
    mesh_code.append(f"{m2_lat}{m2_lon}")
    if level == 2: return "".join(mesh_code)

    # --- 3次メッシュ ---
    t_lat = (t_lat - m2_lat) * 10
    t_lon = (t_lon - m2_lon) * 10
    m3_lat, m3_lon = int(t_lat), int(t_lon)
    mesh_code.append(f"{m3_lat}{m3_lon}")
    if level == 3: return "".join(mesh_code)

    # --- 4次〜6次メッシュ ---
    curr_lat_int, curr_lon_int = m3_lat, m3_lon
    for _ in range(4, level + 1):
        t_lat = (t_lat - curr_lat_int) * 2
        t_lon = (t_lon - curr_lon_int) * 2
        curr_lat_int, curr_lon_int = int(t_lat), int(t_lon)
        code = curr_lat_int * 2 + curr_lon_int + 1
        mesh_code.append(str(code))
    return "".join(mesh_code)
```

### メッシュコードから緯度経度を求める
```python
def meshcode_to_latlon(mesh_code):
    length = len(mesh_code)
    lat_delta, lon_delta = 2.0 / 3.0, 1.0
    lat = int(mesh_code[0:2]) * lat_delta
    lon = int(mesh_code[2:4]) + 100.0

    # 2次、3次、4次以降と順次加算
    if length >= 6:
        lat_delta /= 8.0; lon_delta /= 8.0
        lat += int(mesh_code[4]) * lat_delta
        lon += int(mesh_code[5]) * lon_delta
    if length >= 8:
        lat_delta /= 10.0; lon_delta /= 10.0
        lat += int(mesh_code[6]) * lat_delta
        lon += int(mesh_code[7]) * lon_delta
    if length > 8:
        for i in range(8, length):
            lat_delta /= 2.0; lon_delta /= 2.0
            mc_i = int(mesh_code[i])
            if mc_i in [3, 4]: lat += lat_delta
            if mc_i in [2, 4]: lon += lon_delta
            
    return {'lat': lat, 'lon': lon} # 南西端（基準点）
```

## 5. まとめ
- 4次メッシュ以降はコード体系が1〜4の割り当てに変わる点に注意。
- 浮動小数点の精度が重要な場合は `Decimal` モジュールの使用が推奨される。

---
**参照元:** [ドコモ開発者ブログ (2025/12/18)](https://nttdocomo-developers.jp/entry/2025/12/18/090000_6)