import os
import json
import base64
import binascii
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import dash
from dash import dcc, html
import plotly.graph_objects as go
from plotly.subplots import make_subplots

load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT = os.environ["GCP_PROJECT"]


_CREDS_ENV_VARS = ("GOOGLE_CREDENTIALS_JSON", "GCP_SERVICE_ACCOUNT_KEY")


def _decode_creds(raw: str) -> dict:
    """
    Accept a service-account key as either base64-encoded JSON (how it's stored
    on Render) or raw JSON, and return the parsed dict.
    """
    raw = raw.strip()
    # Raw JSON is passed through as-is; anything else is treated as base64.
    if not raw.startswith("{"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                "Service-account key env var is neither valid JSON nor valid "
                "base64-encoded JSON"
            ) from exc
    return json.loads(raw)


def _make_client(project: str) -> bigquery.Client:
    """
    Build a BigQuery client.

    In production (Render) the service-account key is provided as a base64-encoded
    JSON string in an env var (GOOGLE_CREDENTIALS_JSON / GCP_SERVICE_ACCOUNT_KEY) —
    there is no key file on disk. Locally we fall back to Application Default
    Credentials (e.g. GOOGLE_APPLICATION_CREDENTIALS pointing at a key file).
    """
    raw = next((os.environ[v] for v in _CREDS_ENV_VARS if os.environ.get(v)), None)
    if raw:
        info = _decode_creds(raw)
        credentials = service_account.Credentials.from_service_account_info(info)
        return bigquery.Client(project=project, credentials=credentials)
    return bigquery.Client(project=project)


client = _make_client(PROJECT)


# ── data ─────────────────────────────────────────────────────────────────────

def bq(sql: str) -> pd.DataFrame:
    return client.query(sql).to_dataframe()


df_rate_type = bq(f"""
    SELECT
        issuance_quarter,
        SUM(fixed_rate_deals)    AS fixed_rate_deals,
        SUM(floating_rate_deals) AS floating_rate_deals,
        SUM(deal_count) - SUM(fixed_rate_deals) - SUM(floating_rate_deals) AS unclassified
    FROM `{PROJECT}.marts.mart_rate_correlation`
    GROUP BY 1
    ORDER BY 1
""")

df_instrument = bq(f"""
    SELECT
        issuance_quarter,
        instrument_type,
        SUM(deal_count) AS deal_count
    FROM `{PROJECT}.marts.mart_rate_correlation`
    WHERE instrument_type IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 1, 2
""")

df_rates = bq(f"""
    SELECT
        issuance_quarter,
        SUM(deal_count)                  AS total_deals,
        ROUND(AVG(avg_fed_funds_rate), 2) AS avg_fed_funds_rate
    FROM `{PROJECT}.marts.mart_rate_correlation`
    GROUP BY 1
    ORDER BY 1
""")

kpi = bq(f"""
    SELECT
        COUNT(*)                                                                  AS total_filings,
        SUM(IF(principal_amount_usd <= 50e9, principal_amount_usd, NULL))        AS total_volume_usd,
        MIN(file_date)                                                            AS earliest_date,
        MAX(file_date)                                                            AS latest_date
    FROM `{PROJECT}.marts.mart_debt_issuance`
    WHERE parse_success = true
""").iloc[0]

top_sector = bq(f"""
    SELECT gics_sector, SUM(deal_count) AS n
    FROM `{PROJECT}.marts.mart_rate_correlation`
    WHERE gics_sector != 'Other'
    GROUP BY 1 ORDER BY 2 DESC LIMIT 1
""").iloc[0]["gics_sector"]


# ── helpers ───────────────────────────────────────────────────────────────────

TEMPLATE = "plotly_white"
CHART_HEIGHT = 440

def qs(series: pd.Series) -> pd.Series:
    """Convert BQ DATE column to YYYY-Q# labels for x-axis."""
    dt = pd.to_datetime(series)
    return dt.dt.year.astype(str) + " Q" + dt.dt.quarter.astype(str)


# ── chart 1: issuance by rate type (fixed / floating / unclassified) ──────────

df_rate_type["quarter_label"] = qs(df_rate_type["issuance_quarter"])

fig1 = go.Figure()
for col, label, color in [
    ("fixed_rate_deals",    "Fixed Rate",    "#636EFA"),
    ("floating_rate_deals", "Floating Rate", "#EF553B"),
    ("unclassified",        "Unclassified",  "#D3D3D3"),
]:
    fig1.add_trace(go.Bar(
        x=df_rate_type["quarter_label"],
        y=df_rate_type[col],
        name=label,
        marker_color=color,
        hovertemplate="%{x}<br>%{y} filings<extra>" + label + "</extra>",
    ))

