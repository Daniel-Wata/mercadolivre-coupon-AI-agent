import os

def get_database_url():
    # Database connection parameters
    DB_USER = os.getenv("DATABASE_USER", "postgres")
    DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "postgres")
    DB_NAME = os.getenv("DATABASE_NAME", "telegram_bot")
    DB_HOST = os.getenv("DATABASE_HOST", "localhost")
    DB_PORT = os.getenv("DATABASE_PORT", "5432")

    # Create connection string
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}" 