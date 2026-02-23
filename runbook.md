# Quotes Aggregator API - Runbook

## 1. 📦 OVERVIEW
**Service:** Quotes Aggregator API  
**Purpose:** Create and retrieve quotes with idempotency  
**Tech Stack:** Python/Flask, Redis, Docker, Kubernetes  
**Criticality:** Medium  

## 2. 🚀 DEPLOYMENT

### Prerequisites
```bash
# Check versions
python --version  # 3.11+
docker --version   # 24.0+
kubectl version    # 1.28+
redis-cli --version # 7.0+