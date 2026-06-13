"""Extract OHLCV bars from MetaTrader 5 to parquet files."""

import MetaTrader5 as mt5
import pandas as pd
from pathlib import Path

# === CONFIG ===
MT5_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\terminal64.exe"
SYMBOLS = ["XAUUSDc", "XAUUSD"]
TIMEFRAMES = {
    "M12": mt5.TIMEFRAME_M12,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "D1": mt5.TIMEFRAME_D1,
}
BARS_PER_TF = 50000  # ~2.3 years of M12
OUT_DIR = Path("mt5_data")
OUT_DIR.mkdir(exist_ok=True)

# === INIT ===
if not mt5.initialize(path=MT5_PATH):
    raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

account_info = mt5.account_info()
print(f"Connected: {account_info.login} @ {account_info.server}")

# === EXTRACT ===
for symbol in SYMBOLS:
    if not mt5.symbol_select(symbol, True):
        print(f"Symbol {symbol} not found, skipping")
        continue

    for tf_name, tf_const in TIMEFRAMES.items():
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, BARS_PER_TF)
        if rates is None:
            print(f"  {symbol} {tf_name}: no data")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df = df[["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]
        df.columns = ["open", "high", "low", "close", "volume", "spread", "real_volume"]

        out_file = OUT_DIR / f"{symbol}_{tf_name}.parquet"
        df.to_parquet(out_file, compression="zstd")
        print(f"  {symbol} {tf_name}: {len(df)} bars → {out_file}")

mt5.shutdown()
print("\nDone. Files in:", OUT_DIR.resolve())