fig1.update_layout(
    barmode="stack",
    template=TEMPLATE,
    height=CHART_HEIGHT,
    title=dict(text="Debt Issuance by Rate Type — Quarterly", font=dict(size=15)),
    xaxis=dict(title="", tickangle=-35, tickfont=dict(size=11)),
    yaxis=dict(title="Filing Count"),
    legend=dict(title="Rate Type", font=dict(size=11)),
    margin=dict(t=50, b=10, l=60, r=20),
)


# ── chart 2: instrument type breakdown (stacked bar, top 8 types) ─────────────

top_types = (
    df_instrument.groupby("instrument_type")["deal_count"]
    .sum()
    .nlargest(8)
    .index.tolist()
)

df_inst = df_instrument.copy()
df_inst["instrument_type"] = df_inst["instrument_type"].where(
    df_inst["instrument_type"].isin(top_types), "other"
)
df_inst = (
    df_inst.groupby(["issuance_quarter", "instrument_type"], as_index=False)["deal_count"]
    .sum()
)
df_inst["quarter_label"] = qs(df_inst["issuance_quarter"])

ordered_types = top_types + (["other"] if "other" not in top_types else [])

fig2 = go.Figure()
for itype in ordered_types:
    d = df_inst[df_inst["instrument_type"] == itype]
    if d.empty:
        continue
    fig2.add_trace(go.Bar(
        x=d["quarter_label"],
        y=d["deal_count"],
        name=itype.replace("_", " ").title(),
        hovertemplate="%{x}<br>%{y} filings<extra>%{fullData.name}</extra>",
    ))

fig2.update_layout(
    barmode="stack",
    template=TEMPLATE,
    height=CHART_HEIGHT,
    title=dict(text="Instrument Type Breakdown — Quarterly", font=dict(size=15)),
    xaxis=dict(title="", tickangle=-35, tickfont=dict(size=11)),
    yaxis=dict(title="Filing Count"),
    legend=dict(title="Instrument Type", font=dict(size=11)),
    margin=dict(t=50, b=10, l=60, r=20),
)


# ── chart 3: issuance volume vs. fed funds rate (dual-axis) ──────────────────

df_rates["quarter_label"] = qs(df_rates["issuance_quarter"])

fig3 = make_subplots(specs=[[{"secondary_y": True}]])

fig3.add_trace(
    go.Bar(
        x=df_rates["quarter_label"],
        y=df_rates["total_deals"],
        name="Deal Count",
        marker_color="#636EFA",
        opacity=0.75,
        hovertemplate="%{x}<br>%{y} filings<extra>Deal Count</extra>",
    ),
    secondary_y=False,
)

fig3.add_trace(
    go.Scatter(
        x=df_rates["quarter_label"],
        y=df_rates["avg_fed_funds_rate"],
        name="Fed Funds Rate",
        mode="lines+markers",
        line=dict(color="#EF553B", width=2.5),
        marker=dict(size=7),
        hovertemplate="%{x}<br>%{y:.2f}%<extra>Fed Funds Rate</extra>",
    ),
    secondary_y=True,
)

fig3.update_layout(
    template=TEMPLATE,
    height=CHART_HEIGHT,
    title=dict(text="Issuance Volume vs. Fed Funds Rate", font=dict(size=15)),
    xaxis=dict(title="", tickangle=-35, tickfont=dict(size=11)),
    legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
    margin=dict(t=50, b=60, l=60, r=60),
)
fig3.update_yaxes(title_text="Filing Count", secondary_y=False)
fig3.update_yaxes(title_text="Fed Funds Rate (%)", secondary_y=True, showgrid=False)


# ── chart 4: sector heatmap (quarters × GICS sector, color = deal count) ──────

df_sector_heat = bq(f"""
    SELECT
        issuance_quarter,
        gics_sector,
        SUM(deal_count) AS deal_count
    FROM `{PROJECT}.marts.mart_rate_correlation`
    WHERE gics_sector != 'Other'
    GROUP BY 1, 2
    ORDER BY 1, 2
""")

