# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.20.4",
# ]
# ///
import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")

with app.setup:
    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd
    import pyarrow as pa


@app.cell
def _():
    logo_url = "https://raw.githubusercontent.com/mohitshrestha/brand/refs/heads/main/logo/logo.png"

    mo.md(
        f"""
        # Interactive Data Visualization

        <img src="{logo_url}" width="200" />

        This notebook demonstrates a simple interactive visualization using Altair.
        Try selecting the points!
        """
    )
    return


@app.cell
def _():
    # Create sample data
    data = pd.DataFrame({"x": np.arange(100), "y": np.random.normal(0, 1, 100)})

    # Create interactive chart
    chart = mo.ui.altair_chart(
        (
            alt.Chart(data)
            .mark_circle()
            .encode(
                x="x", y="y", size=alt.value(100), color=alt.value("steelblue")
            )
            .properties(height=400, title="Interactive Scatter Plot")
        )
    )
    return (chart,)


@app.cell
def _(chart):
    # Just return the chart value to satisfy ruff
    chart
    return


if __name__ == "__main__":
    app.run()
