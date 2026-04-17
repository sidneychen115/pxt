import logging
import aiosmtplib
from email.message import EmailMessage
from src.core.config import settings
from src.signals.notifiers.base import BaseNotifier
from src.core.models import TradeSignalRecord

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    async def send(self, signal: TradeSignalRecord, instrument_symbol: str) -> bool:
        msg = EmailMessage()
        msg["From"] = settings.smtp_user
        msg["To"] = settings.notify_email
        msg["Subject"] = f"[PXT] {signal.direction.upper()} Signal - {instrument_symbol}"
        direction_emoji = "🟢" if signal.direction == "buy" else "🔴"
        msg.set_content(f"""{direction_emoji} Trade Signal Generated

Symbol:     {instrument_symbol}
Direction:  {signal.direction.upper()}
Order Type: {signal.order_type}
Quantity:   {signal.quantity or 'Not specified'}
Limit:      {signal.limit_price or 'N/A'}
Stop:       {signal.stop_price or 'N/A'}
Confidence: {float(signal.confidence or 0):.0%}
Strategy:   {signal.strategy_id}
Time:       {signal.signal_time}

Reasoning:
{signal.reasoning or 'No reasoning provided.'}

---
This is an automated notification from PXT Trading System.
Do NOT act on this without your own due diligence.
""")
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
            return True
        except Exception:
            logger.exception("Email send failed")
            return False
