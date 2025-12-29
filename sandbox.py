import marimo

__generated_with = "0.18.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    return (pd,)


@app.cell
def _(pd):
    df = pd.read_csv("./data/tblT001227E13.txt", encoding="shift-jis")
    df
    return (df,)


@app.cell
def _(df):
    df.columns
    return


@app.cell
def _(pd):
    df2 = pd.read_csv("./data/processed/tblT001227E13.csv")
    df2
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
