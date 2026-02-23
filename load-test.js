import http from 'k6/http';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

export const options = {
    stages: [
        { duration: '1m', target: 50 },
        { duration: '3m', target: 100 },
        { duration: '1m', target: 0 },
    ],
};

export default function() {
    const key = uuidv4();
    const data = {
        content: "Load test quote",
        author: "k6 Tester"
    };
    
    const res = http.post('http://localhost:8080/api/v1/quotes', 
        JSON.stringify(data),
        { headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }
    );
    
    check(res, { 'status 201': (r) => r.status === 201 });
    sleep(1);
}