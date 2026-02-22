import unittest
import json
import uuid
from app import app

class TestQuotesAggregator(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
    def test_health_endpoint(self):
        response = self.app.get('/health')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'healthy')
        
    def test_create_quote_success(self):
        idempotency_key = str(uuid.uuid4())
        quote_data = {
            'content': 'Test quote content',
            'author': 'Test Author',
            'category': 'inspiration',
            'tags': ['test', 'quote']
        }
        
        response = self.app.post(
            '/api/v1/quotes',
            headers={
                'Idempotency-Key': idempotency_key,
                'Content-Type': 'application/json'
            },
            data=json.dumps(quote_data)
        )
        
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', data)

if __name__ == '__main__':
    unittest.main()
