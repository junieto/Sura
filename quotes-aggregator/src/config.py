import os

# Flask settings
DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
TESTING = False
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Redis settings
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = 0
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# API Sources
PRIMARY_QUOTE_URL = os.getenv('PRIMARY_QUOTE_URL', 'https://api.quotable.io/random')
SECONDARY_QUOTE_URL = os.getenv('SECONDARY_QUOTE_URL', 'https://api.quotable.io/random')

# Timeouts
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 5))
CONNECT_TIMEOUT = int(os.getenv('CONNECT_TIMEOUT', 3))

# Rate limiting
RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true'
REQUESTS_PER_SECOND = int(os.getenv('REQUESTS_PER_SECOND', 10))
RATE_LIMIT_BURST = int(os.getenv('RATE_LIMIT_BURST', 20))

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = os.getenv('LOG_FORMAT', 'json')  # json or text

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv('CIRCUIT_BREAKER_FAILURE_THRESHOLD', 3))
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(os.getenv('CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 30))

# Retry settings
RETRY_MAX_ATTEMPTS = int(os.getenv('RETRY_MAX_ATTEMPTS', 3))
RETRY_INITIAL_DELAY = int(os.getenv('RETRY_INITIAL_DELAY', 1))
RETRY_MAX_DELAY = int(os.getenv('RETRY_MAX_DELAY', 10))

# Cache TTLs (in seconds)
CACHE_QUOTE_TTL = int(os.getenv('CACHE_QUOTE_TTL', 3600))  # 1 hour
CACHE_AGGREGATED_TTL = int(os.getenv('CACHE_AGGREGATED_TTL', 300))  # 5 minutes
IDEMPOTENCY_TTL = int(os.getenv('IDEMPOTENCY_TTL', 86400))  # 24 hours