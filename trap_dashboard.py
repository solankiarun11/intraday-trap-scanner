import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import requests
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Intraday Liquidity Trap Terminal", layout="wide")
st.title("🚀 Intraday Institutional Trap & Telegram Scanner")
st.markdown("Live charts dekhein, liquidity traps ko analyze karein, aur ek click par Telegram par alert bhejein.")

# --- TELEGRAM AUTO-LOAD FROM SECRETS (FIXED) ---
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")

# --- SIDEBAR CONFIG ---
st.sidebar.header("⚙️ Settings & Watchlist")

# Telegram Status Indicator
st.sidebar.subheader("📱 Telegram Connection")
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    st.sidebar.success("✅ Telegram Connected & Ready!")
else:
    st.sidebar.warning("⚠️ Secrets set nahi hain. Manual details daalein:")
    TELEGRAM_BOT_TOKEN = st.sidebar.text_input("Bot Token", type="password", placeholder="123456:ABC-DEF...")
    TELEGRAM_CHAT_ID = st.sidebar.text_input("Chat ID", placeholder="123456789")

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Stock / Index Selector")
watchlist_default = ["^NSEI", "^NSEBANK", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]
selected_symbol = st.sidebar.selectbox("Choose Symbol to View Chart", watchlist_default)

period = st.sidebar.selectbox("Data Period", ["1d", "5d", "1mo"], index=1)
interval = st.sidebar.selectbox("Timeframe", ["5m", "15m", "1h"], index=1)
lookback = st.sidebar.slider("Liquidity Lookback", 10, 40, 20)
vol_multiplier = st.sidebar.slider("Volume Multiplier", 1.0, 3.0, 1.5, step=0.1)

# Telegram Alert Function
def send_telegram_alert(token, chat_id, message):
    if not token or not chat_id:
        return False, "Bot Token ya Chat ID missing hai!"
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            return True, "Alert sent successfully!"
        else:
            return False, f"Telegram Error: {res.text}"
    except Exception as e:
        return False, str(e)

