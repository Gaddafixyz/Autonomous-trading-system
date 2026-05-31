# Autonomous Algorithmic Trading System

A production-grade algorithmic trading bot for Binance Futures with mean reversion and momentum strategies, comprehensive risk management, and extensive backtesting capabilities.

**⚠️ WARNING**: This system trades with real money on mainnet. Use only after extensive testing and with capital you can afford to lose completely.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Trading Strategies](#trading-strategies)
- [Risk Management](#risk-management)
- [Backtesting](#backtesting)
- [Live Trading](#live-trading)
- [Deployment](#deployment)
- [Safety Checklist](#safety-checklist)
- [Troubleshooting](#troubleshooting)

---

## Features

### Trading Capabilities
- ✅ **Hybrid Strategy**: Combines mean reversion (Bollinger Bands) and momentum (EMA+ADX)
- ✅ **Paper Trading**: Test on Binance testnet without real funds
- ✅ **Live Trading**: Real order execution on Binance mainnet (with caution)
- ✅ **Leverage Support**: Up to 20x leverage on margin trading
- ✅ **Position Management**: Multiple concurrent positions with sophisticated sizing

### Risk Management
- ✅ **Kelly Criterion**: Dynamic position sizing based on win rate
- ✅ **Stop Loss & Take Profit**: Automatic exit at configured levels
- ✅ **Daily Loss Limits**: Emergency shutdown if daily loss exceeds threshold
- ✅ **Drawdown Controls**: Maximum drawdown protection
- ✅ **Circuit Breaker**: Automatic kill switch for critical errors

### Backtesting & Analysis
- ✅ **Historical Data**: Load from Binance for any date range
- ✅ **Realistic Simulation**: Includes commission, slippage, partial fills
- ✅ **Performance Metrics**: Sharpe ratio, max drawdown, win rate, profit factor
- ✅ **Trade Journal**: Detailed record of every trade with entry/exit reasons

### Infrastructure
- ✅ **Async Architecture**: Non-blocking I/O for efficient resource usage
- ✅ **WebSocket Streams**: Real-time order and market data updates
- ✅ **Professional Logging**: JSON logs + colored console output
- ✅ **Database Storage**: SQLite persistence for trades and backups
- ✅ **Systemd Integration**: Run as background service on Linux

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      PAPER TRADER / LIVE TRADER                 │
│                    (Main trading loop, risk checks)              │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                    ┌─────────┼─────────┐
                    │         │         │
         ┌──────────▼──┐  ┌──▼────────┐│  ┌────────────────┐
         │  STRATEGIES  │  │  RISK MGT │   │   EXECUTION    │
         │              │  │           │   │                │
         │ • MeanRev    │  │ • Position│   │ • Order Mgmt   │
         │ • Momentum   │  │ • Portfolio   │ • Fill Monitor │
         │ • Hybrid     │  │ • Kelly   │   │ • Persistence │
         └──────────────┘  └───────────┘   └────────────────┘
                    ▲              ▲              ▲
                    │              │              │
         ┌──────────▼──────────────┴──────────────┼────────────┐
         │                    API LAYER                        │
         │                                                      │
         │  ┌──────────────┐    ┌──────────────┐              │
         │  │ REST Client  │    │  WebSocket   │              │
         │  │              │    │  Manager     │              │
         │  │ • Account    │    │              │              │
         │  │ • Orders     │    │ • Klines     │              │
         │  │ • Positions  │    │ • Trades     │              │
         │  │ • Klines     │    │ • User Data  │              │
         │  └──────────────┘    └──────────────┘              │
         └─────────────────────────────────────────────────────┘
                          ▲
                          │
                ┌─────────┴──────────┐
                │   BINANCE API      │
                │   (Testnet/Live)   │
                └────────────────────┘
```

### Core Modules

| Module | Purpose | Key Classes |
|--------|---------|------------|
| `core/` | Shared types, config, utils | Config, Candle, Signal, Trade |
| `api/` | Binance connectivity | BinanceClient, WebSocketManager |
| `strategies/` | Trading logic | HybridStrategy, MeanReversionStrategy |
| `risk_management/` | Position sizing & limits | PositionManager, KellySizing, PortfolioRisk |
| `execution/` | Order management | ExecutionEngine, FillMonitor, OrderManager |
| `backtester/` | Historical simulation | BacktestEngine, DataLoader, Reporter |
| `live/` | Paper & live trading | PaperTrader, LiveTrader, Monitor |

---

## Quick Start

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.template .env
```

Edit `.env` and set:
- `BINANCE_API_KEY` and `BINANCE_API_SECRET` (from Binance account)
- `BINANCE_TESTNET=true` (for initial testing)
- Risk parameters (leverage, position size, daily loss limit)

### 3. Run Verification Tests

```bash
python verify.py      # Test core modules
python test_api.py    # Test Binance connection
python test_strategies.py  # Test trading signals
```

### 4. Backtest Strategy

```bash
python test_backtest.py
# Edit dates/parameters in the file as needed
```

### 5. Paper Trade (Testnet)

```bash
python test_live.py
# Runs for 30 seconds with simulated fills
# Check logs/ directory for results
```

### 6. (Advanced) Live Trade on Mainnet

⚠️ **ONLY after passing safety checklist below**

```bash
# Switch to mainnet in .env
BINANCE_TESTNET=false

# Start daemon
python -m live.daemon --mode paper  # Paper trading on mainnet data
# OR
python -m live.daemon --mode live   # REAL TRADING
```

---

## Configuration

### Quick Reference

```env
# Trading parameters
TRADING_SYMBOL=SOLUSDT          # Symbol to trade
TRADING_LEVERAGE=5.0            # 1-20x leverage
MAX_DAILY_LOSS_PCT=0.05         # Stop if -5% loss/day
MAX_DRAWDOWN_PCT=0.10           # Stop if -10% from peak
MAX_POSITION_PCT=0.30           # Each position ≤ 30% of account

# Strategy parameters
BB_PERIOD=20                    # Bollinger Bands period
BB_ENTRY_THRESHOLD=0.5          # Distance from lower band
EMA_FAST_PERIOD=50              # Fast EMA
EMA_SLOW_PERIOD=400             # Slow EMA
ADX_THRESHOLD=25.0              # Minimum trend strength

# Risk sizing
MIN_ORDER_QTY=0.1               # Minimum trade size (SOL)
MAX_ORDER_QTY=1000.0            # Maximum trade size
KELLY_FRACTION=0.25             # Kelly Criterion multiplier
```

See `.env.template` for detailed descriptions and all options.

---

## Trading Strategies

### Mean Reversion Strategy

**When**: Oversold conditions (price touches lower Bollinger Band)

**How**: 
1. Calculate 20-period Bollinger Bands
2. Enter when price is within 0.5σ below the lower band
3. Exit when price recovers above the middle band (SMA)

**Best for**: Range-bound markets, consolidation periods

### Momentum Strategy

**When**: Strong directional moves (trend confirmed)

**How**:
1. EMA(50) > EMA(400) = uptrend, EMA(50) < EMA(400) = downtrend
2. ADX > 25 = strong trend confirmed
3. Volume > 1.2x average = high conviction entry

**Best for**: Trending markets, breakouts

### Hybrid Strategy (Default)

**Combines both**: 60% weight to mean reversion, 40% to momentum

**Signal generation**:
- Only trades if combined confidence ≥ 0.3
- Weights signals from both strategies
- Adapts to market conditions

---

## Risk Management

### Position Sizing (Kelly Criterion)

Position size = (Win Rate × Payoff Ratio - Loss Probability) / Payoff Ratio × Kelly Fraction

**Conservative by default**: Uses 25% of full Kelly

**Example**:
- 60% win rate, $100 average win, $50 average loss
- Full Kelly = 2.5%
- Conservative Kelly (25%) = 0.625% per trade

### Stop Loss & Take Profit

Calculated by StopLossCalculator:
- **Mean Reversion**: SL at lower band, TP at middle band
- **Momentum**: SL at 2× ATR, TP at 3× ATR

### Daily Loss Limit

If daily realized loss > `MAX_DAILY_LOSS_PCT`:
1. No new positions opened
2. Existing positions allowed to exit
3. System stops trading

**Example**: `MAX_DAILY_LOSS_PCT=0.05` with $10k account = stop if -$500

### Maximum Drawdown

If peak-to-current drawdown > `MAX_DRAWDOWN_PCT`:
1. Emergency shutdown triggered
2. All positions forcefully closed
3. Manual intervention required to restart

**Example**: `MAX_DRAWDOWN_PCT=0.10` = stop if peak was $10k and current is $9k

---

## Backtesting

### Quick Backtest

```bash
python test_backtest.py
```

Loads recent data, runs backtest, prints metrics.

### Custom Backtest

```python
import asyncio
from backtester import DataLoader, BacktestEngine, Reporter
from core import Config, TimeFrame
from api import BinanceClient

async def main():
    cfg = Config()
    client = BinanceClient(cfg.binance)
    loader = DataLoader(client)

    # Load 6 months of data
    candles = await loader.load_candles(
        "SOLUSDT",
        TimeFrame.FIVE_MINUTE,
        "2024-01-01",
        "2024-06-30"
    )

    # Run backtest
    engine = BacktestEngine(initial_equity=10000)
    metrics = await engine.run(candles, "SOLUSDT", TimeFrame.FIVE_MINUTE)

    # Print results
    Reporter.print_summary(metrics)

asyncio.run(main())
```

### Interpreting Results

```
BACKTEST RESULTS
==================================================
Initial equity:  10000.00 USDT
Final equity:    12500.00 USDT
Total return:    25.00%
Sharpe ratio:    1.45
Max drawdown:    8.2%
Total trades:    47
Win rate:        63.8%
Profit factor:   2.1
Avg win:         125.00 USDT
Avg loss:        60.00 USDT
```

**Healthy backtest**: Win rate > 55%, Profit factor > 1.5, Sharpe > 1.0

---

## Live Trading

### Paper Trading (Risk-Free Testing)

```bash
# On testnet, with simulated fills
python test_live.py

# OR as daemon
python -m live.daemon --mode paper --simulate
```

**Pros**: No real money at risk, test infrastructure
**Cons**: Fills are simulated (not realistic), testnet account balance limited

### Live Trading on Mainnet

⚠️ **DANGER ZONE** - Real money trading

```bash
# Enable mainnet in .env
BINANCE_TESTNET=false
LIVE_MODE=live

# Start bot
python -m live.daemon --mode live
```

**Before doing this**:
1. Complete entire safety checklist below
2. Start with tiny position size (0.01 SOL)
3. Monitor actively for first week
4. Have manual kill switch ready (Binance app for emergency close)

### Monitoring

Watch logs in real-time:

```bash
# All logs
tail -f logs/app.log

# Trades only
tail -f logs/trades.log

# Errors only
tail -f logs/app.log | grep ERROR
```

---

## Deployment

### Systemd Service (Linux)

1. Edit `trading_bot.service`:
   ```ini
   User=your_username
   WorkingDirectory=/home/your_username/trading_system
   Environment="PATH=/home/your_username/trading_system/venv/bin"
   ```

2. Install service:
   ```bash
   sudo cp trading_bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable trading_bot  # Auto-start on reboot
   sudo systemctl start trading_bot
   ```

3. Monitor:
   ```bash
   sudo systemctl status trading_bot
   sudo journalctl -u trading_bot -f  # Live logs
   ```

### Docker (Coming Soon)

Build and run in container:
```bash
docker build -t trading-bot .
docker run --env-file .env trading-bot
```

---

## Safety Checklist

**Before live trading, verify ALL items**:

### Code Review
- [ ] Someone else reviewed your configuration
- [ ] Backtest shows positive returns over 6+ months
- [ ] Win rate > 50%, Sharpe ratio > 0.5

### Configuration
- [ ] API keys are correct (test with paper trading first)
- [ ] `BINANCE_TESTNET=true` initially, only switch after 2 weeks
- [ ] `MAX_DAILY_LOSS_PCT` is 2-5% (not higher)
- [ ] `MAX_DRAWDOWN_PCT` is 5-10% (not higher)
- [ ] `KELLY_FRACTION` ≤ 0.25 (conservative)
- [ ] Position size tested in backtest

### Paper Trading
- [ ] Run paper trading for 2+ weeks on testnet
- [ ] All logs reviewed, no errors
- [ ] Confirmed positions open/close correctly
- [ ] Profit metrics align with backtest

### Live Trading Prep
- [ ] Have an emergency exit plan (manual close in Binance app)
- [ ] Starting capital is amount you can afford to lose completely
- [ ] Trading hours chosen (avoid low-liquidity times)
- [ ] Monitoring system set up (email/SMS alerts for errors)
- [ ] Ready to manually stop bot if needed (kill signal)

### Day 1
- [ ] Start with 0.01 SOL positions (tiny)
- [ ] Monitor actively for first 8 hours
- [ ] Watch for errors, unexpected behavior
- [ ] Ready to stop bot immediately if issues

### First Week
- [ ] Gradually increase position size (0.01 → 0.05 → 0.1)
- [ ] Review all trades daily for unusual fills
- [ ] Monitor daily loss vs limit
- [ ] Verify circuit breaker works (intentionally trigger to test)

---

## Troubleshooting

### "API key invalid" Error

**Problem**: Authentication failed
```
AuthenticationError: API key authentication failed
```

**Solution**:
1. Check API key in `.env` is correct (copy from Binance website)
2. Verify API key has "Futures" permission
3. Check key hasn't expired or been deactivated
4. If on IP whitelist, check your IP is allowed

### "Insufficient Balance" Error

**Problem**: Not enough USDT to open position
```
OrderPlacementError: insufficient balance
```

**Solution**:
1. Check account USDT balance in Binance
2. Verify margin is enabled for futures
3. Position size calculation may be wrong → reduce `MAX_POSITION_PCT`
4. Check if funds are locked in other positions

### "No candles" / "Insufficient data" Error

**Problem**: Historical data loading failed
```
InsufficientDataError: not enough candles
```

**Solution**:
1. Check Binance API is accessible: `python test_api.py`
2. Try different date range (more recent = more data available)
3. Check firewall/proxy isn't blocking API calls
4. Rate limit hit? Wait 1 minute and retry

### "Order not filled" Timeout

**Problem**: Order placed but never filled
```
WARNING: Order 123456 not filled within 30s
```

**Solution** (normal behavior):
1. Limit order price may be too far from market
2. Reduce `timeout_seconds` or accept partial fills
3. Lower limit prices for buys, higher for sells
4. Check market spread isn't too wide

### Circuit Breaker Triggered

**Problem**: Bot stopped unexpectedly
```
CRITICAL: CIRCUIT BREAKER TRIPPED: max drawdown exceeded
```

**Solution**:
1. Check `logs/app.log` for the triggering event
2. Review `MAX_DAILY_LOSS_PCT` and `MAX_DRAWDOWN_PCT` - may be too low
3. Close any losing positions manually in Binance
4. When ready, restart bot

---

## Performance Tips

### Backtest Faster
- Use higher timeframe (5m instead of 1m = 5x faster)
- Reduce historical period (3 months instead of 1 year)
- Cache data locally (`use_cache=True`)

### Reduce API Calls
- Increase health check interval: `LIVE_HEALTH_CHECK_INTERVAL_SECONDS=30`
- Reduce WebSocket subscription frequency
- Batch multiple API calls into fewer requests

### Lower Latency
- Run bot on machine with low ping to Binance servers
- Use mainnet URLs (fstream.binance.com) not testnet
- Minimize unnecessary logging in production

---

## Contributing

Found a bug? Want to improve the system?

1. Create an issue describing the problem
2. Fork the repo
3. Fix and test thoroughly
4. Submit a pull request

**Areas needing improvement**:
- [ ] Multi-symbol trading
- [ ] Options strategies
- [ ] Machine learning signal generation
- [ ] Performance optimization
- [ ] Better UI/dashboard

---

## License

MIT License - See LICENSE file for details

---

## ⚠️ Disclaimer

**This system is provided as-is for educational purposes.** 

- Trading is risky and can result in substantial losses
- Past performance does not guarantee future results
- Use only with money you can afford to lose completely
- The authors assume no responsibility for financial losses
- Always test thoroughly before risking real capital

**Never trade without understanding the code and strategies.**

---

## Support

- 📖 See `.env.template` for detailed configuration help
- 🧪 Run `python verify.py` to test your setup
- 📊 Check `logs/` directory for detailed debugging info
- 💬 Review inline code comments for implementation details

Good luck! 🚀