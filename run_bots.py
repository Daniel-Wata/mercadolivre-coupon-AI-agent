#!/usr/bin/env python3
"""
Unified script to run both the Sales Listener and Wishlist Bot
"""
import os
import sys
import asyncio
import threading
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_sales_listener():
    """Run the sales listener bot in a separate process"""
    print("Starting Sales Listener...")
    from telegram_bots.sales_listener import main
    asyncio.run(main())

def run_wishlist_bot():
    """Run the wishlist bot in a separate process"""
    print("Starting Wishlist Bot...")
    from telegram_bots.wishlist_bot import run_telethon_bot
    asyncio.run(run_telethon_bot())

def run_test_mode():
    """Run the sales listener in test mode"""
    print("Starting Sales Listener in test mode...")
    from telegram_bots.sales_listener import test_bot_send_message
    asyncio.run(test_bot_send_message())

def main():
    """Main function to start the bots based on command line arguments"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "sales":
            run_sales_listener()
        elif sys.argv[1] == "wishlist":
            run_wishlist_bot()
        elif sys.argv[1] == "test":
            run_test_mode()
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print_usage()
    else:
        # Run both bots in separate threads
        print("Starting both bots...")
        
        # Create threads for each bot
        sales_thread = threading.Thread(target=run_sales_listener, daemon=True)
        wishlist_thread = threading.Thread(target=run_wishlist_bot, daemon=True)
        
        # Start the threads
        sales_thread.start()
        wishlist_thread.start()
        
        # Wait for both threads to complete (which they won't unless there's an error)
        try:
            while True:
                if not sales_thread.is_alive() and not wishlist_thread.is_alive():
                    print("Both bots have stopped.")
                    break
                if not sales_thread.is_alive():
                    print("Sales Listener has stopped.")
                    break
                if not wishlist_thread.is_alive():
                    print("Wishlist Bot has stopped.")
                    break
                # Sleep to prevent high CPU usage
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down bots...")
            # The threads are daemon threads, so they'll be terminated when the main thread exits

def print_usage():
    """Print usage information"""
    print("""
Usage: python run_bots.py [command]

Commands:
  (none)    - Run both bots
  sales     - Run only the Sales Listener
  wishlist  - Run only the Wishlist Bot
  test      - Run the Sales Listener in test mode
    """)

if __name__ == "__main__":
    main() 