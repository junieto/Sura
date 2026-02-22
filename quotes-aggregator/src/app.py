import os
import uuid
import logging
import json
import time
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional

import requests
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from prometheus_flask_exporter import PrometheusMetrics
import redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import circuitbreaker

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
app.config.from_pyfile('config.py')

# Metrics
metrics = PrometheusMetrics(app, path='/metrics')
metrics.info('quotes_aggregator', 'Quotes Aggregator Service', version='1.0.0')

# Redis for caching and idempotency
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True
)

# Setup logging
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(g, 'request_id', 'no-request-id')
        return True

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - request_id=%(request_id)s'
)

# Add filter to all handlers
logger = logging.getLogger(__name__)
for handler in logger.root.handlers:
    handler.addFilter(RequestIdFilter())

# Custom request ID middleware
@app.before_request
def before_request():
    g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    g.start_time = time.time()
    logger.info(f'Request started - Path: {request.path} - Method: {request.method}')

@app.after_request
def after_request(response):
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        logger.info(f'Request completed - Status: {response.status_code} - Duration: {duration:.3f}s')
        
        # Add request ID to response headers
        if hasattr(g, 'request_id'):
            response.headers['X-Request-ID'] = g.request_id
    
    return response

# Quote sources configuration
QUOTE_SOURCES = [
    {
        'name': 'primary',
        'url': os.getenv('PRIMARY_QUOTE_URL', 'https://api.quotable.io/random'),
        'priority': 1,
        'timeout': int(os.getenv('REQUEST_TIMEOUT', 2))
    },
    {
        'name': 'secondary',
        'url': os.getenv('SECONDARY_QUOTE_URL', 'https://api.quotable.io/random'),
        'priority': 2,
        'timeout': int(os.getenv('REQUEST_TIMEOUT', 3))
    }
]

# Resilience patterns
class QuoteCircuitBreaker(circuitbreaker.CircuitBreaker):
    """Circuit breaker for quote API calls"""
    FAILURE_THRESHOLD = 3
    RECOVERY_TIMEOUT = 30
    EXPECTED_EXCEPTION = requests.RequestException

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.RequestException)
)
def call_quote_api(source):
    """Call external quote API with retry logic"""
    try:
        logger.info(f"Calling quote API: {source['name']}")
        response = requests.get(
            source['url'],
            timeout=source['timeout'],
            headers={'User-Agent': 'QuotesAggregator/1.0'}
        )
        response.raise_for_status()
        logger.info(f"Successfully got response from {source['name']}")
        return response.json()
    except requests.Timeout:
        logger.warning(f"Timeout calling {source['name']}")
        raise
    except requests.RequestException as e:
        logger.error(f"Error calling {source['name']}: {str(e)}")
        raise

@QuoteCircuitBreaker
def get_quote_from_source(source):
    """Get quote from a single source with circuit breaker"""
    return call_quote_api(source)