# Data Analysis Function
@st.cache_data(ttl=120)
def analyze_stock(sym, per, inter, lb, vol_mult):
    df = yf.download(sym, period=per, interval=inter, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    if len(df) < lb + 5:
        return df, []

    df['Date'] = df.index.date
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TP_Vol'] = df['Typical_Price'] * df['Volume']
    df['Cum_TP_Vol'] = df.groupby('Date')['TP_Vol'].cumsum()
    df['Cum_Vol'] = df.groupby('Date')['Volume'].cumsum()
    df['VWAP'] = df['Cum_TP_Vol'] / df['Cum_Vol']
    
    df['Swing_High'] = df['High'].rolling(window=lb).max().shift(2)
    df['Swing_Low'] = df['Low'].rolling(window=lb).min().shift(2)
    df['Avg_Vol'] = df['Volume'].rolling(window=10).mean().shift(2)
    
    df['Signal'] = 0
    signals_list = []
    
    for i in range(2, len(df)):
        curr = df.iloc[i]
        high_vol = curr['Volume'] > (vol_mult * curr['Avg_Vol'])
        
        # Bullish Trap (Buy)
        if (curr['Low'] < curr['Swing_Low']) and (curr['Close'] > curr['Swing_Low']):
            if high_vol and (curr['Close'] > curr['VWAP']):
                df.iloc[i, df.columns.get_loc('Signal')] = 1
                sl = curr['Low'] - (curr['High'] * 0.001)
                tp = curr['Close'] + ((curr['Close'] - sl) * 2)
                signals_list.append((df.index[i], 'BUY', curr['Close'], sl, tp, curr['VWAP']))
                
        # Bearish Trap (Sell)
        elif (curr['High'] > curr['Swing_High']) and (curr['Close'] < curr['Swing_High']):
            if high_vol and (curr['Close'] < curr['VWAP']):
                df.iloc[i, df.columns.get_loc('Signal')] = -1
                sl = curr['High'] + (curr['High'] * 0.001)
                tp = curr['Close'] - ((sl - curr['Close']) * 2)
                signals_list.append((df.index[i], 'SELL', curr['Close'], sl, tp, curr['VWAP']))
                
    return df, signals_list

# --- MAIN DASHBOARD INTERFACE ---
data, signals = analyze_stock(selected_symbol, period, interval, lookback, vol_multiplier)

if data.empty:
    st.error(f"{selected_symbol} ke liye data load nahi ho paya.")
else:
    buy_sigs = data[data['Signal'] == 1]
    sell_sigs = data[data['Signal'] == -1]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Selected Symbol", selected_symbol)
    col2.metric("Current Price", f"₹{data['Close'].iloc[-1]:.2f}")
    col3.metric("Buy Setups Found", len(buy_sigs))
    col4.metric("Sell Setups Found", len(sell_sigs))
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Price"))
    fig.add_trace(go.Scatter(x=data.index, y=data['VWAP'], mode='lines', line=dict(color='orange', width=1.5), name='VWAP'))
    
    if not buy_sigs.empty:
        fig.add_trace(go.Scatter(x=buy_sigs.index, y=buy_sigs['Low']*0.997, mode='markers', marker=dict(symbol='triangle-up', size=14, color='#00FF00'), name='Buy Signal'))
    if not sell_sigs.empty:
        fig.add_trace(go.Scatter(x=sell_sigs.index, y=sell_sigs['High']*1.003, mode='markers', marker=dict(symbol='triangle-down', size=14, color='#FF0000'), name='Sell Signal'))
        
    fig.update_layout(height=550, xaxis_rangeslider_visible=False, template="plotly_dark", title=f"{selected_symbol} - Intraday Chart & Traps")
    st.plotly_chart(fig, use_container_width=True)
    
    # --- SCAN ALL WATCHLIST & SEND TELEGRAM BUTTON ---
    st.markdown("---")
    st.subheader("⚡ Quick Watchlist Scanner & Telegram Alert")
    
    col_btn1, col_btn2 = st.columns([2, 1])
    with col_btn1:
        scan_clicked = st.button("🔍 Scan Entire Watchlist & Send Telegram Alerts Now", use_container_width=True)
    with col_btn2:
        test_clicked = st.button("🔔 Send Test Telegram Ping", use_container_width=True)

    if test_clicked:
        success, resp = send_telegram_alert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, "✅ *Test Alert:* Aapka Intraday Trap Scanner Telegram se successfully jud gaya hai!")
        if success:
            st.success("Test message aapke Telegram par pahunch gaya hai!")
        else:
            st.error(f"Error: {resp}")

    if scan_clicked:
        found_alerts = []
        with st.spinner("Scanning all stocks in watchlist..."):
            for sym in watchlist_default:
                df_temp, sigs_temp = analyze_stock(sym, period, interval, lookback, vol_multiplier)
                if sigs_temp:
                    latest = sigs_temp[-1] # (time, type, close, sl, tp, vwap)
                    icon = "🟢" if latest[1] == "BUY" else "🔴"
                    found_alerts.append(
                        f"{icon} *{sym}* ({latest[1]})\n"
                        f"   Entry: `₹{latest[2]:.2f}` | SL: `₹{latest[3]:.2f}` | TP: `₹{latest[4]:.2f}`"
                    )
                    
        if found_alerts:
            st.success(f"{len(found_alerts)} active setups mil gaye!")
            msg = "🚨 *INTRADAY TRAP SCANNER ALERT* 🚨\n\n" + "\n\n".join(found_alerts)
            
            success, resp = send_telegram_alert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
            if success:
                st.success("✅ Telegram par alert bhej diya gaya hai!")
            else:
                st.warning(f"⚠️ Alerts mile, par Telegram error aaya: {resp}")
                
            for alert in found_alerts:
                st.markdown(alert)
        else:
            st.info("Watchlist mein abhi kisi bhi stock par active trap signal nahi mila.")
