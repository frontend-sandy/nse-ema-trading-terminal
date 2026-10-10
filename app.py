import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
import io

# 1. Page config with mobile sidebar collapsed by default
st.set_page_config(
    page_title="10/20 EMA Strategy Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Inject Mobile-Responsive CSS
st.markdown("""
    <style>
    /* Reduce padding on mobile devices */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    
    /* Auto-wrap horizontal metric containers on smaller screens */
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        div[data-testid="column"] {
            min-width: 48% !important;
            margin-bottom: 8px !important;
        }
        .stMetric {
            background-color: #1e1e1e;
            padding: 8px;
            border-radius: 6px;
        }
    }
    </style>
""", unsafe_allow_html=True)

st.title("📈 10/20 EMA Strategy Terminal")

# Fetch NSE Symbol List safely
@st.cache_data(ttl=86400)
def load_nse_symbols():
    fallback_list = [
        "PERSISTENT.NS", "MANKIND.NS", "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", 
        "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", 
        "SUNPHARMA.NS", "TITAN.NS", "CIPLA.NS", "DRREDDY.NS", "WIPRO.NS", "HCLTECH.NS", 
        "COFORGE.NS", "LTTS.NS", "DIXON.NS"
    ]
    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            symbols = [f"{symbol.strip()}.NS" for symbol in df['SYMBOL'].dropna().unique()]
            return sorted(symbols)
    except Exception:
        pass
    return fallback_list

ALL_NSE_STOCKS = load_nse_symbols()

# Pre-defined Sectors
WATCHLISTS = {
    "IT & Tech": ["PERSISTENT.NS", "LTTS.NS", "COFORGE.NS", "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
    "Nifty Core": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS"],
    "Pharma & Healthcare": ["MANKIND.NS", "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "TORNTPHARM.NS"],
    "Custom Selection": []
}

# Sidebar Navigation
st.sidebar.header("⚙️ Strategy Settings")
mode = st.sidebar.selectbox("Select Watchlist", list(WATCHLISTS.keys()))

if mode == "Custom Selection":
    selected_stocks = st.sidebar.multiselect(
        "Search & Pick NSE Stocks:",
        options=ALL_NSE_STOCKS,
        default=["PERSISTENT.NS", "MANKIND.NS", "RELIANCE.NS"]
    )
else:
    selected_stocks = WATCHLISTS[mode]

timeframe = st.sidebar.selectbox("Timeframe", ["15m", "60m", "1d"], index=2)
period = st.sidebar.selectbox("Historical Period", ["1mo", "3mo", "6mo", "1y"], index=2)
rr_ratio = st.sidebar.slider("Target Risk-Reward Ratio (1:X)", min_value=1.0, max_value=3.0, value=2.0, step=0.5)

# Data fetching helper
def fetch_clean_data(symbol):
    try:
        df = yf.download(symbol, period=period, interval=timeframe, progress=False)
        if df.empty:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.dropna()
        
        close_series = df['Close'].squeeze()
        low_series = df['Low'].squeeze()
        high_series = df['High'].squeeze()
        open_series = df['Open'].squeeze()

        df_clean = pd.DataFrame({
            'Open': open_series,
            'High': high_series,
            'Low': low_series,
            'Close': close_series
        }, index=df.index)

        # Calculate EMAs
        df_clean['EMA_10'] = df_clean['Close'].ewm(span=10, adjust=False).mean()
        df_clean['EMA_20'] = df_clean['Close'].ewm(span=20, adjust=False).mean()
        df_clean['EMA_50'] = df_clean['Close'].ewm(span=50, adjust=False).mean()

        # Strategy Rules
        df_clean['Uptrend'] = (df_clean['Close'] > df_clean['EMA_50']) & (df_clean['EMA_10'] > df_clean['EMA_20'])
        df_clean['Near_20EMA'] = (df_clean['Low'] <= df_clean['EMA_20'] * 1.008) & (df_clean['Close'] >= df_clean['EMA_20'] * 0.985)
        df_clean['Buy_Signal'] = df_clean['Uptrend'] & df_clean['Near_20EMA']

        return df_clean
    except Exception:
        return None

tab1, tab2, tab3 = st.tabs(["🚀 Scanner", "📊 Chart Setup", "💼 Live Positions"])

# TAB 1: SCANNER
with tab1:
    st.subheader(f"Scanner ({len(selected_stocks)} Tickers)")
    
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()

    scan_results = []
    
    if selected_stocks:
        with st.spinner("Scanning markets..."):
            for symbol in selected_stocks:
                df = fetch_clean_data(symbol)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    close = float(latest['Close'])
                    ema20 = float(latest['EMA_20'])
                    ema50 = float(latest['EMA_50'])
                    
                    recent_swing_low = float(df['Low'].tail(5).min())
                    sl_price = min(recent_swing_low, ema50 * 0.995)
                    risk = max(close - sl_price, close * 0.01)
                    target_price = close + (risk * rr_ratio)
                    
                    if latest['Buy_Signal']:
                        status = "🔥 BUY ZONE"
                        buy_p = f"₹{close:.2f}"
                        sl_p = f"₹{sl_price:.2f}"
                        tgt_p = f"₹{target_price:.2f}"
                    elif latest['Uptrend']:
                        status = "⚡ Uptrend"
                        buy_p = f"₹{close:.2f}"
                        sl_p = f"₹{sl_price:.2f}"
                        tgt_p = f"₹{target_price:.2f}"
                    else:
                        status = "⚠️ Inactive"
                        buy_p = "-"
                        sl_p = "-"
                        tgt_p = "-"

                    scan_results.append({
                        "Ticker": symbol,
                        "Price": f"₹{close:.2f}",
                        "Buy": buy_p,
                        "SL": sl_p,
                        "Target": tgt_p,
                        "Status": status
                    })

    if scan_results:
        results_df = pd.DataFrame(scan_results)
        st.dataframe(results_df, hide_index=True, use_container_width=True, height=350)
    else:
        st.info("Select tickers in the sidebar to run scan.")

# TAB 2: DETAILED TRADE SETUP CHART
with tab2:
    chart_ticker = st.selectbox("Select Ticker for Charting:", ALL_NSE_STOCKS, index=0)
    df_single = fetch_clean_data(chart_ticker)

    if df_single is not None and not df_single.empty:
        latest = df_single.iloc[-1]
        close = float(latest['Close'])
        ema50 = float(latest['EMA_50'])
        
        swing_low = float(df_single['Low'].tail(5).min())
        sl_price = min(swing_low, ema50 * 0.995)
        risk = max(close - sl_price, close * 0.01)
        target_price = close + (risk * rr_ratio)

        # Responsive Metrics
        m1, m2 = st.columns(2)
        m1.metric("🟢 Entry Buy", f"₹{close:.2f}")
        m2.metric("🔴 Stop Loss (SL)", f"₹{sl_price:.2f}", delta=f"-₹{risk:.2f}", delta_color="inverse")
        
        m3, m4 = st.columns(2)
        m3.metric("🎯 Target Price", f"₹{target_price:.2f}", delta=f"+₹{risk * rr_ratio:.2f}")
        m4.metric("📊 Risk/Share", f"₹{risk:.2f}")

        # Plotly Candlestick Chart (Mobile Optimized)
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_single.index,
            open=df_single['Open'], high=df_single['High'], low=df_single['Low'], close=df_single['Close'],
            name="Price"
        ))
        fig.add_trace(go.Scatter(x=df_single.index, y=df_single['EMA_10'], line=dict(color='orange', width=1.5), name="10 EMA"))
        fig.add_trace(go.Scatter(x=df_single.index, y=df_single['EMA_20'], line=dict(color='blue', width=2), name="20 EMA"))
        fig.add_trace(go.Scatter(x=df_single.index, y=df_single['EMA_50'], line=dict(color='purple', width=2), name="50 EMA"))

        fig.add_hline(y=close, line_dash="dash", line_color="green", annotation_text=f"BUY: ₹{close:.2f}")
        fig.add_hline(y=sl_price, line_dash="dash", line_color="red", annotation_text=f"SL: ₹{sl_price:.2f}")
        fig.add_hline(y=target_price, line_dash="dash", line_color="cyan", annotation_text=f"TGT: ₹{target_price:.2f}")

        fig.update_layout(
            title=f"{chart_ticker} — Trade Levels",
            yaxis_title="Price (INR)",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=400,
            margin=dict(l=10, r=10, t=35, b=10)
        )
        st.plotly_chart(fig, use_container_width=True, config={'responsive': True})

# TAB 3: LIVE POSITIONS & TRAILING SL ENGINE
with tab3:
    st.subheader("💼 Active Holdings & Dynamic TSL")
    
    if "positions" not in st.session_state:
        st.session_state.positions = [
            {"Ticker": "PERSISTENT.NS", "Buy_Price": 5500.00, "Qty": 20, "Initial_SL": 5400.00},
            {"Ticker": "MANKIND.NS", "Buy_Price": 2425.00, "Qty": 30, "Initial_SL": 2390.00}
        ]

    with st.expander("➕ Add Open Position"):
        with st.form("add_pos_form"):
            p_symbol = st.selectbox("Ticker", ALL_NSE_STOCKS, index=0)
            c1, c2 = st.columns(2)
            p_price = c1.number_input("Buy Price (₹)", min_value=1.0, value=2000.0, step=10.0)
            p_qty = c2.number_input("Quantity", min_value=1, value=10, step=1)
            p_sl = st.number_input("Initial SL Price (₹)", min_value=1.0, value=1950.0, step=10.0)
            
            if st.form_submit_button("Add Position", use_container_width=True):
                st.session_state.positions.append({
                    "Ticker": p_symbol, "Buy_Price": float(p_price), "Qty": int(p_qty), "Initial_SL": float(p_sl)
                })
                st.toast(f"Added {p_symbol}!")
                st.rerun()

    if not st.session_state.positions:
        st.info("No active positions tracked.")
    else:
        # Responsive Card Grid for Open Positions
        for idx, pos in enumerate(st.session_state.positions):
            df_p = fetch_clean_data(pos["Ticker"])
            if df_p is not None and not df_p.empty:
                latest = df_p.iloc[-1]
                curr_price = float(latest['Close'])
                ema10 = float(latest['EMA_10'])
                ema20 = float(latest['EMA_20'])
                
                pnl = (curr_price - pos["Buy_Price"]) * pos["Qty"]
                pnl_pct = ((curr_price - pos["Buy_Price"]) / pos["Buy_Price"]) * 100
                
                raw_tsl = max(ema10, ema20) if curr_price > pos["Buy_Price"] else pos["Initial_SL"]
                active_tsl = max(pos["Initial_SL"], raw_tsl * 0.995)
                tsl_dist = ((curr_price - active_tsl) / curr_price) * 100
                
                if curr_price <= pos["Initial_SL"]:
                    rec = "🚨 EXIT NOW (SL Hit)"
                elif curr_price <= active_tsl:
                    rec = "⚠️ TRAIL SL BROKEN (Book Profit)"
                elif curr_price > pos["Buy_Price"] and ema10 > ema20:
                    rec = "🔥 RIDE THE RALLY" if pnl_pct >= 5.0 else "🟢 HOLD & RIDE"
                else:
                    rec = "🟡 HOLD (Consolidating)"

                with st.container(border=True):
                    # Header Row: Symbol & PnL
                    r1_c1, r1_c2 = st.columns([2, 1])
                    r1_c1.markdown(f"### {pos['Ticker']}")
                    if pnl >= 0:
                        r1_c2.success(f"₹{pnl:+.2f} ({pnl_pct:+.1f}%)")
                    else:
                        r1_c2.error(f"₹{pnl:+.2f} ({pnl_pct:+.1f}%)")
                    
                    # Details Grid
                    r2_c1, r2_c2 = st.columns(2)
                    r2_c1.write(f"**Live:** ₹{curr_price:.2f}\n**Qty:** {pos['Qty']}")
                    r2_c2.write(f"**TSL:** ₹{active_tsl:.2f}\n**Buf:** {tsl_dist:.1f}%")
                    
                    # Recommendation & Exit Button
                    st.caption(f"Status: **{rec}**")
                    if st.button("🚪 Exit Position", key=f"exit_{idx}", type="primary", use_container_width=True):
                        exited_item = st.session_state.positions.pop(idx)
                        st.toast(f"Exited {exited_item['Ticker']} at ₹{curr_price:.2f}!")
                        st.rerun()

        # Visual Trailing SL Chart Inspector
        st.divider()
        st.subheader("📉 Trailing SL Chart Inspector")
        active_tickers = [p["Ticker"] for p in st.session_state.positions]
        pos_select = st.selectbox("Select Position:", active_tickers)
        
        selected_pos_data = next(p for p in st.session_state.positions if p["Ticker"] == pos_select)
        df_pos_chart = fetch_clean_data(pos_select)
        
        if df_pos_chart is not None and not df_pos_chart.empty:
            e10_c = float(df_pos_chart['EMA_10'].iloc[-1])
            e20_c = float(df_pos_chart['EMA_20'].iloc[-1])
            tsl_line_val = max(selected_pos_data["Initial_SL"], min(e10_c, e20_c))

            fig_p = go.Figure()
            fig_p.add_trace(go.Candlestick(
                x=df_pos_chart.index,
                open=df_pos_chart['Open'], high=df_pos_chart['High'], low=df_pos_chart['Low'], close=df_pos_chart['Close'],
                name="Price"
            ))
            fig_p.add_trace(go.Scatter(x=df_pos_chart.index, y=df_pos_chart['EMA_10'], line=dict(color='orange', width=2), name="10 EMA"))
            fig_p.add_trace(go.Scatter(x=df_pos_chart.index, y=df_pos_chart['EMA_20'], line=dict(color='blue', width=2), name="20 EMA"))

            fig_p.add_hline(y=selected_pos_data["Buy_Price"], line_dash="dash", line_color="green", annotation_text="BUY")
            fig_p.add_hline(y=tsl_line_val, line_dash="solid", line_color="orange", annotation_text="TSL")

            fig_p.update_layout(
                title=f"{pos_select} — Trailing SL",
                yaxis_title="Price (INR)",
                xaxis_rangeslider_visible=False,
                template="plotly_dark",
                height=380,
                margin=dict(l=10, r=10, t=35, b=10)
            )
            st.plotly_chart(fig_p, use_container_width=True, config={'responsive': True})

        if st.button("🗑️ Clear All Positions", use_container_width=True):
            st.session_state.positions = []
            st.rerun()