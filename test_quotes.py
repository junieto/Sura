import unittest
import json
import uuid
from app import app

class TestQuotesAPI(unittest.TestCase):
    
    def setUp(self):
        self.app = app.test_client()
        
    def test_create_quote_success(self):
        key = str(uuid.uuid4())
        data = {"content": "Test quote", "author": "Test"}
        res = self.app.post('/api/v1/quotes', 
                           headers={'Idempotency-Key': key},
                           json=data)
        self.assertEqual(res.status_code, 201)
    
    def test_idempotency(self):
        key = str(uuid.uuid4())
        data = {"content": "Test", "author": "Test"}
        res1 = self.app.post('/api/v1/quotes', headers={'Idempotency-Key': key}, json=data)
        res2 = self.app.post('/api/v1/quotes', headers={'Idempotency-Key': key}, json=data)
        self.assertEqual(res1.json['id'], res2.json['id'])

if __name__ == '__main__':
    unittest.main()