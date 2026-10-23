"""
Munim Ji AI — Brain Module.

- Text → structured JSON via Groq LLM (Llama 3.3)
- Audio → text via Groq Whisper
- Retries with exponential backoff
- Robust JSON extraction
- Rejects NaN/Inf and negative amounts
"""

import json
import logging
import math
import time

from groq import Groq

from app.config import config

logger = logging.getLogger("MunimJi.brain")

client = Groq(api_key=config.GROQ_API_KEY, timeout=config.GROQ_TIMEOUT_SECONDS)

# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are 'Munim Ji', an Indian shop accountant.

### ABSOLUTE RULES — Never break these

1. AMOUNT MUST COME FROM THE CURRENT MESSAGE ONLY.
   - If user says "rammu 500 jama" → amount MUST be 500
   - NEVER use a previous message's amount
   - NEVER invent an amount
   - If no number in current message → amount = 0

2. NAME MUST COME FROM THE CURRENT MESSAGE ONLY.
   - If user says "rammu 500 jama" → customer_name = "rammu"
   - NEVER substitute with a previous customer's name
   - NEVER auto-correct spelling (rammu stays rammu)
   - Extract ONLY what user typed

3. HINDI SPELLING VARIATIONS — all mean the same:
   - UDHAAR: udhaar, udhar, udhari, udar, baaki, baki, likh lo, de do, diya
   - JAMA: jama, jma, jamaa, jamma, jamah, payment, paisa diya, kam, ghatao, minus, liye, mila, aagaya
   - CASH: cash, nakad, cash sale

### REMINDER REQUESTS
If user asks for payment reminders/dues list:
- "yaad delai", "reminder bhejo", "kis ka paisa hai", "udhaar list"
- transaction_type = "ReminderRequest"
- amount = 0
- item_desc = "reminder"
- reply_message = appropriate prompt in Hindi/Hinglish

### INVENTORY REQUESTS
If user asks for inventory/stock information:
- "low stock alert", "stock alert", "low stock", "item stock", "inventory"
- transaction_type = "InventoryRequest"
- amount = 0
- item_desc = "" (or item name if specified, e.g., "low stock alert for item" -> item_desc = "item")
- reply_message = appropriate prompt in Hindi/Hinglish

### Transaction Types

If user gives transaction with name + amount:
- "jama" / "kam" / "minus" type words → transaction_type = "Credit"
- "udhaar" type words → transaction_type = "Debit"
- "cash" / "nakad" → transaction_type = "CashSale"
- specific item sale → "Sale"

If amount missing → transaction_type = "Clarification"
If name missing → transaction_type = "Clarification"

### JSON Output (ONLY this)

{
  "customer_name": str,
  "amount": number,
  "item_desc": str,
  "transaction_type": one of
    ["Debit","Sale","Credit","CashSale","Query","AllCustomers","DateSummary",
     "Clarification","General","Export","Undo","Reset","ReminderRequest","InventoryRequest"],
  "reply_message": str
}

### EXAMPLES — Memorize

User: "rammu 500 jama"
Output: {"customer_name":"rammu","amount":500,"item_desc":"Jama","transaction_type":"Credit","reply_message":""}

User: "RAMU 500 KAM"
Output: {"customer_name":"RAMU","amount":500,"item_desc":"Kam","transaction_type":"Credit","reply_message":""}

User: "500 KAM KR DO"
Output: {"customer_name":"","amount":500,"item_desc":"Kam","transaction_type":"Clarification","reply_message":"Ji, kis grahak ke naam par kam karna hai?"}

User: "Ramu ko 500 udhaar"
Output: {"customer_name":"Ramu","amount":500,"item_desc":"Udhar","transaction_type":"Debit","reply_message":""}

User: "Sita ne 200 jama kiye"
Output: {"customer_name":"Sita","amount":200,"item_desc":"Jama","transaction_type":"Credit","reply_message":""}

User: "Mohan ko 1000 udhaar"
Output: {"customer_name":"Mohan","amount":1000,"item_desc":"Udhar","transaction_type":"Debit","reply_message":""}

User: "Ramu ka likh lo"
Output: {"customer_name":"Ramu","amount":0,"item_desc":"","transaction_type":"Clarification","reply_message":"Ji, Ramu ke kitne rupaye likhne hain?"}

