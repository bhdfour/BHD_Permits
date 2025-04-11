import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

# Title
st.set_page_config(page_title="Building Permits Dashboard", layout="wide")
st.title("Fulton County Building Permits Dashboard (2019–2024)")

# You know my name
st.markdown("""
<style>
#benjamin-signature {
    position: absolute;
    top: 10px;
    right: 20px;
    opacity: 0.3;
    font-size: 14px;
    font-style: italic;
    color: gray;
    z-index: 9999;
}
</style>
<div id="benjamin-signature">Benjamin Dillard</div>
""", unsafe_allow_html=True)

# Read csvs from GitHub
@st.cache_data
def load_and_prepare_data():
    records = pd.read_csv("BuildingPermits2019_2024,csv")
    status = pd.read_csv("StatusTable.csv")
    types = pd.read_csv("RecordType.csv")

    # Create relationships
    df = records.merge(status, left_on="RECORD STATUS", right_on="Status", how="left")
    df = df.merge(types, on="RECORD TYPE", how="left")

    # Get year from records
    df["RECORD STATUS DATE"] = pd.to_datetime(df["RECORD STATUS DATE"], format="%m/%d/%Y", errors="coerce")
    df["Year"] = df["RECORD STATUS DATE"].dt.year

    # Get zip from records, ignore 0
    df["ZipCode"] = df["ADDR FULL LINE#"].astype(str).str[-5:]
    df = df[df["ZipCode"].str.match(r"^\d{5}$") & (df["ZipCode"] != "00000")]

    return df

df = load_and_prepare_data()

# Add year slicer
st.sidebar.title("📅 Select Year")
available_years = sorted([int(y) for y in df["Year"].dropna().unique() if int(y) != 2042], reverse=True)
selected_year = st.sidebar.selectbox("Year", available_years)
df_filtered = df[df["Year"] == selected_year]

# Add weather API call
st.sidebar.markdown("---")
st.sidebar.title("🌤️ Weather Outlook")

def get_weather(lat=34.0, lon=-84.0): #rounded coordinates from the dataset
    future_time = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%dT%H:00')
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,wind_speed_10m,precipitation",
        "hourly": "temperature_2m,wind_speed_10m,precipitation_probability",
        "timezone": "UTC"
    }
    res = requests.get(url, params=params)
    data = res.json()
    
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    idx = hourly["time"].index(future_time)
    
    return {
        "now": {
            "temp_f": current.get("temperature_2m") * 9/5 + 32,
            "wind_mph": current.get("wind_speed_10m") * 0.621371,
            "precip_in": current.get("precipitation") * 0.0393701
        },
        "24h": {
            "temp_f": hourly["temperature_2m"][idx] * 9/5 + 32,
            "wind_mph": hourly["wind_speed_10m"][idx] * 0.621371,
            "precip_prob": hourly["precipitation_probability"][idx]
        }
    }

weather = get_weather()

# Display weather on sidebar - maybe later I'll say it's a bad day to be outside
# tomorrow if the temperature is going to be above 85 or something
st.sidebar.markdown(f"**Current Temp:** {weather['now']['temp_f']:.1f} °F")
st.sidebar.markdown(f"**Wind Speed:** {weather['now']['wind_mph']:.1f} mph")
st.sidebar.markdown(f"**Precipitation:** {weather['now']['precip_in']:.2f} in")

st.sidebar.markdown("### 📆 Forecast in 24h")
st.sidebar.markdown(f"**Temp:** {weather['24h']['temp_f']:.1f} °F")
st.sidebar.markdown(f"**Wind:** {weather['24h']['wind_mph']:.1f} mph")
st.sidebar.markdown(f"**Chance of Rain:** {weather['24h']['precip_prob']}%")

# Zip by final status (defined on https://gisdata.fultoncountyga.gov/datasets/655f985f43cc40b4bf2ab7bc73d2169b/about)
combo_counts = (
    df_filtered.groupby(["ZipCode", "FinalStatus"])
    .size()
    .reset_index(name="Count")
)

if combo_counts.empty:
    st.warning("No permit data available for the selected year.")
else:
    st.subheader(f"Permits by Zip Code and Final Status ({selected_year})")

    fig = px.bar(
        combo_counts,
        x="Count",
        y="ZipCode",
        color="FinalStatus",
        orientation="h",
        title="Permit Volume by Zip Code and Final Status",
        labels={"Count": "Permit Count", "ZipCode": "Zip Code"},
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)

# Zip tree map
st.subheader(f"Permit Volume by Zip Code - {selected_year}")
zip_treemap_data = (
    df_filtered.groupby("ZipCode")
    .size()
    .reset_index(name="Count")
)

fig_zip_treemap = px.treemap(
    zip_treemap_data,
    path=["ZipCode"],
    values="Count",
    title="Permit Distribution by Zip Code",
)
st.plotly_chart(fig_zip_treemap, use_container_width=True)

# Simplified type in third csv: residential, commercial, multi((family))
st.subheader(f"Permits by Simple Type and Final Status ({selected_year})")
type_combo_counts = (
    df_filtered.groupby(["SimpleType", "FinalStatus"])
    .size()
    .reset_index(name="Count")
)

fig_type_bar = px.bar(
    type_combo_counts,
    x="Count",
    y="SimpleType",
    color="FinalStatus",
    orientation="h",
    title="Permit Volume by Simple Type and Final Status",
    labels={"Count": "Permit Count", "SimpleType": "Permit Type"},
    height=600
)

st.plotly_chart(fig_type_bar, use_container_width=True)

# KPIs: looked at product/service offerings on DW1.com and then searched records
# DESCRIPTION column for keywords to count 'potential' for upsales or services had DW1
# performed that job for the permit

st.markdown("---")
st.subheader("📈 Sales Potential KPIs (Keyword-Based)")

# lowercase for searching
df_filtered["Description_lower"] = df_filtered["DESCRIPTION"].astype(str).str.lower()
# KPI title and matching keyword
kpi_keywords = {
    "Potential for Portable Toilet Sales": "bathroom",
    "Potential for Dumpster Sales": "demolition",
    "Potential for Commercial Flooring Sales": "flooring",
    "Potential for Fencing Sales": "fence"
}
cols = st.columns(4)

# Loop to count the number of times each keyword appears in a description
for idx, (label, keyword) in enumerate(kpi_keywords.items()):
    count = df_filtered["Description_lower"].str.contains(keyword).sum()
    cols[idx].metric(label, f"{count}")

