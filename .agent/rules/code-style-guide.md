---
trigger: always_on
---

# Python コーディングガイドライン (PEP 8 準拠)

このドキュメントは、Pythonコードの可読性と一貫性を保つのための基本的なコーディングルールをまとめたものです。

---

## 1. 基本原則
* **読みやすさは重要である:** コードは書かれる回数よりも読まれる回数の方が多い。
* **一貫性を保つ:** プロジェクト内、あるいはモジュール内でスタイルを統一する。

---

## 2. レイアウトと空白

### インデント
* **スペース4つ**を使用する（タブは使用しない）。

### 1行の長さ
* 最大 **79文字** とする。
* 構造上長くなる場合は、括弧内での改行やバックスラッシュを利用する。

### 空行
* トップレベルの関数やクラスの定義の間は **2行** 空ける。
* クラス内のメソッド定義の間は **1行** 空ける。

### インポート (Imports)
* インポートは常にファイルの冒頭、モジュールコメントや docstring の直後に記述する。
* 以下の順序でグループ化し、各グループの間には空行を入れる。
    1. 標準ライブラリ
    2. サードパーティライブラリ（`pandas`, `requests` など）
    3. ローカルなアプリケーション/ライブラリ特定のインポート

```python
# 良い例
import os
import sys

import numpy as np
import pandas as pd

from my_project import utils
```

---

## 3. 命名規則 (Naming Conventions)

| 対象 | 命名スタイル | 例 |
| :--- | :--- | :--- |
| **パッケージ / モジュール** | 短い小文字（アンダースコア可） | `my_package`, `utils.py` |
| **クラス** | 最初の文字を大文字にする (PascalCase) | `UserProfile`, `DataManager` |
| **関数 / メソッド** | 小文字＋アンダースコア (snake_case) | `calculate_total()`, `get_user_id()` |
| **変数** | 小文字＋アンダースコア (snake_case) | `user_name`, `items_count` |
| **定数** | 全て大文字＋アンダースコア | `MAX_RETRY`, `API_KEY` |
| **非公開変数/メソッド** | 先頭にアンダースコアを1つ付ける | `_internal_method()` |

---

## 4. プログラミングの作法

### 比較
* `None` との比較は常に `is` または `is not` を使用する（`==` は使わない）。
```python
if val is None:
    # 処理
```

### ブール値の評価
* `if items == True:` ではなく `if items:` と書く。
* 空のリスト `[]` や辞書 `{}` は偽として評価される性質を利用する。

### 文字列
* 文字列の結合には `+` ではなく、**f-string**（Python 3.6+）を推奨する。
```python
name = "Alice"
print(f"Hello, {name}!")
```

---

## 5. コメントと Docstring

### コメント
* コードと矛盾するコメントは、コメントがないよりも悪い。コードを修正したら必ずコメントも更新する。
* インラインコメントは控えめにし、コード自体を読みやすくする。

### Docstring (関数の説明)
* すべてのパブリックなモジュール、関数、クラス、メソッドには docstring を記述する。
```python
def fetch_data(url: str) -> dict:
    """
    指定されたURLからデータを取得する。

    Args:
        url (str): 取得先のURL

    Returns:
        dict: パースされたJSONデータ
    """
    pass
```

---

## 6. 推奨ツール
コード品質を自動で維持するために、以下のツールの導入を推奨します。

* **Linter:** `flake8` または `Ruff` (コードの不備をチェック)
* **Formatter:** `black` または `Ruff` (コードを自動整形)
* **Type Checker:** `mypy` (静的型チェック)


## Streamlit Coding Rules
- **HTML/CSS Rendering**: Do NOT use `st.markdown(..., unsafe_allow_html=True)`. This is a security risk.
- **Alternative**: Use `st.html(...)` for any raw HTML or CSS injection.