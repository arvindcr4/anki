#!/bin/bash
# Environment setup for LLM flashcard generation mission

set -e

# Add cargo to PATH (required for workers)
export PATH="$HOME/.cargo/bin:$PATH"

# Verify cargo is available
if ! command -v cargo &> /dev/null; then
    echo "ERROR: cargo not found in PATH"
    echo "Please ensure Rust is installed: https://rustup.rs"
    exit 1
fi

# Fetch Rust dependencies
echo "Fetching Rust dependencies..."
cargo fetch

# Verify required environment variables are set (warning only)
if [ -z "$MINIMAX_API_KEY" ]; then
    echo "WARNING: MINIMAX_API_KEY not set. Set it to use MiniMax LLM."
fi

if [ -z "$GEMINI_API_KEY" ]; then
    echo "WARNING: GEMINI_API_KEY not set. Set it to use Gemini LLM."
fi

# Build Rust to catch any proto/gen errors early
echo "Checking Rust build..."
cargo check

echo "Environment ready. Run './check' before committing."