# Pivot to matrix: rows = sectors, cols = quarters
if not df_sector_heat.empty:
    df_sector_heat["quarter_label"] = qs(df_sector_heat["issuance_quarter"])
    pivot = df_sector_heat.pivot_table(
        index="gics_sector", columns="quarter_label", values="deal_count", fill_value=0
    )
    # Order columns chronologically (they're already YYYY Q# strings, sort works)
    pivot = pivot[sorted(pivot.columns)]
    # Sort rows by total activity descending
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=True).index]

    z_raw  = pivot.values.astype(float)
    z_log  = np.log1p(z_raw)   # log(1+n) so zeros stay at 0

    # Build custom hover that shows the real count, not the log value
    hover = [[f"<b>{row}</b><br>{col}<br>{int(z_raw[i,j]):,} filings"
              for j, col in enumerate(pivot.columns)]
             for i, row in enumerate(pivot.index)]

    fig4 = go.Figure(go.Heatmap(
        z=z_log,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        text=hover,
        hovertemplate="%{text}<extra></extra>",
        colorscale="Blues",
        hoverongaps=False,
        colorbar=dict(
            title="Filings<br>(log scale)",
            thickness=14,
            len=0.8,
            tickvals=[np.log1p(v) for v in [1, 10, 50, 200, 500, 1000, 2000]],
            ticktext=["1", "10", "50", "200", "500", "1k", "2k"],
        ),
    ))
    fig4.update_layout(
        template=TEMPLATE,
        height=420,
        title=dict(text="Issuance Activity by Sector — Quarterly Heatmap", font=dict(size=15)),
        xaxis=dict(title="", tickangle=-35, tickfont=dict(size=11), side="bottom"),
        yaxis=dict(title="", tickfont=dict(size=11), autorange="reversed"),
        margin=dict(t=50, b=60, l=160, r=20),
    )
else:
    # Sector data not yet loaded — show placeholder
    fig4 = go.Figure()
    fig4.update_layout(
        template=TEMPLATE,
        height=420,
        title=dict(text="Sector Heatmap — run scripts/load_cik_sectors.py first", font=dict(size=14)),
        annotations=[dict(text="No sector data available yet", showarrow=False,
                          font=dict(size=16, color="#aaa"), xref="paper", yref="paper",
                          x=0.5, y=0.5)],
    )


# ── KPI card builder ──────────────────────────────────────────────────────────

def _fmt_volume(usd: float) -> str:
    if usd >= 1e12:
        return f"${usd/1e12:.1f}T"
    if usd >= 1e9:
        return f"${usd/1e9:.1f}B"
    return f"${usd/1e6:.0f}M"

def kpi_card(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.P(label, style={"margin": "0 0 6px", "fontSize": "11px",
                                 "fontWeight": "600", "color": "#888",
                                 "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.P(value, style={"margin": "0", "fontSize": "26px",
                                 "fontWeight": "700", "color": "#1a1a2e", "lineHeight": "1"}),
        ],
        style={
            "background": "#fff",
            "border": "1px solid #e8e8e8",
            "borderRadius": "10px",
            "padding": "20px 24px",
            "flex": "1",
            "minWidth": "160px",
        },
    )

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
           "Jul","Aug","Sep","Oct","Nov","Dec"]

def _fmt_date(d) -> str:
    s = str(d)   # "YYYY-MM-DD" or datetime
    year, month = int(s[:4]), int(s[5:7])
    return f"{_MONTHS[month-1]} {year}"

total_filings   = f"{int(kpi['total_filings']):,}"
total_volume    = _fmt_volume(float(kpi['total_volume_usd'] or 0))
date_range      = f"{_fmt_date(kpi['earliest_date'])} → {_fmt_date(kpi['latest_date'])}"


# ── layout ────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, title="Corporate Debt Issuance Trends")
server = app.server  # for Render / gunicorn

app.layout = html.Div(
    [
        # Header
        html.Div(
            [
                html.H1(
                    "Corporate Debt Issuance Trends",
                    style={"margin": "0", "fontWeight": "600", "fontSize": "22px"},
                ),
                html.P(
                    "SEC EDGAR 8-K Item 2.03 filings · 2022–2026 Q2 · FRED interest rates",
                    style={"margin": "4px 0 0", "color": "#888", "fontSize": "13px"},
                ),
            ],
            style={
                "padding": "24px 36px 20px",
                "borderBottom": "1px solid #e8e8e8",
                "background": "#fff",
            },
        ),
        # KPI cards
        html.Div(
            [
                kpi_card("Parsed Filings",       total_filings),
                kpi_card("Parsed Volume",        total_volume),
                kpi_card("Most Active Sector",   top_sector),
                kpi_card("Date Range",           date_range),
            ],
            style={
                "display": "flex",
                "gap": "16px",
                "padding": "20px 36px 4px",
                "flexWrap": "wrap",
            },
        ),
        # Charts
        html.Div(
            [
                dcc.Graph(figure=fig1, config={"displayModeBar": False}),
                dcc.Graph(figure=fig4, config={"displayModeBar": False}),
                dcc.Graph(figure=fig2, config={"displayModeBar": False}),
                dcc.Graph(figure=fig3, config={"displayModeBar": False}),
            ],
            style={"padding": "20px 24px", "display": "flex", "flexDirection": "column", "gap": "12px"},
        ),
    ],
    style={
        "fontFamily": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "maxWidth": "1280px",
        "margin": "0 auto",
        "background": "#fafafa",
        "minHeight": "100vh",
    },
)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