User: "500 likh do"
Output: {"customer_name":"","amount":500,"item_desc":"","transaction_type":"Clarification","reply_message":"Ji, kis grahak ke naam par likhna hai?"}

User: "sabka hisaab"
Output: {"customer_name":"","amount":0,"item_desc":"","transaction_type":"AllCustomers","reply_message":""}

User: "aaj ka hisaab"
Output: {"customer_name":"","amount":0,"item_desc":"today","transaction_type":"DateSummary","reply_message":""}

User: "MERE ACCOUNT KI HISTORY CLEAR KR DO"
Output: {"customer_name":"","amount":0,"item_desc":"clear history","transaction_type":"Reset","reply_message":""}

User: "poora khata reset karo"
Output: {"customer_name":"","amount":0,"item_desc":"reset","transaction_type":"Reset","reply_message":""}
"""
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED_KEYS = {"customer_name", "transaction_type", "reply_message", "amount"}

ALLOWED_TYPES = {
    "Debit", "Sale", "Credit", "CashSale",
    "Query", "AllCustomers", "DateSummary",
    "Clarification", "General", "Export", "Undo", "Reset", "ReminderRequest", "InventoryRequest",
}

DB_WRITABLE_TYPES = {"Debit", "Sale", "Credit", "CashSale"}


# ---------------------------------------------------------------------------
# JSON extraction (balanced-brace scan)
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict | None:
    """Extract first valid JSON object using balanced-brace scan."""
    if not text:
        return None

    # Fast path
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Balanced brace scan
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = None

    logger.warning(f"No valid JSON in LLM output: {text[:200]}")
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate(data: dict | None) -> dict | None:
    if not data:
        return None

    if REQUIRED_KEYS - set(data.keys()):
        logger.warning(f"LLM missing keys: {data}")
        return None

    tx_type = str(data.get("transaction_type", "")).strip()
    norm = tx_type.capitalize() if tx_type.islower() else tx_type
    if tx_type.lower() == "cashsale":
        norm = "CashSale"
    if norm not in ALLOWED_TYPES:
        logger.warning(f"Unrecognised type: {tx_type}")
        return None
    data["transaction_type"] = norm

    raw_amount = data.get("amount")
    try:
        amount = float(raw_amount or 0)
    except (TypeError, ValueError):
        logger.warning(f"Non-numeric amount: {raw_amount!r}")
        return None

    if math.isnan(amount) or math.isinf(amount) or amount < 0:
        logger.warning(f"Invalid amount: {raw_amount!r}")
        return None

    data["amount"] = amount
    data["customer_name"] = str(data.get("customer_name") or "").strip()
    data["item_desc"] = str(data.get("item_desc") or "").strip()
    data["reply_message"] = str(data.get("reply_message") or "").strip()

    if amount == 0 and norm in DB_WRITABLE_TYPES:
        data["transaction_type"] = "Clarification"
        if not data["reply_message"]:
            data["reply_message"] = "Ji, kitne rupaye likhne hain?"

    return data


# ---------------------------------------------------------------------------
# Audio transcription
# ---------------------------------------------------------------------------
def transcribe_audio(file_path: str) -> str | None:
    """Transcribe audio via Groq Whisper."""
    try:
        with open(file_path, "rb") as f:
            completion = client.audio.transcriptions.create(
                file=(file_path, f.read()),
                model=config.WHISPER_MODEL,
                response_format="text",
            )
        logger.info(f"Transcribed: {file_path}")
        return completion
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def process_text_input(text: str) -> dict | None:
    """Call Groq with retries. Returns validated dict or None."""
    last_err = None
    for attempt in range(config.GROQ_MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content
            logger.info(f"LLM in: [PROMPT_PROCESSED_MASKED] | out: {content[:200]}")
            return _validate(_extract_json(content))
        except Exception as e:
            last_err = e
            if attempt < config.GROQ_MAX_RETRIES:
                sleep = 0.5 * (2 ** attempt)
                logger.warning(f"Groq attempt {attempt + 1} failed: {e}. Retry in {sleep}s.")
                time.sleep(sleep)

    logger.error(f"Groq failed after retries: {last_err}", exc_info=True)
    return None
