import os
DB_CONFIG = {
    "host": os.getenv('API_DB_HOST'),
    "port": os.getenv('API_DB_PORT'),
    "database": os.getenv('API_DB_DATABASE'),
    "user": os.getenv('API_DB_USER'),
    "password": os.getenv('API_DB_PASSWORD')
    }