def aggregate_quotes():
    """Aggregate quotes from multiple sources with fallback"""
    results = []
    
    # Try sources in priority order
    for source in sorted(QUOTE_SOURCES, key=lambda x: x['priority']):
        try:
            logger.info(f"Trying source: {source['name']}")
            quote_data = get_quote_from_source(source)
            
            # Transform to standard format
            quote = {
                'id': str(uuid.uuid4()),
                'content': quote_data.get('content', quote_data.get('quote', 'No content available')),
                'author': quote_data.get('author', 'Unknown'),
                'source': source['name'],
                'retrieved_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            results.append(quote)
            logger.info(f"Successfully got quote from {source['name']}")
            
            # If we have enough quotes, break
            if len(results) >= 2:
                break
                
        except Exception as e:
            logger.error(f"Failed to get quote from {source['name']}: {str(e)}")
            continue
    
    return results

# API Endpoints
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'request_id': getattr(g, 'request_id', '')
    }), 200

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness probe"""
    # Check Redis connection
    redis_ok = False
    try:
        redis_client.ping()
        redis_ok = True
    except Exception as e:
        logger.error(f"Redis connection failed: {str(e)}")
    
    status_code = 200 if redis_ok else 503
    
    return jsonify({
        'status': 'ready' if redis_ok else 'not_ready',
        'redis': 'connected' if redis_ok else 'disconnected',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), status_code

@app.route('/api/v1/quotes', methods=['POST'])
@metrics.counter('quotes_created', 'Number of quotes created')
@metrics.timer('quote_creation_duration', 'Quote creation duration')
def create_quote():
    """Create a new quote with idempotency"""
    
    # Get idempotency key
    idempotency_key = request.headers.get('Idempotency-Key')
    if not idempotency_key:
        return jsonify({
            'error': 'Idempotency-Key header is required',
            'code': 'MISSING_IDEMPOTENCY_KEY',
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Validate idempotency key format (basic UUID check)
    try:
        uuid.UUID(idempotency_key)
    except ValueError:
        return jsonify({
            'error': 'Idempotency-Key must be a valid UUID',
            'code': 'INVALID_IDEMPOTENCY_KEY',
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Check if we've seen this key before
    cached_response = redis_client.get(f"idempotency:{idempotency_key}")
    if cached_response:
        logger.info(f"Returning cached response for key: {idempotency_key}")
        return jsonify(json.loads(cached_response)), 200
    
    # Validate request body
    if not request.is_json:
        return jsonify({
            'error': 'Content-Type must be application/json',
            'code': 'INVALID_CONTENT_TYPE',
            'request_id': getattr(g, 'request_id', '')
        }), 415
    
    data = request.get_json()
    if not data:
        return jsonify({
            'error': 'Request body is required',
            'code': 'MISSING_BODY',
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Validate required fields
    required_fields = ['content', 'author']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'error': f'Missing required field: {field}',
                'code': 'MISSING_FIELD',
                'field': field,
                'request_id': getattr(g, 'request_id', '')
            }), 400
    
    # Validate content length
    if len(data['content']) < 3 or len(data['content']) > 500:
        return jsonify({
            'error': 'Content must be between 3 and 500 characters',
            'code': 'INVALID_CONTENT_LENGTH',
            'current_length': len(data['content']),
            'min_length': 3,
            'max_length': 500,
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Validate author length
    if len(data['author']) < 2 or len(data['author']) > 100:
        return jsonify({
            'error': 'Author must be between 2 and 100 characters',
            'code': 'INVALID_AUTHOR_LENGTH',
            'current_length': len(data['author']),
            'min_length': 2,
            'max_length': 100,
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Validate tags if provided
    if 'tags' in data:
        if not isinstance(data['tags'], list):
            return jsonify({
                'error': 'Tags must be an array',
                'code': 'INVALID_TAGS_TYPE',
                'request_id': getattr(g, 'request_id', '')
            }), 400
        
        if len(data['tags']) > 10:
            return jsonify({
                'error': 'Maximum 10 tags allowed',
                'code': 'TOO_MANY_TAGS',
                'request_id': getattr(g, 'request_id', '')
            }), 400
        
        for tag in data['tags']:
            if not isinstance(tag, str) or len(tag) < 2 or len(tag) > 30:
                return jsonify({
                    'error': 'Tags must be strings between 2 and 30 characters',
                    'code': 'INVALID_TAG',
                    'request_id': getattr(g, 'request_id', '')
                }), 400
    
    # Validate category if provided
    valid_categories = ['inspiration', 'wisdom', 'success', 'love', 'life', 'business', 'technology']
    if 'category' in data and data['category'] not in valid_categories:
        return jsonify({
            'error': f'Category must be one of: {", ".join(valid_categories)}',
            'code': 'INVALID_CATEGORY',
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Validate language if provided
    if 'language' in data and (not isinstance(data['language'], str) or len(data['language']) != 2):
        return jsonify({
            'error': 'Language must be a 2-letter ISO code',
            'code': 'INVALID_LANGUAGE',
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Create quote
    quote = {
        'id': str(uuid.uuid4()),
        'content': data['content'],
        'author': data['author'],
        'category': data.get('category', 'general'),
        'tags': data.get('tags', []),
        'language': data.get('language', 'en'),
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'request_id': getattr(g, 'request_id', '')
    }
    
    # Cache for idempotency (24 hours)
    redis_client.setex(
        f"idempotency:{idempotency_key}",
        86400,  # 24 hours
        json.dumps(quote)
    )
    
    # Cache the quote itself (1 hour)
    redis_client.setex(
        f"quote:{quote['id']}",
        3600,  # 1 hour
        json.dumps(quote)
    )
    
    logger.info(f"Created quote: {quote['id']}")
    
    response = jsonify(quote)
    response.status_code = 201
    response.headers['Location'] = f"/api/v1/quotes/{quote['id']}"
    response.headers['Idempotency-Key-Status'] = 'CREATED'
    
    return response

@app.route('/api/v1/quotes/aggregate', methods=['GET'])
@metrics.counter('quotes_aggregated', 'Number of quote aggregations')
def get_aggregated_quotes():
    """Get aggregated quotes from multiple sources"""
    
    # Try to get from cache first
    try:
        cached = redis_client.get('aggregated_quotes')
        if cached:
            logger.info("Returning cached aggregated quotes")
            return jsonify(json.loads(cached)), 200
    except Exception as e:
        logger.error(f"Redis cache error: {str(e)}")
    
    # Aggregate quotes
    quotes = aggregate_quotes()
    
    if not quotes:
        return jsonify({
            'error': 'No quotes available from any source',
            'code': 'NO_QUOTES_AVAILABLE',
            'request_id': getattr(g, 'request_id', '')
        }), 503
    
    result = {
        'quotes': quotes,
        'count': len(quotes),
        'sources': [q['source'] for q in quotes],
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    # Cache for 5 minutes
    try:
        redis_client.setex('aggregated_quotes', 300, json.dumps(result))
    except Exception as e:
        logger.error(f"Failed to cache aggregated quotes: {str(e)}")
    
    return jsonify(result), 200

@app.route('/api/v1/quotes/<quote_id>', methods=['GET'])
def get_quote(quote_id):
    """Get a specific quote by ID"""
    
    # Validate UUID format
    try:
        uuid.UUID(quote_id)
    except ValueError:
        return jsonify({
            'error': 'Invalid quote ID format',
            'code': 'INVALID_QUOTE_ID',
            'request_id': getattr(g, 'request_id', '')
        }), 400
    
    # Try cache first
    try:
        cached = redis_client.get(f"quote:{quote_id}")
        if cached:
            logger.info(f"Returning cached quote: {quote_id}")
            return jsonify(json.loads(cached)), 200
    except Exception as e:
        logger.error(f"Redis cache error: {str(e)}")
    
    return jsonify({
        'error': 'Quote not found',
        'code': 'QUOTE_NOT_FOUND',
        'request_id': getattr(g, 'request_id', '')
    }), 404

@app.route('/api/v1/quotes', methods=['GET'])
def list_quotes():
    """List recent quotes (simplified - in production would use database)"""
    return jsonify({
        'message': 'This endpoint would return paginated quotes from database',
        'note': 'This is a simplified version - implement database for production',
        'request_id': getattr(g, 'request_id', '')
    }), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Not found',
        'code': 'NOT_FOUND',
        'request_id': getattr(g, 'request_id', str(uuid.uuid4()))
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        'error': 'Internal server error',
        'code': 'INTERNAL_ERROR',
        'request_id': getattr(g, 'request_id', str(uuid.uuid4()))
    }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)