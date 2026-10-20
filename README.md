# Munim Ji AI 🧾

An AI-powered accountant for Indian shopkeepers. Chat in Hindi/Hinglish (text or voice) and it records udhaar, jama, cash sales, gives balances, reports, and Excel exports.

**Mobile-app-only backend.** No WhatsApp.

## ✨ Features

- 🗣️ Voice & Text chat in Hindi/Hinglish
- 💰 Paise-accurate (integer paise, no float errors)
- 👥 Customer ledger with full history
- 🧠 AI-powered (Groq LLaMA 3.3 + Whisper)
- 📊 Excel export with balance sheet
- 🔒 JWT auth, OTP login, rate limiting, audit log
- 📈 Sentry error monitoring
- 💾 Daily encrypted S3 backups
- 🔄 Undo last entry within 5 minutes
- ⚠️ Large-amount confirmation (≥ ₹5000)
- 🎯 Name disambiguation

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Groq API key from [console.groq.com](https://console.groq.com)

### Local Setup

```bash
cp .env.example .env
# Edit .env — set GROQ_API_KEY and JWT_SECRET

python -c "import secrets; print(secrets.token_urlsafe(48))"

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

python run.py