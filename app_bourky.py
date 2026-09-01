import datetime
import io
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# Nastavení stránky na široký režim
st.set_page_config(
    page_title="Klimatologie Bouřek Most", page_icon="⚡", layout="wide"
)


# ==========================================
# 1. NAČTENÍ A CHYTRÁ FILTRACE DAT
# ==========================================
@st.cache_data(ttl=3600)  # Automatické promazání cache každou hodinu
def nacti_data():
  file_path = "thunder2crossplatforms.xlsx"
  df_raw = pd.read_excel(file_path, header=None)

  header_indices = df_raw[df_raw[0] == "Date"].index.tolist()

  if len(header_indices) < 2:
    h1_idx, h2_idx = 3, 374
  else:
    h1_idx, h2_idx = header_indices[0], header_indices[1]

  def parsuj_sekci(start_hdr):
    cols = [
        str(c).split(".")[0] if isinstance(c, (int, float)) else str(c)
        for c in df_raw.iloc[start_hdr].values
    ]
    df_sub = df_raw.iloc[start_hdr + 1 : start_hdr + 367].copy()
    df_sub.columns = cols
    df_sub.set_index("Date", inplace=True)

    kandidati = [c for c in df_sub.columns if c.isdigit() and int(c) >= 1999]
    df_roky_temp = df_sub[kandidati].apply(pd.to_numeric, errors="coerce")

    posledni_aktivni = 1999
    for col in kandidati:
      if df_roky_temp[col].max() > 0:
        posledni_aktivni = max(posledni_aktivni, int(col))

    roky_cols = [str(r) for r in range(1999, posledni_aktivni + 1)]
    df_roky_res = df_roky_temp[roky_cols].copy()

    for col in df_roky_res.columns:
      last_valid = df_roky_res[col].last_valid_index()
      if last_valid is not None:
        s = df_roky_res[col].ffill().fillna(0)
        if int(col) == posledni_aktivni:
          idx_num = df_roky_res.index.get_loc(last_valid)
          s.iloc[idx_num + 1 :] = np.nan
        df_roky_res[col] = s
      else:
        df_roky_res[col] = 0

    return df_roky_res, roky_cols, posledni_aktivni

  df_roky, roky_sloupce, posledni_aktivni_rok = parsuj_sekci(h1_idx)
  df_roky_direct, _, _ = parsuj_sekci(h2_idx)

  return df_roky, df_roky_direct, roky_sloupce, posledni_aktivni_rok


try:
  df_roky, df_roky_direct, roky_sloupce, posledni_aktivni_rok = nacti_data()
except Exception as e:
  st.error(f"Nepodařilo se načíst Excel. Chyba: {e}")
  st.stop()

x_str = roky_sloupce
N = len(x_str)

posledni_uzavreny_rok = posledni_aktivni_rok - 1
roky_uzavrene = [
    rok for rok in roky_sloupce if int(rok) <= posledni_uzavreny_rok
]
df_uzavrene = df_roky[roky_uzavrene]
df_uzavrene_direct = df_roky_direct[roky_uzavrene]

# ==========================================
# 2. BOČNÍ PANEL (Ovládání)
# ==========================================
st.sidebar.header("⚙️ Nastavení grafu")
vybrany_rok = st.sidebar.selectbox(
    "Vyberte rok pro detailní srovnání:", options=roky_sloupce, index=N - 1
)

# ==========================================
# 3. HLAVNÍ NÁSTĚNKA (Dashboard)
# ==========================================
st.title("⚡ Bouřkový Dashboard: Most")
st.markdown("Interaktivní klimatologická analýza na základě lidského pozorování.")

col1, col2, col3 = st.columns(3)
with col1:
  st.metric("Nejvíce bouřek (2014)", "40 dní")
with col2:
  min_rok = df_uzavrene.iloc[-1].idxmin()
  min_hodnota = df_uzavrene.iloc[-1].min()
  st.metric(f"Nejméně bouřek ({min_rok})", f"{int(min_hodnota)} dní")
with col3:
  st.metric(
      f"Bouřky v roce {vybrany_rok}",
      f"{int(np.nanmax(df_roky[vybrany_rok].values))} dní",
  )

st.divider()

# ==========================================
# 4. KRESLENÍ (Graf 1A & 1B: Kumulativní normály)
# ==========================================
st.subheader("📈 Kumulativní normál a průběh sezóny (Celkové bouřky)")

df_stats = pd.DataFrame(index=df_uzavrene.index)
df_stats["min_q0"] = df_uzavrene.min(axis=1)
df_stats["max_q4"] = df_uzavrene.max(axis=1)
df_stats["mean"] = df_uzavrene.mean(axis=1)
df_stats["p10"] = df_uzavrene.quantile(0.10, axis=1)
df_stats["p25"] = df_uzavrene.quantile(0.25, axis=1)
df_stats["p75"] = df_uzavrene.quantile(0.75, axis=1)
df_stats["p90"] = df_uzavrene.quantile(0.90, axis=1)

dummy_dates = pd.date_range(start="2024-01-01", periods=len(df_stats))

fig1, ax1 = plt.subplots(figsize=(14, 6))
ax1.fill_between(
    dummy_dates,
    df_stats["p10"],
    df_stats["p90"],
    step="post",
    alpha=0.3,
    color="gray",
    label="80 % let ($P_{10} - P_{90}$)",
)
ax1.fill_between(
    dummy_dates,
    df_stats["p25"],
    df_stats["p75"],
    step="post",
    alpha=0.5,
    color="darkgray",
    label="50 % let ($Q_1 - Q_3$)",
)
ax1.step(
    dummy_dates,
    df_stats["max_q4"],
    where="post",
    color="black",
    linewidth=1.5,
    label="Extrémy (Min/Max)",
)
ax1.step(
    dummy_dates,
    df_stats["min_q0"],
    where="post",
    color="black",
    linewidth=1.5,
)
ax1.step(
    dummy_dates,
    df_stats["mean"],
    where="post",
    color="#d62828",
    linewidth=2.5,
    label="Dlouhodobý Průměr",
)

ax1.step(
    dummy_dates,
    df_roky[vybrany_rok],
    where="post",
    color="#003049",
    linewidth=3.5,
    label=f"Rok {vybrany_rok}",
)

ax1.grid(True, alpha=0.4, linestyle="--")
ax1.set_xticks([pd.to_datetime(f"2024-{m:02d}-01") for m in range(1, 13)])
ax1.set_xticklabels([
    "Led",
    "Úno",
    "Bře",
    "Dub",
    "Kvě",
    "Čvn",
    "Čvc",
    "Srp",
    "Zář",
    "Říj",
    "Lis",
    "Pro",
])
ax1.set_xlim(dummy_dates[0], dummy_dates[-1])
ax1.set_ylim(bottom=0)
ax1.legend(loc="upper left")
st.pyplot(fig1)
plt.close(fig1)

st.subheader(
    "📈 Kumulativní normál a průběh sezóny (Přímé a blízké bouřky - Direct /"
    " Near)"
)

