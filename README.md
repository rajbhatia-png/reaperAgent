# reaperAgent

CLI agent that reads instructions from `.txt` or `.md` and sends messages to one WhatsApp phone number (provided via command line).

## What it does
- Reads instructions from a file.
- Supports explicit directives:
  - `SEND: your message`
  - `WAIT: seconds`
- If no directives are present, it splits the file into paragraphs and sends each paragraph.
- Sends to exactly one target number per run (`--to`).

## API required
Use **WhatsApp Cloud API** (Meta Graph API).

You need:
- `WHATSAPP_TOKEN`: Permanent/long-lived access token with WhatsApp permissions.
- `WHATSAPP_PHONE_NUMBER_ID`: Sender phone number ID from your Meta app.

## Setup
1. Copy `.env.example` to `.env`.
2. Fill in:
   - `WHATSAPP_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
3. Use Python 3.8+.

## Run
```bash
python3 whatsapp_agent.py \
  --instructions sample_instructions.md \
  --to +14155552671
```

Dry run (no API calls):
```bash
python3 whatsapp_agent.py \
  --instructions sample_instructions.md \
  --to +14155552671 \
  --dry-run
```

## Instruction file examples

With directives:
```text
SEND: First message
WAIT: 3
SEND: Second message
```

Without directives (paragraph mode):
```text
Hello there.

How are you today?
```

## Notes
- WhatsApp Cloud API may require recipients to be in your allowed/test list while in development mode.
- Recipient number should include country code (for example `+14155552671`).
