# pip install telethon
from telethon import TelegramClient, events, types
from agent.sales_evaluation_agent import run_workflow
import os
from dotenv import load_dotenv
import asyncio
import sys
import psycopg2
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np

# Load environment variables
load_dotenv()

# Use your personal account credentials for the listener
api_id = os.getenv("API_ID")           # from https://my.telegram.org
api_hash = os.getenv("API_HASH")

# Create sessions directory if it doesn't exist
os.makedirs("telegram_bots/sessions", exist_ok=True)
session = "telegram_bots/sessions/user_session"

# Use your bot token for the sender
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")  # Add your bot token to .env file

# Replace this with the URL or ID of the sales group you want to monitor
SALES_GROUP = os.getenv("SALES_GROUP")
TEST_SALES_GROUP = os.getenv("TEST_SALES_GROUP")

test = False
if test:
    SALES_GROUP = TEST_SALES_GROUP

# Use negative chat ID for the wishlist group
WISHLIST_GROUP_ID = int(os.getenv("WISHLIST_GROUP_ID"))

# Database connection parameters
DB_USER = os.getenv("DATABASE_USER", "postgres")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "postgres")
DB_NAME = os.getenv("DATABASE_NAME", "telegram_bot")
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "5432")

# Create connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Initialize the embedding model (lazy loading - will load on first use)
embedding_model = None

def get_embedding_model():
    """Get or initialize the embedding model"""
    global embedding_model
    if embedding_model is None:
        # Load the model - this will download it if not already present
        print("Loading embedding model...")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Embedding model loaded")
    return embedding_model

def get_embedding(text):
    """Generate embedding for the given text using MiniLM"""
    try:
        if not text or text.strip() == "":
            return None
            
        # Truncate text if it's too long
        if len(text) > 5000:  # Arbitrary limit to avoid memory issues
            text = text[:5000]
            
        model = get_embedding_model()
        embedding = model.encode(text)
        
        # Convert to list for database storage
        return embedding.tolist()
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def get_db_connection():
    """Create and return a database connection"""
    conn = psycopg2.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )
    return conn

def store_message(chat_title, message_text, message_id, sender_id):
    """Store the message and its embedding in the database"""
    try:
        # Generate embedding for the message
        embedding = get_embedding(message_text)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert the message into the telegram_messages table with embedding
        if embedding:
            cursor.execute(
                """
                INSERT INTO telegram_messages (chat_title, message_text, message_id, sender_id, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (chat_title, message_text, message_id, sender_id, embedding)
            )
        else:
            # Insert without embedding if generation failed
            cursor.execute(
                """
                INSERT INTO telegram_messages (chat_title, message_text, message_id, sender_id)
                VALUES (%s, %s, %s, %s)
                """,
                (chat_title, message_text, message_id, sender_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Message stored in database with embedding. ID: {message_id}")
    except Exception as e:
        print(f"Error storing message in database: {e}")

def search_similar_messages(query_text, limit=5):
    """Search for messages similar to the query text"""
    try:
        # Generate embedding for the query
        query_embedding = get_embedding(query_text)
        if not query_embedding:
            return []
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Search for similar messages using cosine similarity
        cursor.execute(
            """
            SELECT id, chat_title, message_text, 
                   1 - (embedding <=> %s) as similarity
            FROM telegram_messages
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (query_embedding, query_embedding, limit)
        )
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format results
        similar_messages = [
            {
                "id": row[0],
                "chat_title": row[1],
                "message_text": row[2],
                "similarity": row[3]
            }
            for row in results
        ]
        
        return similar_messages
    except Exception as e:
        print(f"Error searching similar messages: {e}")
        return []

def process_sales_message(chat_title, message_text):
    """Function that processes the received sales message"""
    print(f"Sales alert from {chat_title}: {message_text}")