df_stats_direct = pd.DataFrame(index=df_uzavrene_direct.index)
df_stats_direct["min_q0"] = df_uzavrene_direct.min(axis=1)
df_stats_direct["max_q4"] = df_uzavrene_direct.max(axis=1)
df_stats_direct["mean"] = df_uzavrene_direct.mean(axis=1)
df_stats_direct["p10"] = df_uzavrene_direct.quantile(0.10, axis=1)
df_stats_direct["p25"] = df_uzavrene_direct.quantile(0.25, axis=1)
df_stats_direct["p75"] = df_uzavrene_direct.quantile(0.75, axis=1)
df_stats_direct["p90"] = df_uzavrene_direct.quantile(0.90, axis=1)

dummy_dates_direct = pd.date_range(
    start="2024-01-01", periods=len(df_stats_direct)
)

fig1b, ax1b = plt.subplots(figsize=(14, 6))
ax1b.fill_between(
    dummy_dates_direct,
    df_stats_direct["p10"],
    df_stats_direct["p90"],
    step="post",
    alpha=0.3,
    color="gray",
    label="80 % let ($P_{10} - P_{90}$)",
)
ax1b.fill_between(
    dummy_dates_direct,
    df_stats_direct["p25"],
    df_stats_direct["p75"],
    step="post",
    alpha=0.5,
    color="darkgray",
    label="50 % let ($Q_1 - Q_3$)",
)
ax1b.step(
    dummy_dates_direct,
    df_stats_direct["max_q4"],
    where="post",
    color="black",
    linewidth=1.5,
    label="Extrémy (Min/Max)",
)
ax1b.step(
    dummy_dates_direct,
    df_stats_direct["min_q0"],
    where="post",
    color="black",
    linewidth=1.5,
)
ax1b.step(
    dummy_dates_direct,
    df_stats_direct["mean"],
    where="post",
    color="#d62828",
    linewidth=2.5,
    label="Dlouhodobý Průměr",
)

ax1b.step(
    dummy_dates_direct,
    df_roky_direct[vybrany_rok],
    where="post",
    color="#003049",
    linewidth=3.5,
    label=f"Rok {vybrany_rok}",
)

ax1b.grid(True, alpha=0.4, linestyle="--")
ax1b.set_xticks([pd.to_datetime(f"2024-{m:02d}-01") for m in range(1, 13)])
ax1b.set_xticklabels([
    "Led",
    "Úno",
    "Bře",
    "Dub",
    "Kvě",
    "Čvn",
    "Čvc",
    "Srp",
    "Zář",
    "Říj",
    "Lis",
    "Pro",
])
ax1b.set_xlim(dummy_dates_direct[0], dummy_dates_direct[-1])
ax1b.set_ylim(bottom=0)
ax1b.legend(loc="upper left")
st.pyplot(fig1b)
plt.close(fig1b)

st.divider()

# ==========================================
# 5. KRESLENÍ (Graf 2: Dlouhodobý trend)
# ==========================================
st.subheader("📉 Dlouhodobý vývoj a trend")

td_amount = []
for r in roky_sloupce:
  vals = df_roky[r].values
  td_amount.append(np.nanmax(vals) if not np.all(np.isnan(vals)) else 0)
td_amount = np.array(td_amount)

roky_cisla_uzavrene = np.array([int(r) for r in roky_uzavrene])
td_amount_uzavrene = np.array([
    td_amount[i] for i, r in enumerate(roky_sloupce) if r in roky_uzavrene
])

koeficienty = np.polyfit(roky_cisla_uzavrene, td_amount_uzavrene, 1)
trendova_rovnice = np.poly1d(koeficienty)
trend_cara = trendova_rovnice(np.arange(1999, posledni_aktivni_rok + 1))

fig2, ax2 = plt.subplots(figsize=(14, 5))
ax2.plot(
    x_str, trend_cara, color="#7fbfff", linewidth=2, label="Dlouhodobý trend"
)
ax2.plot(
    x_str,
    td_amount,
    color="#004488",
    marker="s",
    markersize=8,
    linewidth=3,
    label="Bouřkové dny (Celkem)",
)

for i, txt in enumerate(td_amount):
  ax2.annotate(
      int(txt),
      (x_str[i], td_amount[i]),
      textcoords="offset points",
      xytext=(0, 10),
      ha="center",
      fontsize=10,
      fontweight="bold",
  )

ax2.set_ylim(0, max(td_amount) + 10)
ax2.set_xticks(range(len(x_str)))
ax2.set_xticklabels(x_str, rotation=45, ha="right")
ax2.grid(True, alpha=0.4, linestyle="--")
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)
ax2.legend(loc="lower left")
st.pyplot(fig2)
plt.close(fig2)

st.divider()

# ==========================================
# 6. KRESLENÍ (Graf 3: Typy událostí)
# ==========================================
st.subheader("📊 Typy bouřkových událostí")

data_events = {
    "MCS": [
        1,
        0,
        2,
        2,
        2,
        3,
        1,
        2,
        3,
        1,
        2,
        0,
        4,
        2,
        1,
        0,
        1,
        0,
        3,
        2,
        1,
        0,
        2,
        2,
        1,
        0,
        0,
    ],
    "STR TS or SC": [
        1,
        1,
        1,
        3,
        5,
        0,
        1,
        2,
        3,
        0,
        3,
        2,
        2,
        2,
        1,
        1,
        2,
        1,
        4,
        3,
        1,
        1,
        0,
        2,
        2,
        9,
        3,
    ],
    "WF induced": [
        0,
        0,
        0,
        0,
        0,
        0,
        2,
        0,
        0,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
        0,
        0,
        3,
        3,
        2,
        4,
        2,
        0,
        0,
    ],
    "Far storms": [
        8,
        15,
        8,
        9,
        11,
        15,
        8,
        9,
        11,
        8,
        11,
        8,
        8,
        7,
        8,
        11,
        9,
        14,
        11,
        12,
        10,
        10,
        9,
        10,
        13,
        14,
        7,
    ],
}

for k in data_events.keys():
  while len(data_events[k]) < N:
    data_events[k].append(0)
  data_events[k] = data_events[k][:N]

fig3, ax3 = plt.subplots(figsize=(14, 6))
sirka_sloupce = 0.2
x_pos = np.arange(N)

ax3.bar(
    x_pos - 1.5 * sirka_sloupce,
    data_events["MCS"],
    sirka_sloupce,
    label="MCS",
    color="#FF0000",
)
ax3.bar(
    x_pos - 0.5 * sirka_sloupce,
    data_events["STR TS or SC"],
    sirka_sloupce,
    label="STR TS or SC",
    color="#FF8C00",
)
ax3.bar(
    x_pos + 0.5 * sirka_sloupce,
    data_events["WF induced"],
    sirka_sloupce,
    label="WF induced",
    color="#0070C0",
)
ax3.bar(
    x_pos + 1.5 * sirka_sloupce,
    data_events["Far storms"],
    sirka_sloupce,
    label="Far storms",
    color="#FFFF00",
)

ax3.set_xticks(x_pos)
ax3.set_xticklabels(x_str, rotation=45, ha="right")
ax3.set_ylabel("Počet událostí")
ax3.legend(loc="upper left", bbox_to_anchor=(1, 1), frameon=False)
ax3.grid(True, axis="y", alpha=0.3, linestyle="--")
ax3.spines["top"].set_visible(False)
ax3.spines["right"].set_visible(False)
st.pyplot(fig3)
plt.close(fig3)

