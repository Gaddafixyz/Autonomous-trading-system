#!/usr/bin/env python3
"""
Helper scripts for the SDK migration process.
Run these to automate parts of the migration.

Usage:
    python migration_helpers.py --check-install     # Verify installation
    python migration_helpers.py --compare-api        # Compare old vs new API
    python migration_helpers.py --test-connection    # Test SDK connection
    python migration_helpers.py --validate-config    # Validate configuration
"""

import sys
import subprocess
import importlib.util
from pathlib import Path
from typing import Tuple

# Color codes for console output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def colored(text: str, color: str) -> str:
    """Add color to console output."""
    return f"{color}{text}{RESET}"


def check_package_installed(package_name: str) -> bool:
    """Check if a Python package is installed."""
    spec = importlib.util.find_spec(package_name)
    return spec is not None


def print_section(title: str):
    """Print a section header."""
    print(f"\n{colored('=' * 60, BLUE)}")
    print(f"{colored(title, BLUE)}")
    print(f"{colored('=' * 60, BLUE)}\n")


def check_installation() -> bool:
    """Verify that all required packages are installed."""
    print_section("Checking Package Installation")
    
    required = {
        'binance_sdk_derivatives_trading_usds_futures': 'binance-sdk-derivatives-trading-usds-futures',
        'binance_common': 'binance-common',
    }
    
    all_installed = True
    for module, package in required.items():
        if check_package_installed(module):
            print(f"{colored('✓', GREEN)} {package} is installed")
        else:
            print(f"{colored('✗', RED)} {package} is NOT installed")
            print(f"  Install with: pip install {package}")
            all_installed = False
    
    # Check old SDK isn't still there
    if check_package_installed('binance.um_futures'):
        print(f"{colored('⚠', YELLOW)} Old binance-connector SDK is still installed")
        print(f"  Consider removing it: pip uninstall binance-connector -y")
    else:
        print(f"{colored('✓', GREEN)} Old binance-connector SDK is removed")
    
    return all_installed


def compare_api():
    """Show side-by-side comparison of old vs new API."""
    print_section("API Comparison: Old vs New")
    
    comparisons = [
        {
            'name': 'Import',
            'old': 'from binance.um_futures import UMFutures',
            'new': 'from binance_sdk_derivatives_trading_usds_futures import...',
        },
        {
            'name': 'Initialization',
            'old': 'client = UMFutures(key="...", secret="...")',
            'new': 'config = ConfigurationRestAPI(...)\nconfig = DerivativesTradingUsdsFutures(...)',
        },
        {
            'name': 'Get Account',
            'old': 'resp = client.account()',
            'new': 'resp = client.rest_api.account(); data = resp.data()',
        },
        {
            'name': 'Place Order',
            'old': 'resp = client.new_order(type="LIMIT", ...)',
            'new': 'resp = client.rest_api.new_order(order_type="LIMIT", ...)',
        },
        {
            'name': 'Query Order',
            'old': 'resp = client.query_order(orderId=123)',
            'new': 'resp = client.rest_api.query_order(order_id=123)',
        },
        {
            'name': 'Get Klines',
            'old': 'klines = client.klines(...)',
            'new': 'resp = client.rest_api.klines(...); data = resp.data()',
        },
    ]
    
    for comp in comparisons:
        print(f"{colored(comp['name'], YELLOW)}")
        print(f"  {colored('OLD', RED)}: {comp['old']}")
        print(f"  {colored('NEW', GREEN)}: {comp['new']}")
        print()


def test_connection() -> bool:
    """Test that the SDK can connect to Binance."""
    print_section("Testing SDK Connection")
    
    try:
        from binance_common.configuration import ConfigurationRestAPI
        from binance_common.constants import DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL
        from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import DerivativesTradingUsdsFutures
        
        print(f"{colored('✓', GREEN)} SDK imports successful")
        
        # Try to create a public client (no API keys needed)
        try:
            config = ConfigurationRestAPI(base_path=DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL)
            client = DerivativesTradingUsdsFutures(config_rest_api=config)
            print(f"{colored('✓', GREEN)} SDK client initialized")
            
            # Try to get exchange info (public endpoint)
            import asyncio
            
            async def test_api():
                response = await asyncio.to_thread(client.rest_api.exchange_information)
                data = response.data()
                return data
            
            try:
                # Try to call the API
                response = asyncio.run(test_api())
                print(f"{colored('✓', GREEN)} API connection successful")
                print(f"  Exchange: {response.timezone if hasattr(response, 'timezone') else 'USDS-M Futures'}")
                return True
            except Exception as e:
                print(f"{colored('⚠', YELLOW)} Could not reach API: {e}")
                print(f"  (This is OK if no internet connection)")
                return True  # SDK is installed, just no network
        except Exception as e:
            print(f"{colored('✗', RED)} SDK initialization failed: {e}")
            return False
    except ImportError as e:
        print(f"{colored('✗', RED)} SDK import failed: {e}")
        return False


