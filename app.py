import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
import io
import json
import os

# 1. Page Configuration
st.set_page_config(
    page_title="10/20 EMA Strategy Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Inject Mobile-Responsive CSS Styling
st.markdown("""
    <style>
    .block-container { 
        padding-top: 1rem !important; 
        padding-bottom: 1rem !important; 
        padding-left: 0.5rem !important; 
        padding-right: 0.5rem !important; 
    }
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] { 
            flex-wrap: wrap !important; 
        }
        div[data-testid="column"] { 
            min-width: 48% !important; 
            margin-bottom: 8px !important; 
        }
    }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ 10/20 EMA Fast Strategy Terminal")

# 3. File-Based Persistence Helpers (No Hardcoded Positions)
POSITIONS_FILE = "positions.json"

def load_saved_positions():
    """Loads positions from local file if available, else returns empty list."""
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_positions(positions):
    """Saves active positions to local JSON file for session persistence."""
    try:
        with open(POSITIONS_FILE, "w") as f:
            json.dump(positions, f, indent=4)
    except Exception as e:
        st.error(f"Failed to save positions to disk: {e}")

if "positions" not in st.session_state:
    st.session_state.positions = load_saved_positions()

# 4. Symbol Master List Loader (Cached 24 Hours)
@st.cache_data(ttl=86400)
def load_nse_symbols():
    fallback_list = [
        "DRREDDY.NS", "MANKIND.NS", "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", 
        "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "TATAMOTORS.NS", "BAJFINANCE.NS", 
        "SUNPHARMA.NS", "TITAN.NS", "CIPLA.NS", "WIPRO.NS", "HCLTECH.NS", 
        "COFORGE.NS", "LTTS.NS", "DIXON.NS", "PERSISTENT.NS"
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

WATCHLISTS = {
    "Pharma & Healthcare": ["DRREDDY.NS", "MANKIND.NS", "SUNPHARMA.NS", "CIPLA.NS", "TORNTPHARM.NS"],
    "IT & Tech": ["LTTS.NS", "COFORGE.NS", "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "PERSISTENT.NS"],
    "Nifty Core": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS"],
    "Custom Selection": []
}

# 5. Sidebar Controls
st.sidebar.header("⚙️ Settings")
mode = st.sidebar.selectbox("Watchlist", list(WATCHLISTS.keys()))

if mode == "Custom Selection":
    selected_stocks = st.sidebar.multiselect("Pick Stocks:", options=ALL_NSE_STOCKS, default=["DRREDDY.NS", "MANKIND.NS", "RELIANCE.NS"])
else:
    selected_stocks = WATCHLISTS[mode]

timeframe = st.sidebar.selectbox("Timeframe", ["15m", "60m", "1d"], index=2)
period = st.sidebar.selectbox("Period", ["1mo", "3mo", "6mo"], index=1)
rr_ratio = st.sidebar.slider("Risk-Reward Ratio (1:X)", min_value=1.0, max_value=3.0, value=2.0, step=0.5)

# 6. Robust Batch Data Processing Engine
@st.cache_data(ttl=60)
def fetch_batch_data(symbols_tuple, p, tf):
    if not symbols_tuple:
        return {}
    
    symbols = list(set(symbols_tuple))
    results = {}
    
    try:
        data = yf.download(
            symbols, 
            period=p, 
            interval=tf, 
            group_by='ticker', 
            progress=False, 
            threads=True,
            auto_adjust=False,
            actions=False
        )
        
        if data.empty:
            return {}

        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    if isinstance(data.columns, pd.MultiIndex):
                        if symbol in data.columns.levels[0]:
                            df = data[symbol].copy()
                        else:
                            df = data.xs(symbol, axis=1, level=1).copy() if symbol in data.columns.levels[1] else data.copy()
                    else:
                        df = data.copy()
                else:
                    if isinstance(data.columns, pd.MultiIndex):
                        if symbol in data.columns.levels[0]:
                            df = data[symbol].copy()
                        elif symbol in data.columns.levels[1]:
                            df = data.xs(symbol, axis=1, level=1).copy()
                        else:
                            continue
                    else:
                        continue
                
                df = df.dropna(how='all')
                if df.empty or len(df) < 20:
                    continue

                close_series = df['Close'].squeeze().astype(float)
                low_series = df['Low'].squeeze().astype(float)
                high_series = df['High'].squeeze().astype(float)
                open_series = df['Open'].squeeze().astype(float)

                df_clean = pd.DataFrame({
                    'Open': open_series, 
                    'High': high_series, 
                    'Low': low_series, 
                    'Close': close_series
                }, index=df.index).dropna()

                # Calculate EMAs
                df_clean['EMA_10'] = df_clean['Close'].ewm(span=10, adjust=False).mean()
                df_clean['EMA_20'] = df_clean['Close'].ewm(span=20, adjust=False).mean()
                df_clean['EMA_50'] = df_clean['Close'].ewm(span=50, adjust=False).mean()

                # Strategy Rules
                df_clean['Uptrend'] = (df_clean['Close'] > df_clean['EMA_50']) & (df_clean['EMA_10'] > df_clean['EMA_20'])
                df_clean['Near_20EMA'] = (df_clean['Low'] <= df_clean['EMA_20'] * 1.008) & (df_clean['Close'] >= df_clean['EMA_20'] * 0.985)
                df_clean['Buy_Signal'] = df_clean['Uptrend'] & df_clean['Near_20EMA']

                results[symbol] = df_clean
            except Exception:
                continue
    except Exception:
        pass
        
    return results

tab1, tab2, tab3 = st.tabs(["🚀 Fast Scanner", "📊 Chart Setup", "💼 Live Positions"])

# TAB 1: FAST SCANNER
with tab1:
    st.subheader(f"Watchlist Scan ({len(selected_stocks)} Tickers)")
    
    if st.button("🔄 Force Refresh Cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if selected_stocks:
        with st.spinner("Batch processing market data..."):
            stock_data_dict = fetch_batch_data(tuple(selected_stocks), period, timeframe)
            
        scan_results = []
        for symbol in selected_stocks:
            if symbol in stock_data_dict:
                df = stock_data_dict[symbol]
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
                elif latest['Uptrend']:
                    status = "⚡ Uptrend"
                else:
                    status = "⚠️ Inactive"

                scan_results.append({
                    "Ticker": symbol,
                    "Price": f"₹{close:.2f}",
                    "Buy": f"₹{close:.2f}" if status != "⚠️ Inactive" else "-",
                    "SL": f"₹{sl_price:.2f}" if status != "⚠️ Inactive" else "-",
                    "Target": f"₹{target_price:.2f}" if status != "⚠️ Inactive" else "-",
                    "Status": status
                })

        if scan_results:
            st.dataframe(pd.DataFrame(scan_results), hide_index=True, use_container_width=True, height=350)
        else:
            st.warning("No data returned for selected stocks.")
    else:
        st.info("Select tickers in the sidebar.")

# TAB 2: DETAILED TRADE SETUP CHART
with tab2:
    chart_ticker = st.selectbox("Select Ticker for Charting:", ALL_NSE_STOCKS, index=0)
    
    with st.spinner(f"Loading candlestick chart for {chart_ticker}..."):
        chart_data_dict = fetch_batch_data((chart_ticker,), period, timeframe)

    if chart_ticker in chart_data_dict:
        df_single = chart_data_dict[chart_ticker]
        latest = df_single.iloc[-1]
        close = float(latest['Close'])
        ema50 = float(latest['EMA_50'])
        
        swing_low = float(df_single['Low'].tail(5).min())
        sl_price = min(swing_low, ema50 * 0.995)
        risk = max(close - sl_price, close * 0.01)
        target_price = close + (risk * rr_ratio)

        m1, m2 = st.columns(2)
        m1.metric("🟢 Entry Buy", f"₹{close:.2f}")
        m2.metric("🔴 Stop Loss (SL)", f"₹{sl_price:.2f}", delta=f"-₹{risk:.2f}", delta_color="inverse")
        
        m3, m4 = st.columns(2)
        m3.metric("🎯 Target Price", f"₹{target_price:.2f}", delta=f"+₹{risk * rr_ratio:.2f}")
        m4.metric("📊 Risk/Share", f"₹{risk:.2f}")

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_single.index, 
            open=df_single['Open'], 
            high=df_single['High'], 
            low=df_single['Low'], 
            close=df_single['Close'], 
            name="Price"
        ))
        fig.add_trace(go.Scatter(x=df_single.index, y=df_single['EMA_10'], line=dict(color='orange', width=1.5), name="10 EMA"))
        fig.add_trace(go.Scatter(x=df_single.index, y=df_single['EMA_20'], line=dict(color='blue', width=2), name="20 EMA"))
        fig.add_trace(go.Scatter(x=df_single.index, y=df_single['EMA_50'], line=dict(color='purple', width=2), name="50 EMA"))

        fig.add_hline(y=close, line_dash="dash", line_color="green", annotation_text="BUY")
        fig.add_hline(y=sl_price, line_dash="dash", line_color="red", annotation_text="SL")
        fig.add_hline(y=target_price, line_dash="dash", line_color="cyan", annotation_text="TGT")

        fig.update_layout(
            title=f"{chart_ticker} — Technical Setup & Levels",
            yaxis_title="Price (INR)", 
            xaxis_rangeslider_visible=False, 
            template="plotly_dark", 
            height=420, 
            margin=dict(l=10, r=10, t=35, b=10)
        )
        st.plotly_chart(fig, use_container_width=True, config={'responsive': True})
    else:
        st.error(f"Could not load market data for {chart_ticker}. Please pick another stock or refresh.")

# TAB 3: USER DYNAMIC LIVE POSITIONS
with tab3:
    st.subheader("💼 Active Holdings & Dynamic TSL")

    # Form to add custom user positions
    with st.expander("➕ Add New Position", expanded=len(st.session_state.positions) == 0):
        with st.form("add_pos_form"):
            p_symbol = st.selectbox("Ticker", ALL_NSE_STOCKS, index=0)
            
            # Dynamically auto-fill price and calculated SL if available
            with st.spinner("Fetching live metrics for auto-fill..."):
                auto_data = fetch_batch_data((p_symbol,), period, timeframe)
                if p_symbol in auto_data:
                    default_buy = float(auto_data[p_symbol]['Close'].iloc[-1])
                    default_ema50 = float(auto_data[p_symbol]['EMA_50'].iloc[-1])
                    default_swing = float(auto_data[p_symbol]['Low'].tail(5).min())
                    default_sl = min(default_swing, default_ema50 * 0.995)
                else:
                    default_buy = 1000.0
                    default_sl = 970.0

            c1, c2 = st.columns(2)
            p_price = c1.number_input("Buy Price (₹)", min_value=1.0, value=round(default_buy, 2), step=1.0)
            p_qty = c2.number_input("Quantity", min_value=1, value=10, step=1)
            p_sl = st.number_input("Initial SL Price (₹)", min_value=1.0, value=round(default_sl, 2), step=1.0)
            
            if st.form_submit_button("Add Position", use_container_width=True):
                new_entry = {
                    "Ticker": p_symbol, 
                    "Buy_Price": float(p_price), 
                    "Qty": int(p_qty), 
                    "Initial_SL": float(p_sl)
                }
                st.session_state.positions.append(new_entry)
                save_positions(st.session_state.positions)
                st.toast(f"Added position for {p_symbol}!")
                st.rerun()

    # Display active positions
    if len(st.session_state.positions) == 0:
        st.info("💡 No active positions found. Use the 'Add New Position' form above to track your open trades.")
    else:
        pos_tickers = tuple(p["Ticker"] for p in st.session_state.positions)
        pos_data_dict = fetch_batch_data(pos_tickers, period, timeframe)

        for idx, pos in enumerate(st.session_state.positions):
            if pos["Ticker"] in pos_data_dict:
                df_p = pos_data_dict[pos["Ticker"]]
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
                    rec = "⚠️ TRAIL SL BROKEN (Exit)"
                elif curr_price > pos["Buy_Price"] and ema10 > ema20:
                    rec = "🔥 RIDE THE RALLY" if pnl_pct >= 5.0 else "🟢 HOLD & RIDE"
                else:
                    rec = "🟡 HOLD"

                with st.container(border=True):
                    r1_c1, r1_c2 = st.columns([2, 1])
                    r1_c1.markdown(f"### {pos['Ticker']}")
                    if pnl >= 0:
                        r1_c2.success(f"₹{pnl:+.2f} ({pnl_pct:+.1f}%)")
                    else:
                        r1_c2.error(f"₹{pnl:+.2f} ({pnl_pct:+.1f}%)")
                    
                    r2_c1, r2_c2 = st.columns(2)
                    r2_c1.write(f"**Live:** ₹{curr_price:.2f}\n**Qty:** {pos['Qty']}")
                    r2_c2.write(f"**TSL:** ₹{active_tsl:.2f}\n**Buf:** {tsl_dist:.1f}%")
                    
                    st.caption(f"Status: **{rec}**")
                    if st.button("门 Exit Position", key=f"exit_{idx}", type="primary", use_container_width=True):
                        st.session_state.positions.pop(idx)
                        save_positions(st.session_state.positions)
                        st.toast(f"Exited {pos['Ticker']}!")
                        st.rerun()

        # Dynamic Position Chart Inspector
        st.divider()
        st.subheader("📉 Trailing SL Chart Inspector")
        active_tickers = [p["Ticker"] for p in st.session_state.positions]
        
        pos_select = st.selectbox("Select Active Position:", active_tickers, index=0)
        selected_pos_data = next((p for p in st.session_state.positions if p["Ticker"] == pos_select), None)
        
        if selected_pos_data and pos_select in pos_data_dict:
            df_pos_chart = pos_data_dict[pos_select]
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
                title=f"{pos_select} — Trailing Stop Loss Chart",
                yaxis_title="Price (INR)",
                xaxis_rangeslider_visible=False,
                template="plotly_dark",
                height=420,
                margin=dict(l=10, r=10, t=35, b=10)
            )
            st.plotly_chart(fig_p, use_container_width=True, config={'responsive': True})

        if st.button("🗑️ Clear All Positions", use_container_width=True):
            st.session_state.positions = []
            save_positions([])
            st.toast("Cleared all open positions!")
            st.rerun()