st.divider()

# ==========================================
# 7. KRESLENÍ (Graf 4: Klasifikace sezón)
# ==========================================
st.subheader("📈 Index extremity sezón (Odchylka od průměru)")

td_prumer = 28
body_sezony = []

for td in td_amount:
  rozdil = td - td_prumer
  if rozdil <= -7:
    body = -3
  elif rozdil <= -5:
    body = -2
  elif rozdil <= -3:
    body = -1
  elif rozdil >= 7:
    body = 3
  elif rozdil >= 5:
    body = 2
  elif rozdil >= 3:
    body = 1
  else:
    body = 0
  body_sezony.append(body)

fig4, ax4 = plt.subplots(figsize=(14, 5))
ax4.axhline(0, color="black", linewidth=1.5, alpha=0.5)
ax4.plot(
    x_str,
    body_sezony,
    color="#FF3300",
    marker="D",
    linewidth=2.5,
    markersize=8,
    label="Points",
)
ax4.set_ylim(-4, 4)
ax4.set_yticks(np.arange(-4, 5, 1))
ax4.set_ylabel("Bodová klasifikace")
ax4.set_xticks(range(len(x_str)))
ax4.set_xticklabels(x_str, rotation=45, ha="right")
ax4.grid(True, axis="both", alpha=0.3, linestyle="--")
ax4.spines["top"].set_visible(False)
ax4.spines["right"].set_visible(False)
ax4.legend(loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
st.pyplot(fig4)
plt.close(fig4)

st.divider()

# ==========================================
# 8. KRESLENÍ (Graf 5: Interaktivní měsíční vývoj)
# ==========================================
st.subheader("📅 Měsíční vývoj a trendy")

mesicni_data = {
    "Leden": [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        2,
        0,
        0,
        0,
        0,
        1,
        2,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    ],
    "Únor": [
        0,
        0,
        0,
        2,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
        0,
        1,
        1,
        0,
        0,
        0,
    ],
    "Březen": [
        0,
        2,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        1,
        3,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
    ],
    "Duben": [
        1,
        2,
        1,
        1,
        1,
        3,
        2,
        4,
        1,
        2,
        1,
        0,
        2,
        1,
        2,
        6,
        3,
        1,
        0,
        2,
        1,
        0,
        0,
        1,
        1,
        1,
        0,
        1,
    ],
    "Květen": [
        6,
        6,
        4,
        5,
        7,
        8,
        6,
        4,
        6,
        7,
        7,
        3,
        7,
        6,
        6,
        7,
        2,
        5,
        5,
        6,
        1,
        0,
        5,
        4,
        1,
        7,
        4,
    ],
    "Červen": [
        4,
        7,
        5,
        4,
        7,
        5,
        5,
        6,
        7,
        8,
        7,
        3,
        8,
        6,
        4,
        3,
        7,
        13,
        8,
        3,
        5,
        8,
        8,
        5,
        10,
        6,
        3,
    ],
    "Červenec": [
        5,
        6,
        4,
        7,
        10,
        9,
        9,
        11,
        7,
        3,
        8,
        7,
        7,
        10,
        3,
        13,
        9,
        11,
        10,
        4,
        6,
        4,
        7,
        4,
        6,
        6,
        7,
    ],
    "Srpen": [
        1,
        4,
        8,
        6,
        4,
        8,
        4,
        4,
        9,
        4,
        5,
        4,
        5,
        6,
        4,
        5,
        4,
        2,
        7,
        9,
        9,
        6,
        6,
        5,
        5,
        9,
        2,
    ],
    "Září": [
        3,
        0,
        0,
        5,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        3,
        2,
        1,
        5,
        2,
        1,
        1,
        3,
        1,
        2,
        2,
        5,
        2,
        1,
        3,
    ],
    "Říjen": [
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        2,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
    ],
    "Listopad": [
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    ],
    "Prosinec": [
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
        0,
        0,
    ],
}

for k in mesicni_data.keys():
  while len(mesicni_data[k]) < N:
    mesicni_data[k].append(0)
  mesicni_data[k] = mesicni_data[k][:N]

vybrany_mesic = st.selectbox(
    "Vyberte měsíc:", options=list(mesicni_data.keys()), index=6
)
data_pro_graf = np.array(mesicni_data[vybrany_mesic])

koeficienty_m = np.polyfit(
    roky_cisla_uzavrene, data_pro_graf[: len(roky_cisla_uzavrene)], 1
)
trendova_rovnice_m = np.poly1d(koeficienty_m)
trend_cara_m = trendova_rovnice_m(np.arange(1999, posledni_aktivni_rok + 1))

fig5, ax5 = plt.subplots(figsize=(14, 5))
ax5.plot(
    x_str,
    trend_cara_m,
    color="#7fbfff",
    linewidth=2,
    label=f"Lineární ({vybrany_mesic})",
)
ax5.plot(
    x_str,
    data_pro_graf,
    color="#004488",
    marker="s",
    markersize=6,
    linewidth=2,
    label=vybrany_mesic,
)

ax5.yaxis.set_major_locator(MaxNLocator(integer=True))
ax5.set_ylim(bottom=0)
ax5.set_xticks(range(len(x_str)))
ax5.set_xticklabels(x_str, rotation=45, ha="right")
ax5.grid(True, axis="both", alpha=0.3, linestyle="--")
ax5.spines["top"].set_visible(False)
ax5.spines["right"].set_visible(False)
ax5.legend(loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
st.pyplot(fig5)
plt.close(fig5)

st.divider()

# ==========================================
# 9. KRESLENÍ (Graf 6: Průměrný průběh)
# ==========================================
st.subheader("🔔 Průměrné rozložení bouřek během roku")

mesice = [
    "Leden",
    "Únor",
    "Březen",
    "Duben",
    "Květen",
    "Červen",
    "Červenec",
    "Srpen",
    "Září",
    "Říjen",
    "Listopad",
    "Prosinec",
]
prumery = [
    0.25,
    0.25,
    0.36,
    1.48,
    5.00,
    6.11,
    7.15,
    5.37,
    1.63,
    0.22,
    0.04,
    0.19,
]

fig6, ax6 = plt.subplots(figsize=(14, 5))
ax6.plot(
    mesice,
    prumery,
    color="#004488",
    marker="s",
    markersize=8,
    linewidth=2.5,
    label="Průměrný počet",
)
ax6.set_ylim(bottom=0)
ax6.set_ylabel("Průměrný počet dní")
ax6.grid(True, axis="both", alpha=0.3, linestyle="--")
ax6.spines["top"].set_visible(False)
ax6.spines["right"].set_visible(False)
st.pyplot(fig6)
plt.close(fig6)

st.divider()

# ==========================================
# 10. KRESLENÍ (Graf 7: Délka bouřkové sezóny)
# ==========================================
st.subheader("📏 Trvání bouřkové sezóny (Dumbbell Plot)")

first_storms = []
last_storms = []
valid_years = []

for rok in roky_sloupce:
  s = df_roky[rok].values
  if np.any(~np.isnan(s)) and np.nanmax(s) > 0:
    first_idx = np.where(s > 0)[0][0]

    increments = np.diff(s, prepend=0)
    valid_incs = np.where(increments > 0)[0]
    last_idx = valid_incs[-1] if len(valid_incs) > 0 else first_idx

    first_storms.append(first_idx)
    last_storms.append(last_idx)
    valid_years.append(str(rok))

anglicke_mesice = [
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def bezpecne_datum(idx):
  try:
    idx_int = int(idx)
    if 0 <= idx_int <= 366:
      d = pd.to_datetime("2024-01-01") + pd.to_timedelta(idx_int, unit="D")
      return f"{d.day:02d} {anglicke_mesice[d.month]}"
  except:
    pass
  return ""


durations = [last - first for first, last in zip(first_storms, last_storms)]
min_idx = np.argmin(durations)
max_idx = np.argmax(durations)

colA, colB = st.columns(2)
with colA:
  st.metric(
      label=f"⏳ Nejkratší sezóna (Rok {valid_years[min_idx]})",
      value=f"{durations[min_idx]} dní",
  )
with colB:
  st.metric(
      label=f"🗓️ Nejdelší sezóna (Rok {valid_years[max_idx]})",
      value=f"{durations[max_idx]} dní",
  )

fig7, ax7 = plt.subplots(figsize=(14, 7))
ax7.axhspan(
    np.percentile(first_storms, 25),
    np.percentile(first_storms, 75),
    color="#4A86E8",
    alpha=0.15,
)
ax7.axhline(np.mean(first_storms), color="#4A86E8", linestyle="--", alpha=0.5)
ax7.axhspan(
    np.percentile(last_storms, 25),
    np.percentile(last_storms, 75),
    color="#FF5722",
    alpha=0.15,
)
ax7.axhline(np.mean(last_storms), color="#FF5722", linestyle="--", alpha=0.5)
ax7.vlines(
    valid_years, first_storms, last_storms, color="gray", alpha=0.6, zorder=1
)
ax7.scatter(
    valid_years,
    first_storms,
    color="#4A86E8",
    s=60,
    zorder=2,
    label="First storm",
)
ax7.scatter(
    valid_years,
    last_storms,
    color="#FF5722",
    s=60,
    zorder=2,
    label="Last storm",
)

for x, y1, y2 in zip(valid_years, first_storms, last_storms):
  ax7.annotate(
      bezpecne_datum(y1),
      (x, y1),
      textcoords="offset points",
      xytext=(10, 0),
      color="#4A86E8",
      fontsize=8,
      va="center",
  )
  ax7.annotate(
      bezpecne_datum(y2),
      (x, y2),
      textcoords="offset points",
      xytext=(10, 0),
      color="#FF5722",
      fontsize=8,
      va="center",
  )

ax7.yaxis.set_major_formatter(
    FuncFormatter(lambda val, pos: bezpecne_datum(val))
)
ax7.set_xticks(range(len(valid_years)))
ax7.set_xticklabels(valid_years, rotation=45, ha="right")
ax7.set_ylabel("Day of year")
ax7.grid(True, axis="both", alpha=0.3, linestyle="--")
ax7.spines["top"].set_visible(False)
ax7.spines["right"].set_visible(False)
ax7.legend(loc="upper left", bbox_to_anchor=(1.02, 1), frameon=False)
st.pyplot(fig7)
plt.close(fig7)

st.divider()

# ==========================================
# 11. ANALÝZA KLIMATOLOGIE
# ==========================================
st.subheader("🏆 Analýza extrémů: Kdy to vře a kdy je klid")

df_denni_stavy = df_uzavrene.diff(axis=0).fillna(df_uzavrene.iloc[0])
df_denni_stavy = (df_denni_stavy > 0).astype(int)
denni_soucty = df_denni_stavy.sum(axis=1).values

df_dny = pd.DataFrame({
    "Datum": pd.date_range(start="2024-01-01", periods=len(df_uzavrene)),
    "Pocet": denni_soucty,
})
df_dny["Hezke_Datum"] = df_dny["Datum"].apply(
    lambda x: f"{x.day:02d} {anglicke_mesice[x.month]}"
)

letni_maska = (df_dny["Datum"].dt.month >= 5) & (df_dny["Datum"].dt.month <= 9)
letni_dny = df_dny[letni_maska]
dny_bez_bourky = letni_dny[letni_dny["Pocet"] == 0].copy()
dny_bez_bourky["Mesic_Jmeno"] = dny_bez_bourky["Datum"].apply(
    lambda x: anglicke_mesice[x.month]
)

col_metric, col_text = st.columns([1, 3])
with col_metric:
  st.metric("Bezpečné dny", f"{len(dny_bez_bourky)} dnů")
with col_text:
  if len(dny_bez_bourky) > 0:
    st.info(
        "**Analýza klidu:** Sezóna v Mostě má tendenci definitivně utichat po"
        " 12. září."
    )

colA, colB = st.columns(2)
with colA:
  st.markdown("### 🔥 Top 15 bouřkových dní")
  top15 = df_dny.sort_values(by="Pocet", ascending=False).head(15)
  fig_top, ax_top = plt.subplots(figsize=(8, 7))
  bars = ax_top.barh(
      top15["Hezke_Datum"][::-1],
      top15["Pocet"][::-1],
      color="#FF5722",
      alpha=0.8,
      edgecolor="black",
      linewidth=0.5,
  )
  for bar in bars:
    width = bar.get_width()
    ax_top.text(
        width - 0.5 if width > 2 else width + 0.2,
        bar.get_y() + bar.get_height() / 2,
        f"{int(width)} let",
        color="white" if width > 2 else "black",
        va="center",
        ha="right" if width > 2 else "left",
        fontweight="bold",
        fontsize=10,
    )
  ax_top.set_title(
      "Dny s nejvyšší historickou pravděpodobností", fontsize=10, pad=10
  )
  ax_top.set_xlabel("Počet výskytů", fontsize=9)
  ax_top.spines["top"].set_visible(False)
  ax_top.spines["right"].set_visible(False)
  ax_top.grid(axis="x", linestyle="--", alpha=0.3)
  st.pyplot(fig_top)
  plt.close(fig_top)

with colB:
  st.markdown("### 🛡️ Dny, kdy v Mostě 'nehřmí'")
  if len(dny_bez_bourky) > 0:
    for mesic in dny_bez_bourky["Mesic_Jmeno"].unique():
      dni_v_mesici = dny_bez_bourky[dny_bez_bourky["Mesic_Jmeno"] == mesic][
          "Hezke_Datum"
      ].tolist()
      st.write(f"**Měsíc {mesic}:**")
      cols = st.columns(4)
      for i, datum in enumerate(dni_v_mesici):
        cols[i % 4].button(datum, key=f"btn_{datum}", disabled=True)

st.markdown("### 🦄 Vzácné bouřkové dny")
soucty_array = np.array(denni_soucty)
nenulove_hodnoty = soucty_array[soucty_array > 0]
if len(nenulove_hodnoty) > 0:
  min_vyskyt = nenulove_hodnoty.min()
  vzacne_indexy = np.where(soucty_array == min_vyskyt)[0]
  st.caption(
      f"Dny, kdy v Mostě udeřila bouřka pouze **{int(min_vyskyt)}x**:"
  )
  cols_rare = st.columns(4)
  for i, den_idx in enumerate(vzacne_indexy):
    datum = pd.to_datetime("2024-01-01") + pd.to_timedelta(
        int(den_idx), unit="D"
    )
    with cols_rare[i % 4]:
      st.button(
          f"{datum.strftime('%d. %b')}",
          key=f"rare_unicorn_{den_idx}",
          width="stretch",
      )

st.divider()

pocet_uzavrenych_let = len(roky_uzavrene)
max_prob = (top15["Pocet"].max() / pocet_uzavrenych_let) * 100
st.warning(
    f"**Věděli jste?** Nejkritičtějším dnem je **{top15['Hezke_Datum'].iloc[0]}**."
    f" Pravděpodobnost bouřky je rekordních **{max_prob:.1f} %**."
)

st.divider()

# ==========================================
# 12. ANALÝZA: KDE SEZÓNA NEJVÍC "SKÁČE"
# ==========================================
st.subheader("🚀 Kde sezóna nejvíc nabírá obrátky")

okno_skoku = st.radio(
    "Sledovat nárůst během:",
    options=[7, 14],
    format_func=lambda x: f"{x} dní",
    horizontal=True,
)

df_dny["Smooth"] = df_dny["Pocet"].rolling(window=20, center=True).mean()
df_dny["Slope"] = df_dny["Smooth"].diff(periods=okno_skoku)

idx_max_slope = df_dny["Slope"].idxmax()
datum_skoku_start = df_dny.iloc[idx_max_slope - okno_skoku]["Hezke_Datum"]
datum_skoku_end = df_dny.iloc[idx_max_slope]["Hezke_Datum"]

c1, c2 = st.columns([1, 2])
with c1:
  st.info(f"**Největší skok ({okno_skoku} dní):**")
  st.write(f"Mezi **{datum_skoku_start}** a **{datum_skoku_end}**.")
  st.metric("Nárůst intenzity", f"+{df_dny.iloc[idx_max_slope]['Slope']:.2f}")

with c2:
  fig_acc, ax_acc = plt.subplots(figsize=(10, 5))
  ax_acc.fill_between(
      df_dny["Datum"], df_dny["Smooth"], color="#003049", alpha=0.1
  )
  ax_acc.plot(
      df_dny["Datum"],
      df_dny["Smooth"],
      color="#003049",
      linewidth=2,
      label="Intenzita sezóny",
  )

  segment_x = df_dny.iloc[idx_max_slope - okno_skoku : idx_max_slope + 1][
      "Datum"
  ]
  segment_y = df_dny.iloc[idx_max_slope - okno_skoku : idx_max_slope + 1][
      "Smooth"
  ]
  ax_acc.plot(
      segment_x, segment_y, color="red", linewidth=4, label="Největší zrychlení"
  )

  ax_acc.set_xticks(
      [pd.to_datetime(f"2024-{m:02d}-01") for m in range(1, 13)]
  )
  ax_acc.set_xticklabels([
      "Led",
      "Úno",
      "Bře",
      "Dub",
      "Kvě",
      "Čvn",
      "Čvc",
      "Srp",
      "Zář",
      "Říj",
      "Lis",
      "Pro",
  ])
  ax_acc.grid(True, alpha=0.2, linestyle="--")
  ax_acc.spines["top"].set_visible(False)
  ax_acc.spines["right"].set_visible(False)
  ax_acc.legend(loc="upper left")
  st.pyplot(fig_acc)
  plt.close(fig_acc)

st.divider()

# ==========================================
# 13. ANALÝZA: MOMENTUM SEZÓNY
# ==========================================
st.subheader("⏱️ Momentum sezóny")

df_dny["Speed_Clean"] = df_dny["Smooth"].diff()
df_dny["Speed_Trend"] = (
    df_dny["Speed_Clean"].rolling(window=21, center=True).mean()
)

try:
  idx_start = df_dny[
      (df_dny["Datum"].dt.month >= 3) & (df_dny["Speed_Trend"] > 0)
  ].index[0]
  idx_max_v = df_dny["Speed_Trend"].idxmax()
  idx_peak_v = df_dny["Smooth"].idxmax()
  idx_min_v = df_dny["Speed_Trend"].idxmin()

  milniky_v2 = [
      {
          "Událost": "🌱 Start",
          "Datum": df_dny.iloc[idx_start]["Hezke_Datum"],
          "Význam": "Sezóna se probouzí",
      },
      {
          "Událost": "🚀 Max. zrychlení",
          "Datum": df_dny.iloc[idx_max_v]["Hezke_Datum"],
          "Význam": "Nejstrmější vzestup",
      },
      {
          "Událost": "🏔️ Vrchol",
          "Datum": df_dny.iloc[idx_peak_v]["Hezke_Datum"],
          "Význam": "Dosažení vrcholu",
      },
      {
          "Událost": "📉 Max. útlum",
          "Datum": df_dny.iloc[idx_min_v]["Hezke_Datum"],
          "Význam": "Nejrychlejší konec",
      },
  ]
except:
  milniky_v2 = []

c_tab, c_gra = st.columns([1, 2])
with c_tab:
  if milniky_v2:
    st.table(pd.DataFrame(milniky_v2))

with c_gra:
  fig_mom, ax_mom = plt.subplots(figsize=(10, 6))
  dny = df_dny["Datum"]
  rychlost = df_dny["Speed_Trend"].fillna(0)

  ax_mom.fill_between(
      dny,
      0,
      rychlost,
      where=(rychlost >= 0),
      color="#2ecc71",
      alpha=0.4,
      label="Zrychlování",
  )
  ax_mom.fill_between(
      dny,
      0,
      rychlost,
      where=(rychlost < 0),
      color="#e74c3c",
      alpha=0.4,
      label="Zpomalování",
  )
  ax_mom.plot(dny, rychlost, color="#2c3e50", linewidth=1.5, alpha=0.8)
  ax_mom.axhline(0, color="black", linewidth=1, alpha=0.5)

  if milniky_v2:
    for m in [idx_max_v, idx_min_v, idx_peak_v]:
      ax_mom.scatter(
          df_dny.iloc[m]["Datum"],
          df_dny.iloc[m]["Speed_Trend"],
          color="black",
          s=30,
          zorder=5,
      )

  ax_mom.set_xticks(
      [pd.to_datetime(f"2024-{m:02d}-01") for m in range(1, 13)]
  )
  ax_mom.set_xticklabels([
      "Led",
      "Úno",
      "Bře",
      "Dub",
      "Kvě",
      "Čvn",
      "Čvc",
      "Srp",
      "Zář",
      "Říj",
      "Lis",
      "Pro",
  ])
  ax_mom.grid(True, axis="y", alpha=0.1)
  ax_mom.spines["top"].set_visible(False)
  ax_mom.spines["right"].set_visible(False)
  ax_mom.set_ylabel("Síla trendu")
  st.pyplot(fig_mom)
  plt.close(fig_mom)

st.divider()

# ==========================================
# 14. ANALÝZA: NEJSTRMĚJŠÍ SKOK O PEVNOU HODNOTU
# ==========================================
st.subheader("🏃‍♂️ Sprint: Kdy průměr nejrychleji nastřádá +X bouřek")

cil_narustu = st.number_input(
    "Zadejte cílový nárůst průměru:", value=5.0, step=0.5
)
mean_curve = df_stats["mean"].values
nejkratsi_doba = len(mean_curve)
vitezny_start, vitezny_konec = 0, 0

for start_den in range(len(mean_curve)):
  for konec_den in range(start_den + 1, len(mean_curve)):
    if mean_curve[konec_den] - mean_curve[start_den] >= cil_narustu:
      if konec_den - start_den < nejkratsi_doba:
        nejkratsi_doba = konec_den - start_den
        vitezny_start = start_den
        vitezny_konec = konec_den
      break

if vitezny_konec > 0:
  c1, c2, c3 = st.columns(3)
  c1.metric(
      "Období",
      f"{df_dny.iloc[vitezny_start]['Hezke_Datum']} –"
      f" {df_dny.iloc[vitezny_konec]['Hezke_Datum']}",
  )
  c2.metric("Trvání", f"{nejkratsi_doba} dní")
  c3.metric(
      "Nárůst",
      f"+{mean_curve[vitezny_konec] - mean_curve[vitezny_start]:.1f}",
  )

  fig8, ax8 = plt.subplots(figsize=(12, 5))
  ax8.plot(
      df_dny["Datum"], mean_curve, color="#555555", linewidth=2.5, alpha=0.8
  )

  vitez_x = df_dny.iloc[vitezny_start : vitezny_konec + 1]["Datum"]
  vitez_y = mean_curve[vitezny_start : vitezny_konec + 1]
  ax8.plot(vitez_x, vitez_y, color="red", linewidth=5)
  ax8.hlines(
      [mean_curve[vitezny_start], mean_curve[vitezny_konec]],
      df_dny["Datum"].iloc[0],
      vitez_x.iloc[-1],
      colors="red",
      linestyles="--",
      alpha=0.4,
  )

  ax8.set_xticks([pd.to_datetime(f"2024-{m:02d}-01") for m in range(1, 13)])
  ax8.set_xticklabels([
      "Led",
      "Úno",
      "Bře",
      "Dub",
      "Kvě",
      "Čvn",
      "Čvc",
      "Srp",
      "Zář",
      "Říj",
      "Lis",
      "Pro",
  ])
  ax8.grid(True, alpha=0.2)
  st.pyplot(fig8)
  plt.close(fig8)

st.divider()

# ==========================================
# 15. ANALÝZA: KALENDÁŘ PRAVDĚPODOBNOSTI
# ==========================================
st.subheader("Šance na bouřku v konkrétní den")

okno_vyhlazeni = st.slider(
    "Nastavení vyhlazení (počet dní):", min_value=1, max_value=31, value=15
)
df_dny["Prob_Pct"] = (df_dny["Pocet"] / pocet_uzavrenych_let) * 100
df_dny["Prob_Smooth"] = (
    df_dny["Prob_Pct"].rolling(window=okno_vyhlazeni, center=True).mean()
)

c_prob1, c_prob2 = st.columns([1, 3])
with c_prob1:
  max_p = df_dny["Prob_Smooth"].max()
  st.metric("Nejvyšší průměrná šance", f"{max_p:.1f} %")
  st.write(
      "Kolem"
      f" **{df_dny.iloc[df_dny['Prob_Smooth'].idxmax()]['Hezke_Datum']}** je"
      " špička."
  )

with c_prob2:
  fig_prob = go.Figure()
  fig_prob.add_trace(
      go.Scatter(
          x=df_dny["Datum"],
          y=df_dny["Prob_Smooth"],
          fill="tozeroy",
          mode="lines",
          line=dict(color="#1f77b4", width=2),
          hovertemplate=(
              "<b>%{x|%d. %B}</b><br>Pravděpodobnost: %{y:.1f}%<extra></extra>"
          ),
      )
  )
  fig_prob.update_layout(
      template="plotly_dark",
      margin=dict(l=0, r=0, t=20, b=0),
      height=450,
      xaxis=dict(tickformat="%b", dtick="M1"),
      yaxis=dict(title="Pravděpodobnost (%)"),
      hovermode="x unified",
  )
  st.plotly_chart(fig_prob, width="stretch")

st.divider()

# ==========================================
# 16. KORELACE: ERA5 SEZÓNNÍ ANALÝZA & MAKROKLIMA
# ==========================================
st.subheader("📊 Klimatický detektiv: Co řídí bouřky v Mostě?")


@st.cache_data(ttl=86400)
def ziskej_era5_sezona(roky_seznam):
  if not roky_seznam:
    return None
  lat, lon = 50.503, 13.636
  url = (
      f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={min(roky_seznam)}-04-01&end_date={max(roky_seznam)}-09-30&daily=temperature_2m_mean,precipitation_sum,dew_point_2m_mean&timezone=Europe/Berlin"
  )
  response = requests.get(url)
  if response.status_code == 200:
    data = response.json()
    return pd.DataFrame({
        "Datum": pd.to_datetime(data["daily"]["time"]),
        "Teplota": data["daily"]["temperature_2m_mean"],
        "Srazky": data["daily"]["precipitation_sum"],
        "Rosny_Bod": data["daily"]["dew_point_2m_mean"],
    })
  return None


@st.cache_data(ttl=604800)
def stahni_nao():
  url = "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii"
  try:
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
      return pd.read_csv(
          io.StringIO(resp.text),
          sep=r"\s+",
          header=None,
          names=["Rok", "Mesic", "NAO_Index"],
      )
  except:
    pass
  return None


@st.cache_data(ttl=604800)
def stahni_enso():
  url = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
  try:
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
      df = pd.read_csv(io.StringIO(resp.text), sep=r"\s+")
      df.rename(columns={"YR": "Rok", "ANOM": "ENSO"}, inplace=True)
      mesice_map = {
          "DJF": 1,
          "JFM": 2,
          "FMA": 3,
          "MAM": 4,
          "AMJ": 5,
          "MJJ": 6,
          "JJA": 7,
          "JAS": 8,
          "ASO": 9,
          "SON": 10,
          "OND": 11,
          "NDJ": 12,
      }
      df["Mesic"] = df["SEAS"].map(mesice_map)
      return df[["Rok", "Mesic", "ENSO"]]
  except:
    pass
  return None


mesic_nazvy = {
    0: "Celá sezóna",
    4: "Duben",
    5: "Květen",
    6: "Červen",
    7: "Červenec",
    8: "Srpen",
    9: "Září",
}
vybrany_mesic_klic = st.selectbox(
    "Vyber období pro analýzu:",
    options=list(mesic_nazvy.keys()),
    format_func=lambda x: mesic_nazvy[x],
)

parametr_k_analyze = st.selectbox("Vyber parametr pro osu X:", [
    "Anomálie rosného bodu (°C)",
    "Teplotní anomálie (°C)",
    "Celkové srážky (mm)",
    "NAO Index (Atlantická oscilace)",
    "ENSO (El Niño / La Niña)",
])

valid_years = [int(str(r).strip()) for r in roky_uzavrene]
with st.spinner("Stahuji klimatická a satelitní data..."):
  df_raw_klima = ziskej_era5_sezona(valid_years)
  df_nao = stahni_nao()
  df_enso = stahni_enso()

if df_raw_klima is not None:
  df_filtered = (
      df_raw_klima[df_raw_klima["Datum"].dt.month.isin([4, 5, 6, 7, 8, 9])]
      if vybrany_mesic_klic == 0
      else df_raw_klima[df_raw_klima["Datum"].dt.month == vybrany_mesic_klic]
  )
  rok_map = {int(str(k).strip()): k for k in roky_uzavrene}

  if vybrany_mesic_klic == 0:
    df_agg = (
        df_filtered.groupby(df_filtered["Datum"].dt.year)
        .agg(
            Teplota=("Teplota", "mean"),
            Srazky=("Srazky", "sum"),
            Rosny_Bod=("Rosny_Bod", "mean"),
        )
        .reset_index()
    )
    df_agg.rename(columns={"Datum": "Rok"}, inplace=True)
    df_agg["Pocet_Bourek"] = [
        int(np.nanmax(df_roky[str(r)].values))
        if str(r) in df_roky.columns
        else 0
        for r in df_agg["Rok"]
    ]
  else:
    bourky_v_mesici = []
    for r in df_filtered["Datum"].dt.year.unique():
      rok_s = str(r)
      if rok_s not in df_roky.columns:
        bourky_v_mesici.append(0)
        continue
      prvni_den = pd.to_datetime(f"2024-{vybrany_mesic_klic:02d}-01")
      m_start_idx, m_end_idx = (
          prvni_den.dayofyear - 1,
          (prvni_den + pd.offsets.MonthEnd(0)).dayofyear - 1,
      )
      val_end = df_roky[rok_s].iloc[m_end_idx]
      val_start = (
          df_roky[rok_s].iloc[m_start_idx - 1] if m_start_idx > 0 else 0
      )
      bourky_v_mesici.append(int(val_end - val_start))

    df_agg = (
        df_filtered.groupby(df_filtered["Datum"].dt.year)
        .agg(
            Teplota=("Teplota", "mean"),
            Srazky=("Srazky", "sum"),
            Rosny_Bod=("Rosny_Bod", "mean"),
        )
        .reset_index()
    )
    df_agg.rename(columns={"Datum": "Rok"}, inplace=True)
    df_agg["Pocet_Bourek"] = bourky_v_mesici

  if df_nao is not None:
    if vybrany_mesic_klic == 0:
      nao_filt = (
          df_nao[df_nao["Mesic"].isin([4, 5, 6, 7, 8, 9])]
          .groupby("Rok")["NAO_Index"]
          .mean()
          .reset_index()
      )
    else:
      nao_filt = df_nao[df_nao["Mesic"] == vybrany_mesic_klic][
          ["Rok", "NAO_Index"]
      ]
    df_agg = df_agg.merge(nao_filt, on="Rok", how="left")
  else:
    df_agg["NAO_Index"] = np.nan

  if df_enso is not None:
    if vybrany_mesic_klic == 0:
      enso_filt = (
          df_enso[df_enso["Mesic"].isin([4, 5, 6, 7, 8, 9])]
          .groupby("Rok")["ENSO"]
          .mean()
          .reset_index()
      )
    else:
      enso_filt = df_enso[df_enso["Mesic"] == vybrany_mesic_klic][
          ["Rok", "ENSO"]
      ]
    df_agg = df_agg.merge(enso_filt, on="Rok", how="left")
  else:
    df_agg["ENSO"] = np.nan

  df_agg["Anom_Temp"] = df_agg["Teplota"] - df_agg["Teplota"].mean()
  df_agg["Anom_Rosny"] = df_agg["Rosny_Bod"] - df_agg["Rosny_Bod"].mean()

  if "Teplotní" in parametr_k_analyze:
    x_col, scale = "Anom_Temp", "RdBu_r"
  elif "srážky" in parametr_k_analyze:
    x_col, scale = "Srazky", "BrBG"
  elif "NAO" in parametr_k_analyze:
    x_col, scale = "NAO_Index", "PuOr_r"
  elif "ENSO" in parametr_k_analyze:
    x_col, scale = "ENSO", "RdBu_r"
  else:
    x_col, scale = "Anom_Rosny", "YlGnBu"

  df_agg = df_agg.dropna(subset=[x_col, "Pocet_Bourek"])
  df_agg["Rok_str"] = df_agg["Rok"].astype(str)
  r_val = df_agg[x_col].corr(df_agg["Pocet_Bourek"])

  fig = px.scatter(
      df_agg,
      x=x_col,
      y="Pocet_Bourek",
      text="Rok_str",
      hover_name="Rok_str",
      trendline="ols",
      color=x_col,
      color_continuous_scale=scale,
  )

  for trace in fig.data:
    if trace.mode == "lines":
      trace.line.update(color="white", width=3, dash="dot")
    else:
      trace.update(
          mode="markers+text",
          textposition="top center",
          textfont=dict(color="white", size=10),
          marker=dict(
              size=14, line=dict(width=1, color="rgba(255,255,255,0.3)")
          ),
      )

  fig.update_layout(
      template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0)
  )
  fig.add_annotation(
      x=0.02,
      y=0.98,
      xref="paper",
      yref="paper",
      text=f"<b>r = {r_val:.2f}</b>",
      showarrow=False,
      font=dict(size=16, color="white"),
      bgcolor="#333333",
      bordercolor="white",
      borderwidth=2,
      borderpad=8,
  )
  st.plotly_chart(fig, width="stretch")

  if "NAO" in parametr_k_analyze:
    st.info(
        "💡 **NAO+ (Kladné hodnoty):** Často znamenají silnější příliv vlhkého"
        " oceánského vzduchu do Evropy.\n**NAO- (Záporné hodnoty):** Blokující"
        " výše, sušší a stabilnější vzduch."
    )
  elif "ENSO" in parametr_k_analyze:
    st.info(
        "💡 **Kladné hodnoty (červená):** Fáze El Niño.\n**Záporné hodnoty"
        " (modrá):** Fáze La Niña. Vliv ENSO na Evropu je nelineární a často se"
        " zpožděním."
    )
else:
  st.error("Nepodařilo se stáhnout data z ERA5 nebo NOAA.")

# ==========================================
# 18. KRESLENÍ (Graf 8: Klimatické indexy vs Srážky v Mostě)
# ==========================================
st.subheader("🌍 Vliv ENSO a NAO na srážky v Mostě (1993 - 2024)")
st.markdown(
    "Srovnání úhrnů srážek z reanalýzy ERA5 (Copernicus) pro souřadnice Mostu"
    " s indexy ENSO a NAO od NOAA."
)


@st.cache_data
def nacti_klimaticka_data():
  import numpy as np

  url_meteo = (
      "https://archive-api.open-meteo.com/v1/archive?"
      "latitude=50.503&longitude=13.636&"
      "start_date=1993-01-01&end_date=2024-12-31&"
      "daily=precipitation_sum&timezone=Europe%2FBerlin"
  )
  r_meteo = requests.get(url_meteo)
  df_precip = pd.DataFrame(r_meteo.json()["daily"])
  df_precip["time"] = pd.to_datetime(df_precip["time"])
  df_precip["Rok"] = df_precip["time"].dt.year
  df_precip["Mesic"] = df_precip["time"].dt.month

  df_rocni = (
      df_precip.groupby("Rok")["precipitation_sum"]
      .sum()
      .reset_index()
      .rename(columns={"precipitation_sum": "Srazky_Rocni"})
  )
  df_leto = (
      df_precip[df_precip["Mesic"].isin([6, 7, 8])]
      .groupby("Rok")["precipitation_sum"]
      .sum()
      .reset_index()
      .rename(columns={"precipitation_sum": "Srazky_Leto"})
  )
  df_jaro = (
      df_precip[df_precip["Mesic"].isin([3, 4, 5])]
      .groupby("Rok")["precipitation_sum"]
      .sum()
      .reset_index()
      .rename(columns={"precipitation_sum": "Srazky_Jaro"})
  )

  df_precip["Rok_Zima"] = np.where(
      df_precip["Mesic"] == 12, df_precip["Rok"] + 1, df_precip["Rok"]
  )
  df_zima = (
      df_precip[df_precip["Mesic"].isin([12, 1, 2])]
      .groupby("Rok_Zima")["precipitation_sum"]
      .sum()
      .reset_index()
      .rename(
          columns={"Rok_Zima": "Rok", "precipitation_sum": "Srazky_Zima"}
      )
  )

  url_enso = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
  r_enso = requests.get(url_enso)
  df_enso = pd.read_csv(io.StringIO(r_enso.text), delim_whitespace=True)

  df_enso_rocni = (
      df_enso.groupby("YR")["ANOM"]
      .mean()
      .reset_index()
      .rename(columns={"YR": "Rok", "ANOM": "ENSO_Rocni"})
  )
  df_enso_leto = df_enso[df_enso["SEAS"] == "JJA"][["YR", "ANOM"]].rename(
      columns={"YR": "Rok", "ANOM": "ENSO_Leto"}
  )
  df_enso_jaro = df_enso[df_enso["SEAS"] == "MAM"][["YR", "ANOM"]].rename(
      columns={"YR": "Rok", "ANOM": "ENSO_Jaro"}
  )
  df_enso_zima = df_enso[df_enso["SEAS"] == "DJF"][["YR", "ANOM"]].rename(
      columns={"YR": "Rok", "ANOM": "ENSO_Zima"}
  )

  url_nao = "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii"
  r_nao = requests.get(url_nao)
  df_nao = pd.read_csv(
      io.StringIO(r_nao.text),
      delim_whitespace=True,
      header=None,
      names=["Rok", "Mesic", "NAO"],
  )

  df_nao_rocni = (
      df_nao.groupby("Rok")["NAO"]
      .mean()
      .reset_index()
      .rename(columns={"NAO": "NAO_Rocni"})
  )
  df_nao_leto = (
      df_nao[df_nao["Mesic"].isin([6, 7, 8])]
      .groupby("Rok")["NAO"]
      .mean()
      .reset_index()
      .rename(columns={"NAO": "NAO_Leto"})
  )
  df_nao_jaro = (
      df_nao[df_nao["Mesic"].isin([3, 4, 5])]
      .groupby("Rok")["NAO"]
      .mean()
      .reset_index()
      .rename(columns={"NAO": "NAO_Jaro"})
  )

  df_nao["Rok_Zima"] = np.where(
      df_nao["Mesic"] == 12, df_nao["Rok"] + 1, df_nao["Rok"]
  )
  df_nao_zima = (
      df_nao[df_nao["Mesic"].isin([12, 1, 2])]
      .groupby("Rok_Zima")["NAO"]
      .mean()
      .reset_index()
      .rename(columns={"Rok_Zima": "Rok", "NAO": "NAO_Zima"})
  )

  dfs = [
      df_rocni,
      df_leto,
      df_jaro,
      df_zima,
      df_enso_rocni,
      df_enso_leto,
      df_enso_jaro,
      df_enso_zima,
      df_nao_rocni,
      df_nao_leto,
      df_nao_jaro,
      df_nao_zima,
  ]

  from functools import reduce

  df_final = reduce(
      lambda left, right: pd.merge(left, right, on="Rok", how="outer"), dfs
  )

  df_final = df_final[
      (df_final["Rok"] >= 1993) & (df_final["Rok"] <= 2024)
  ].dropna()
  df_final["Rok_str"] = df_final["Rok"].astype(int).astype(str)

  return df_final


try:
  df_klima = nacti_klimaticka_data()

  col_klima1, col_klima2 = st.columns(2)
  with col_klima1:
    x_moznosti = [
        "NAO_Zima",
        "NAO_Jaro",
        "NAO_Leto",
        "NAO_Rocni",
        "ENSO_Zima",
        "ENSO_Jaro",
        "ENSO_Leto",
        "ENSO_Rocni",
    ]
    x_osa = st.selectbox(
        "Vyberte klimatický index (Osa X):", options=x_moznosti, index=0
    )
  with col_klima2:
    y_moznosti = ["Srazky_Zima", "Srazky_Jaro", "Srazky_Leto", "Srazky_Rocni"]
    y_osa = st.selectbox(
        "Vyberte období pro Srážky (Osa Y):", options=y_moznosti, index=0
    )

  r_val = df_klima[x_osa].corr(df_klima[y_osa])

  fig_klima = px.scatter(
      df_klima,
      x=x_osa,
      y=y_osa,
      text="Rok_str",
      hover_name="Rok_str",
      trendline="ols",
      color=x_osa,
      color_continuous_scale="RdBu_r",
  )

  for trace in fig_klima.data:
    if trace.mode == "lines":
      trace.line.update(color="white", width=3, dash="dot")
    else:
      trace.update(
          mode="markers+text",
          textposition="top center",
          textfont=dict(color="white", size=10),
          marker=dict(
              size=14, line=dict(width=1, color="rgba(255,255,255,0.3)")
          ),
      )

  fig_klima.update_layout(
      template="plotly_dark",
      height=600,
      margin=dict(l=20, r=20, t=50, b=20),
      xaxis_title=f"Index: {x_osa}",
      yaxis_title=f"Srážky [mm] ({y_osa})",
  )

  fig_klima.add_annotation(
      x=0.02,
      y=0.98,
      xref="paper",
      yref="paper",
      text=f"<b>r = {r_val:.2f}</b>",
      showarrow=False,
      font=dict(size=16, color="white"),
      bgcolor="#333333",
      bordercolor="white",
      borderwidth=2,
      borderpad=4,
  )

  st.plotly_chart(fig_klima, width="stretch")

except Exception as e:
  st.error(f"Nepodařilo se načíst data pro klimatologický graf. Chyba: {e}")

st.divider()