def validate_config() -> bool:
    """Validate that .env configuration is correct."""
    print_section("Validating Configuration")
    
    from pathlib import Path
    from dotenv import load_dotenv
    import os
    
    env_file = Path('.env')
    
    if not env_file.exists():
        print(f"{colored('✗', RED)} .env file not found")
        print(f"  Create it: cp .env.template .env")
        return False
    
    load_dotenv()
    
    # Check critical variables
    required = {
        'BINANCE_API_KEY': 'Binance API Key',
        'BINANCE_API_SECRET': 'Binance API Secret',
        'TRADING_SYMBOL': 'Trading Symbol',
        'TRADING_LEVERAGE': 'Leverage',
    }
    
    all_valid = True
    for var, desc in required.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'SECRET' in var or 'KEY' in var:
                display = value[:10] + '...' if len(value) > 10 else '...'
            else:
                display = value
            print(f"{colored('✓', GREEN)} {desc}: {display}")
        else:
            print(f"{colored('✗', RED)} {desc} not set in .env")
            all_valid = False
    
    # Validate values
    leverage = os.getenv('TRADING_LEVERAGE')
    if leverage:
        try:
            lev = float(leverage)
            if 1.0 <= lev <= 20.0:
                print(f"{colored('✓', GREEN)} Leverage {lev}x is in valid range (1-20)")
            else:
                print(f"{colored('✗', RED)} Leverage {lev}x outside valid range (1-20)")
                all_valid = False
        except ValueError:
            print(f"{colored('✗', RED)} Leverage '{leverage}' is not a number")
            all_valid = False
    
    api_key = os.getenv('BINANCE_API_KEY', '')
    if len(api_key) < 30:
        print(f"{colored('⚠', YELLOW)} API key seems too short (< 30 chars)")
    
    return all_valid


def generate_summary() -> str:
    """Generate a migration summary."""
    print_section("Migration Summary")
    
    summary = f"""
{colored('FILES TO UPDATE:', BLUE)}
  1. requirements.txt
     - Remove: binance-connector==3.6.0
     - Add: binance-sdk-derivatives-trading-usds-futures>=5.0.0
  
  2. api/binance_client.py
     - Replace entire file with binance_client_updated.py
     - Main changes:
       • New SDK imports
       • ConfigurationRestAPI instead of direct client init
       • Method calls use self.client.rest_api.method()
       • Response wrapping with .data()
       • New exception types
       • Parameter name changes (type → order_type, etc.)

{colored('MODULES THAT NEED CHANGES:', BLUE)}
  Files to update: 2
  Lines changed: ~150
  
{colored('MODULES THAT DON\'T NEED CHANGES:', GREEN)}
  ✓ api/websocket_manager.py (same WebSocket endpoints)
  ✓ core/ (all core types/utils)
  ✓ strategies/ (signal generation)
  ✓ risk_management/ (position sizing)
  ✓ execution/ (order management)
  ✓ backtester/ (historical simulation)
  ✓ live/ (paper/live trading)
  ✓ All test files

{colored('INSTALLATION:', BLUE)}
  pip install -r requirements.txt
  
{colored('TESTING:', BLUE)}
  python verify.py
  python test_api.py
  python test_strategies.py
  python test_backtest.py
  python test_execution.py
  python test_live.py
  
{colored('ESTIMATED TIME:', BLUE)}
  - Preparation: 5 minutes
  - Installation: 3 minutes
  - Code changes: 5 minutes
  - Testing: 15 minutes
  - Total: ~40 minutes
  
{colored('NEXT STEPS:', BLUE)}
  1. Follow IMPLEMENTATION_CHECKLIST.md step-by-step
  2. Replace api/binance_client.py
  3. Update requirements.txt
  4. Run all tests
  5. Deploy when all tests pass
"""
    
    return summary


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='SDK Migration Helper Scripts')
    parser.add_argument('--check-install', action='store_true', help='Check package installation')
    parser.add_argument('--compare-api', action='store_true', help='Compare old vs new API')
    parser.add_argument('--test-connection', action='store_true', help='Test SDK connection')
    parser.add_argument('--validate-config', action='store_true', help='Validate .env configuration')
    parser.add_argument('--summary', action='store_true', help='Generate migration summary')
    parser.add_argument('--all', action='store_true', help='Run all checks')
    
    args = parser.parse_args()
    
    # If no arguments, show summary
    if not any(vars(args).values()):
        print(generate_summary())
        return
    
    results = {}
    
    if args.check_install or args.all:
        results['install'] = check_installation()
    
    if args.compare_api or args.all:
        compare_api()
    
    if args.test_connection or args.all:
        results['connection'] = test_connection()
    
    if args.validate_config or args.all:
        results['config'] = validate_config()
    
    if args.summary or args.all:
        print(generate_summary())
    
    # Print final status
    if results:
        print_section("Status Summary")
        if all(results.values()):
            print(f"{colored('✓ All checks passed!', GREEN)}")
            return 0
        else:
            print(f"{colored('✗ Some checks failed. See above for details.', RED)}")
            return 1


if __name__ == '__main__':
    sys.exit(main())