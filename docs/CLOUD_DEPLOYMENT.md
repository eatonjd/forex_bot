# 🚀 Google Cloud Run Deployment Guide

## 📋 Prerequisites

1. **Google Cloud Account** with billing enabled
2. **gcloud CLI** installed: <https://cloud.google.com/sdk/docs/install>
3. **OANDA API credentials** (you have these!)

---

## 🔧 Setup Steps

### 1. **Set Environment Variables**

```bash
export OANDA_API_KEY="029fd0b11f5079ccccb4ab14b5f5638b-32865d7468197e4231101be7bc6f3863"
export OANDA_ACCOUNT_ID="101-001-11289252-001"
```

### 2. **Update Project ID**

Edit `deploy_gcloud.sh` line 14:

```bash
PROJECT_ID="your-gcp-project-id"  # Change to your GCP project
```

### 3. **Deploy**

```bash
./deploy_gcloud.sh
```

This will:

- ✅ Build Docker image
- ✅ Push to Google Container Registry
- ✅ Deploy to Cloud Run
- ✅ Set environment variables
- ✅ Start trading bot 24/7

---

## 📊 Monitoring Deployed Bot

### **View Logs**

```bash
gcloud run services logs tail forex-trading-bot --region us-central1
```

### **Check Status**

Visit service URL + `/status`:

```
https://forex-trading-bot-xxxxx-uc.a.run.app/status
```

Shows:

- Account balance
- Open positions
- Bot health

### **Health Check**

```
https://forex-trading-bot-xxxxx-uc.a.run.app/
```

---

## 💰 Cost Estimate

**Cloud Run Pricing** (Free tier):

- First 2 million requests: **FREE**
- 360,000 GB-seconds: **FREE**
- 180,000 vCPU-seconds: **FREE**

**Expected Cost**: **$0-2/month** (likely free!)

Bot runs continuously but uses minimal resources.

---

## 🛑 Stop/Delete Bot

```bash
gcloud run services delete forex-trading-bot --region us-central1
```

---

## ⚙️ Configuration

### **Change Check Interval**

Edit `paper_trading_bot.py` line 26:

```python
CHECK_INTERVAL = 300  # seconds
```

### **Change Symbols**

Edit `paper_trading_bot.py` line 25:

```python
SYMBOLS = ['EUR_USD', 'GBP_USD', 'AUD_USD']  # Add more
```

### **Update Position Size**

Edit `paper_trading_bot.py` line 27:

```python
UNITS_PER_TRADE = 1000  # Increase for larger positions
```

---

## 🔐 Security Notes

1. **API Keys**: Stored as Cloud Run environment variables (secure)
2. **Practice Account**: Cannot lose real money
3. **Private Endpoint**: Only you can access service URL

---

## 🎯 Next Steps After Deployment

1. **Monitor for 1 week** - Check `/status` daily
2. **Review trades** - Login to OANDA dashboard
3. **Adjust if needed** - Redeploy with changes
4. **Go live** - Switch to live account when ready

---

## 📝 Files Created

- `Dockerfile` - Container configuration
- `deploy_gcloud.sh` - Deployment script
- `cloud_run_server.py` - Health check server
- `requirements.txt` - Python dependencies

---

**Ready to deploy? Run `./deploy_gcloud.sh`** 🚀
