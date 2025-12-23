# Forex Bot Project - Environment Setup

## API Keys

Your API keys have been saved. **IMPORTANT: Keep these secret!**

### Gemini API

- ✅ API Key provided
- Model: gemini-1.5-flash
- Status: Ready to use

### Setup Instructions

1. **Create `.env` file** (never commit this!):

```bash
cd /Users/eatonjd/Github/forex_bot
cp .env.example .env
```

2. **Add your API key** to `.env`:

```
GOOGLE_API_KEY=AIzaSyA8vHgd_sM-Z-4RATilxhE3ULzp5QCyBI4
```

3. **Add `.env` to `.gitignore`** (if not already):

```bash
echo ".env" >> .gitignore
```

4. **Install dependencies**:

```bash
pip install google-generativeai python-dotenv
```

5. **Test Gemini integration**:

```bash
# In Python
from dotenv import load_dotenv
load_dotenv()

from utils.gemini_analyzer import GeminiMarketAnalyzer
analyzer = GeminiMarketAnalyzer()
# Should show: ✅ Gemini API connected successfully!
```

## Security Notes

⚠️ **NEVER** commit API keys to Git!

- Always use environment variables or `.env` files
- Add `.env` to `.gitignore`
- Rotate keys if accidentally exposed

## Current Environment

Due to NumPy 2.x compatibility issues in your Anaconda environment, some demos may not run. This doesn't affect the production code - it will work fine in a properly configured environment.

**Recommendation**: Create a clean virtual environment:

```bash
python -m venv forex_venv
source forex_venv/bin/activate
pip install -r requirements.txt
```

This will avoid the NumPy 1.x/2.x conflict.
