# compare_psyll_vs_binance_full.py
# Requirements: pip install requests beautifulsoup4 rich pandas matplotlib

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import time
import csv
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box
import pandas as pd
import matplotlib.pyplot as plt

# --- configuration ---
PSYLL_TRADES_URL = "https://psyll.com/en/trading-bots/holi-bitcoin/trades"
BINANCE_SYMBOL = "BTCUSDC"
WINDOW_SECONDS = 300
PRICE_TOLERANCE = 0.01
OUTPUT_CSV = "psyll_vs_binance.csv"

console = Console()

# --- helpers ---
def format_number(n):
    if n is None:
        return ""
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    elif n >= 1e6:
        return f"{n/1e6:.2f}M"
    elif n >= 1e3:
        return f"{n/1e3:.2f}k"
    else:
        return f"{n:.2f}"

# --- fetch Psyll log ---
def fetch_psyll_trades():
    r = requests.get(PSYLL_TRADES_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    trades = []

    import re
    dt_re = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
    texts = soup.get_text(separator="\n").splitlines()
    i = 0
    while i < len(texts):
        t = texts[i].strip()
        if dt_re.match(t):
            entry_dt = t
            price = None
            for j in range(1,6):
                if i+j < len(texts) and "USDC" in texts[i+j]:
                    price_text = texts[i+j].strip()
                    m = re.search(r"([\d,]+\.\d+|\d+)", price_text.replace(",", ""))
                    if m:
                        price = float(m.group(1).replace(",", ""))
                    break
            if price:
                trades.append({"entry": entry_dt, "price": price})
            i += j+1
        else:
            i += 1
    return trades

# --- fetch Binance klines ---
def fetch_binance_klines_ms(start_ms, end_ms, symbol=BINANCE_SYMBOL):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "1h", "startTime": start_ms, "endTime": end_ms, "limit": 1000}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# --- convert datetime to UTC ms ---
def dt_to_ms_utc_warsaw(s):
    dt_warsaw = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    dt_utc = dt_warsaw - timedelta(hours=2)
    return int(dt_utc.replace(tzinfo=timezone.utc).timestamp()*1000)

# --- price matching ---
def find_best_match(psyll_price, kline_list):
    best_match = None
    min_diff = None
    for k in kline_list:
        o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
        for price in [o, h, l, c]:
            diff = abs(psyll_price - price)
            if (min_diff is None) or (diff < min_diff):
                min_diff = diff
                best_match = price
    return best_match, min_diff

# --- main comparison function ---
def compare_and_save():
    psyll_trades = fetch_psyll_trades()
    total = len(psyll_trades)
    console.print(f"[bold yellow]Found {total} trades in Psyll log[/bold yellow]\n")
    matches = 0
    rows = []

    # prepare CSV
    f = open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8')
    writer = csv.writer(f)
    writer.writerow(["Timestamp", "Psyll Price", "Binance Price", "Difference", "Percent Difference", "Match"])

    # prepare Rich table
    table = Table(show_lines=True, box=box.MINIMAL_HEAVY_HEAD)
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Psyll Price", justify="right")
    table.add_column("Binance Price", justify="right")
    table.add_column("Diff", justify="right")
    table.add_column("% Diff", justify="right")
    table.add_column("Match", justify="center")

    with Live(table, refresh_per_second=4, console=console):
        for t in psyll_trades:
            ms = dt_to_ms_utc_warsaw(t["entry"])
            start_ms = ms - WINDOW_SECONDS*1000
            end_ms = ms + WINDOW_SECONDS*1000
            try:
                klines = fetch_binance_klines_ms(start_ms, end_ms)
            except Exception as e:
                console.print(f"[red]Binance API error for {t['entry']}: {e}[/red]")
                continue

            best_price, diff = find_best_match(t["price"], klines)
            match = best_price is not None and diff/t["price"] <= PRICE_TOLERANCE
            if match:
                matches += 1

            percent_diff = (diff/t["price"]*100) if best_price else None
            match_color = "green" if match else "red"

            row = [
                t['entry'],
                format_number(t['price']),
                format_number(best_price) if best_price else "",
                format_number(diff) if diff else "",
                f"{percent_diff:.2f}%" if percent_diff else "",
                f"[{match_color}]{match}[/{match_color}]"
            ]
            rows.append(row)
            table.add_row(*row)

            # write to CSV
            writer.writerow([
                t['entry'],
                t['price'],
                best_price if best_price else '',
                diff if diff else '',
                f"{percent_diff:.2f}%" if percent_diff else '',
                match
            ])

            time.sleep(0.05)

    f.close()
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"Matched trades: [green]{matches}/{total} ({matches/total*100:.2f}%)[/green]")
    console.print(f"Unmatched trades: [red]{total-matches}/{total} ({(total-matches)/total*100:.2f}%)[/red]")
    console.print(f"Results saved to [bold]{OUTPUT_CSV}[/bold]")

# --- analyze CSV and plot ---
def analyze_csv_and_plot():
    df = pd.read_csv(OUTPUT_CSV)
    df['Difference'] = df['Difference'].astype(float)
    df['Percent Difference'] = df['Percent Difference'].str.replace('%','').astype(float)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df.sort_values('Timestamp')

    # Price trend
    plt.figure(figsize=(14,6))
    plt.plot(df['Timestamp'], df['Psyll Price'], label='Psyll Price', alpha=0.7)
    plt.plot(df['Timestamp'], df['Binance Price'], label='Binance Price', alpha=0.7)
    plt.title("BTCUSDC Price Trend: Psyll vs Binance")
    plt.xlabel("Timestamp")
    plt.ylabel("Price (USDC)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    # Histogram of percent differences
    plt.figure(figsize=(10,5))
    plt.hist(df['Percent Difference'], bins=50, color='skyblue', edgecolor='black')
    plt.title("Histogram of Percent Differences: Psyll vs Binance")
    plt.xlabel("Percent Difference (%)")
    plt.ylabel("Number of trades")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

# --- run ---
if __name__ == "__main__":
    compare_and_save()
    analyze_csv_and_plot()