async def test_bot_send_message():
    """Test function to verify bot can send messages to the group"""
    print("Starting test function...")
    
    # Start user client to get group info
    print("Starting user client...")
    user_client = TelegramClient(session, api_id, api_hash)
    await user_client.start()
    
    # Start bot client
    print("Starting bot client...")
    bot_client = TelegramClient("telegram_bots/sessions/bot_session", api_id, api_hash)
    await bot_client.start(bot_token=bot_token)
    
    # Verify bot identity
    bot_info = await bot_client.get_me()
    print(f"Bot authenticated as: @{bot_info.username} (ID: {bot_info.id})")
    
    # Try to send a message using the negative chat ID
    test_message = """

** Novos cupons disponíveis:**
• `MODABBB50`: 50% de desconto, até R$ 300, compra mínima R$ 30, para produtos selecionados

**Plano de compras recomendado:**
    🛒 **Carrinho 1: **
        - Cupom: `MODABBB50`
        - Itens: 
            - [Item1](https://www.example.com/painel-ripado)
            - [Item2](https://www.example.com/filamento-pla)
        - Subtotal: R$ 1330,00
        - Desconto: R$ 300,00

💰Total de economia: R$ 300,00
"""
    
    try:
        print(f"Sending test message to group with negative ID: {WISHLIST_GROUP_ID}")
        await bot_client.send_message(WISHLIST_GROUP_ID, test_message, parse_mode="Markdown")
        print("Test message sent successfully!")
    except Exception as e:
        print(f"Error in bot test: {e}")
        print("Trying fallback with user account...")
        try:
            await user_client.send_message(WISHLIST_GROUP_ID, f"[BOT TEST FALLBACK] {test_message}", parse_mode="Markdown")
            print("Fallback message sent via user account")
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
    
    # Disconnect clients
    await bot_client.disconnect()
    await user_client.disconnect()
    print("Test completed.")

async def main():
    # Start listener client
    print("Starting listener (personal account)")
    client_listener = TelegramClient(session, api_id, api_hash)
    await client_listener.start()
    
    print("Starting sender (bot account)")
    # Use a different session name for the bot
    client_sender = TelegramClient("telegram_bots/sessions/bot_session", api_id, api_hash)
    # Make sure we're using the bot token
    await client_sender.start(bot_token=bot_token)
    
    # Verify the bot identity
    bot_info = await client_sender.get_me()
    print(f"Bot authenticated as: @{bot_info.username} (ID: {bot_info.id})")
    
    @client_listener.on(events.NewMessage(chats=SALES_GROUP.split(",")))
    async def sales_watcher(event):
        # Store the message in the database
        store_message(
            event.chat.title, 
            event.message.text, 
            event.message.id,
            event.message.sender_id if event.message.sender else None
        )
        
        # Call the processing function with the message details
        process_sales_message(event.chat.title, event.message.text)

        # Process messages sequentially to avoid race conditions
        async with asyncio.Lock():
            data = run_workflow(event.message.text)
        print(data)
        print(data.get('deal_message'))
        # Send deal message to the wishlist group if one was generated
        if data.get('deal_message') and "no match" not in data.get('deal_message').lower():
            try:
                # Use the negative chat ID
                await client_sender.send_message(WISHLIST_GROUP_ID, data['deal_message'], parse_mode="Markdown")
                print("Message sent successfully via bot!")
            except Exception as e:
                print(f"Error sending message: {e}")
                # Fallback: try to send using the user account if bot fails
                try:
                    await client_listener.send_message(WISHLIST_GROUP_ID, 
                                                     f"[BOT FALLBACK] {data['deal_message']}", parse_mode="Markdown")
                    print("Fallback message sent via user account")
                except Exception as e2:
                    print(f"Fallback also failed: {e2}")
        else:
            print("No message will be sent.")
    
    # Keep the script running
    print("Bot is running...")
    await client_listener.run_until_disconnected()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run the test function if "test" argument is provided
        asyncio.run(test_bot_send_message())
    else:
        # Run the main function
        asyncio.run(main()) 