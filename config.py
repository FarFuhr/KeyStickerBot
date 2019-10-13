# encoding: utf-8
import os
import logging
import distutils.util as du

DEBUG = bool(du.strtobool(os.environ.get('DEBUG', 'False') or 'True'))
BOT_TOKEN = os.environ.get('DEBUG_TOKEN') if DEBUG else os.environ.get('PRODUCTION_TOKEN')

DATABASE_CREDENTIALS = {
    'host': os.environ['DB_HOST'],
    'port': os.environ['DB_PORT'],
    'user': os.environ['DB_USER'],
    'database': os.environ.get('DB_DATABASE', 'postgres'),
    'password': os.environ['DB_PASSWORD'],
}
DATABASE_SCHEMA = os.environ.get('DB_SCHEMA')
if DEBUG:
    DATABASE_SCHEMA += '_debug'

QUERY_CACHE_TIME = 1 if DEBUG else 300  # 300 is a default value, referring to docs

logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
_logger = logging.getLogger(__name__)

_logger.info(f'\n\nDebug mode: {DEBUG}\n\n')

