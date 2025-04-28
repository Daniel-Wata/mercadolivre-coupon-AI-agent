import re
import asyncio
import asyncpg
import aiohttp
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram API credentials
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Create sessions directory if it doesn't exist
os.makedirs("telegram_bots/sessions", exist_ok=True)
SESSION = "telegram_bots/sessions/wishlist_session"

# Group or chat where the bot will listen
GROUP = int(os.getenv("WISHLIST_GROUP_ID"))

# Database connection parameters
DB_USER = os.getenv("DATABASE_USER", "postgres")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "postgres")
DB_NAME = os.getenv("DATABASE_NAME", "telegram_bot")
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "5432")

# Create connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Pattern to match Mercado Livre URLs
ML_PATTERN = re.compile(r'https?://[a-zA-Z0-9.-]+mercadoli[v|b]re\.[a-zA-Z0-9.]+/[^\s]+')

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")  # Add your bot token to .env file

class WishlistBot:
    def __init__(self):
        self.client = TelegramClient(SESSION, API_ID, API_HASH)
        self.db_pool = None
        
    async def init_db(self):
        self.db_pool = await asyncpg.create_pool(DATABASE_URL)
        
    async def extract_ml_info(self, url):
        """Extract title and price from Mercado Livre URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Extract title and price (adjust selectors as needed)
                        title_elem = soup.select_one('h1.ui-pdp-title')
                        price_elem = soup.select_one('span.andes-money-amount__fraction')
                        
                        title = title_elem.text.strip() if title_elem else 'Unknown Title'
                        price = price_elem.text.strip() if price_elem else '0'
                        
                        try:
                            price = float(price.replace('.', '').replace(',', '.'))
                        except ValueError:
                            price = 0.0
                            
                        return title, price
                        
        except Exception as e:
            print(f"Error extracting info: {e}")
            
        return 'Unknown Title', 0.0
        
    async def add_to_wishlist(self, url, sender_id):
        """Add an item to the wishlist"""
        title, price = await self.extract_ml_info(url)
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO wishlist (url, title, price, added_by)
                VALUES ($1, $2, $3, $4)
                ''',
                url, title, price, sender_id
            )
        
        return title, price
        
    async def list_wishlist(self):
        """List all items in the wishlist"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch('SELECT id, title, url, price FROM wishlist ORDER BY added_at DESC')
            
        if not rows:
            return "Sua lista de desejos está vazia."
            
        result = "📋 Sua Lista de Desejos:\n\n"
        for row in rows:
            result += f"**ID:** {row['id']}\n[{row['title']}]({row['url']})\n Preço: R${row['price']:.2f}\n\n"
            
        return result
        
    async def delete_from_wishlist(self, item_id):
        """Delete an item from the wishlist"""
        try:
            item_id = int(item_id)
        except ValueError:
            return "Formato de ID inválido. Por favor, use um número."
            
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM wishlist WHERE id = $1',
                item_id
            )
            
        if result and result.split()[-1] != '0':
            return f"✅ Item {item_id} foi removido da sua lista de desejos."
        else:
            return f"❌ Item com ID {item_id} não encontrado na sua lista de desejos."
            
    async def setup_handlers(self):
        @self.client.on(events.NewMessage(chats=GROUP, pattern=ML_PATTERN))
        async def on_mercadolivre_url(event):
            sender_id = event.sender_id
            url = ML_PATTERN.search(event.text).group(0)
            
            title, price = await self.add_to_wishlist(url, sender_id)
            
            await event.reply(f"✅ Adicionado à sua lista de desejos:\n{title}\nPreço: R${price:.2f}")
            
        @self.client.on(events.NewMessage(chats=GROUP, pattern=r'^/list$'))
        async def on_list_command(event):
            wishlist = await self.list_wishlist()
            await event.reply(wishlist, parse_mode="Markdown")
            
        @self.client.on(events.NewMessage(chats=GROUP, pattern=r'^/delete\s+(\d+)$'))
        async def on_delete_command(event):
            item_id = event.pattern_match.group(1)
            result = await self.delete_from_wishlist(item_id)
            await event.reply(result)
        
        @self.client.on(events.NewMessage(chats=GROUP, pattern=r'^/help$'))
        async def on_help_command(event):
            help_text = """
            Comandos disponíveis:
            /help - Mostrar esta mensagem de ajuda
            /list - Mostrar sua lista de desejos
            /delete [number] - Remover um item da sua lista de desejos
            """
            await event.reply(help_text)
            
    async def start(self):
        await self.init_db()
        await self.setup_handlers()
        
        await self.client.start(bot_token=bot_token)
        await self.client.run_until_disconnected()


async def run_telethon_bot():
    """Run the Telethon-based bot for group monitoring"""
    bot = WishlistBot()
    await bot.start()


if __name__ == '__main__':
    import sys
    import threading
    
    # Run only the Telethon bot
    asyncio.run(run_telethon_bot()) 