#!/bin/bash

# Directory check
cd "$(dirname "$0")"

# Ensure data directory exists
mkdir -p data

echo "======================================================="
# Stop any running instances first
echo "Stopping any existing live simulator processes..."
pkill -f "src/lighter_live_simulator.py" 2>/dev/null
sleep 2

echo "Starting Live Simulators for Premium Tier in background..."

# Launch ETH
echo "  Starting ETH Live Simulator (Market ID: 0)..."
nohup python3 -u src/lighter_live_simulator.py 0 ETH premium > data/live_simulator_eth.log 2>&1 &
ETH_PID=$!

# Launch BTC
echo "  Starting BTC Live Simulator (Market ID: 1)..."
nohup python3 -u src/lighter_live_simulator.py 1 BTC premium > data/live_simulator_btc.log 2>&1 &
BTC_PID=$!

# Launch SOL
echo "  Starting SOL Live Simulator (Market ID: 2)..."
nohup python3 -u src/lighter_live_simulator.py 2 SOL premium > data/live_simulator_sol.log 2>&1 &
SOL_PID=$!

echo "======================================================="
echo "Simulators launched:"
echo "  ETH (PID: $ETH_PID) -> data/live_simulator_eth.log"
echo "  BTC (PID: $BTC_PID) -> data/live_simulator_btc.log"
echo "  SOL (PID: $SOL_PID) -> data/live_simulator_sol.log"
echo "======================================================="
ps aux | grep "src/lighter_live_simulator.py" | grep -v grep
