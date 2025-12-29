import os
import pandas as pd
from pathlib import Path


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


if __name__ == "__main__":
    # プロジェクトルートからの相対パス
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_PATH = BASE_DIR / "data" / "raw" / "tblT001227E13.txt"
    PROCESSED_PATH = BASE_DIR / "data" / "processed" / "tblT001227E13.csv"

    process_census_txt_to_csv(str(RAW_PATH), str(PROCESSED_PATH))
