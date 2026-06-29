"""Small text helpers shared across bot handlers."""
import html


def esc(value) -> str:
    """Escape user-controlled text before it goes into a Telegram message.

    The bot sends every message with parse_mode=HTML (see bot/main.py), so a raw
    ``&`` or ``<`` in a business/service/customer name makes Telegram reject the
    whole message ("can't parse entities") and the send silently fails. Escape
    each user-controlled VALUE (never the static template) so the markup stays
    intact. Mirrors the backend's notification_service._esc.
    """
    return html.escape(str(value if value is not None else ""), quote=False)
