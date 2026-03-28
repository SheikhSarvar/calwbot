"""
channel_simulator.py – Simulates chat and WhatsApp channels (OpenClaw integration).

OpenClaw is the middleware layer that:
  1. Receives incoming messages from chat/WhatsApp
  2. Classifies the intent (shopping / support / general)
  3. Routes to the RetailAgent or escalates to a human agent
  4. Formats the response for the originating channel
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from src.agent import RetailAgent

# ─── Data types ──────────────────────────────────────────────────────────────

ChannelType = Literal["chat", "whatsapp", "cli"]

@dataclass
class Message:
    role: Literal["user", "agent", "system"]
    text: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    channel: ChannelType = "cli"


@dataclass
class Session:
    session_id:   str
    channel:      ChannelType
    customer_id:  str
    messages:     list[Message] = field(default_factory=list)
    human_needed: bool = False
    history:      list[dict]   = field(default_factory=list)


# ─── Intent classifier ────────────────────────────────────────────────────────

_SUPPORT_PATTERNS = re.compile(
    r"\b(order|return|refund|exchange|tracking|shipped|deliver|invoice|receipt"
    r"|cancel|wrong size|damaged|defect)\b",
    re.IGNORECASE,
)
_SHOPPING_PATTERNS = re.compile(
    r"\b(dress|gown|outfit|wear|looking for|find|recommend|suggest|shop|buy"
    r"|purchase|size|style|occasion|under \$|under\s*\d|sale|discount)\b",
    re.IGNORECASE,
)
_ESCALATION_PATTERNS = re.compile(
    r"\b(human|agent|person|representative|speak to|talk to|manager|help me|"
    r"frustrated|angry|urgent|lawsuit|complaint|chargeback|dispute|fraud|"
    r"payment|charged|billing|address change|change address|stolen)\b",
    re.IGNORECASE,
)
_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|good morning|good evening|good afternoon|hiya|howdy)[!,. ]*$",
    re.IGNORECASE,
)


def classify_intent(text: str) -> str:
    if _GREETING_PATTERNS.match(text.strip()):
        return "greeting"
    if _ESCALATION_PATTERNS.search(text):
        return "escalation"
    if _SUPPORT_PATTERNS.search(text):
        return "support"
    if _SHOPPING_PATTERNS.search(text):
        return "shopping"
    return "general"


# ─── Channel formatter ────────────────────────────────────────────────────────

def format_for_channel(text: str, channel: ChannelType) -> str:
    """Adapt markdown-like response to channel constraints."""
    if channel == "whatsapp":
        # WhatsApp supports *bold* but not **bold**
        text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)
        # Remove markdown headers
        text = re.sub(r"^#{1,3}\s+", "", text, flags=re.MULTILINE)
        # Wrap at 60 chars for mobile readability
        lines = text.split("\n")
        wrapped = []
        for line in lines:
            if len(line) > 60 and not line.startswith("•") and not line.startswith("*"):
                wrapped.extend(textwrap.wrap(line, 60))
            else:
                wrapped.append(line)
        return "\n".join(wrapped)

    if channel == "chat":
        # Chat widget supports HTML-like rendering; keep markdown
        return text

    # CLI: plain text
    return text


# ─── OpenClaw channel simulation ─────────────────────────────────────────────

class OpenClawSimulator:
    """
    Simulates the OpenClaw middleware layer.

    In a real deployment this class would connect to:
      - A WebSocket / REST endpoint for live chat
      - The WhatsApp Business API (via Meta or Twilio)
    """

    GREETING = (
        "👗 Hi there! Welcome to our boutique.\n"
        "I'm your AI assistant and I can help you:\n"
        "  • 🛍️  Find the perfect outfit\n"
        "  • 📦  Track or manage your order\n"
        "  • 🔄  Check return & exchange eligibility\n"
        "  • ❓  Answer any questions\n\n"
        "What can I help you with today?"
    )

    ESCALATION_MSG = (
        "I understand this may be urgent. I'm connecting you to a "
        "human agent now. Someone will be with you shortly.\n\n"
        "⏱️  Estimated wait: 2–5 minutes\n"
        "📧  You'll also receive a confirmation email."
    )

    WHATSAPP_GREETING = (
        "👗 Hi! Welcome to our boutique. I'm your AI assistant.\n\n"
        "I can help with:\n"
        "• Finding outfits\n"
        "• Order tracking\n"
        "• Returns & exchanges\n\n"
        "How can I help you today?"
    )

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._agent = RetailAgent()

    def get_or_create_session(
        self, session_id: str, channel: ChannelType = "cli", customer_id: str = "guest"
    ) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(
                session_id=session_id,
                channel=channel,
                customer_id=customer_id,
            )
        return self._sessions[session_id]

    def handle_message(
        self,
        session_id: str,
        user_text: str,
        channel: ChannelType = "cli",
        customer_id: str = "guest",
        verbose: bool = True,
    ) -> str:
        """
        Process an incoming message end-to-end.

        Returns the formatted response string.
        """
        session = self.get_or_create_session(session_id, channel, customer_id)

        # Record user message
        session.messages.append(Message(role="user", text=user_text, channel=channel))

        # ── Classify intent ─────────────────────────────────────────────────
        intent = classify_intent(user_text)

        if verbose:
            print(f"\n  [OpenClaw] intent={intent} channel={channel}")

        # ── Handle escalation immediately ───────────────────────────────────
        if intent == "escalation":
            session.human_needed = True
            response = self.ESCALATION_MSG
            session.messages.append(Message(role="system", text="[ESCALATED TO HUMAN]"))
            session.messages.append(Message(role="agent", text=response))
            return format_for_channel(response, channel)

        # ── Send greeting for new session ───────────────────────────────────
        if intent == "greeting" and len(session.messages) == 1:
            greeting = (
                self.WHATSAPP_GREETING if channel == "whatsapp" else self.GREETING
            )
            session.messages.append(Message(role="agent", text=greeting, channel=channel))
            return format_for_channel(greeting, channel)

        # ── Route to AI agent ───────────────────────────────────────────────
        response = self._agent.respond(
            user_message=user_text,
            history=session.history,
        )

        # Update conversation history for multi-turn context
        session.history.append({"role": "user",  "parts": [user_text]})
        session.history.append({"role": "model", "parts": [response]})

        session.messages.append(Message(role="agent", text=response, channel=channel))
        return format_for_channel(response, channel)

    def print_transcript(self, session_id: str) -> None:
        """Print formatted transcript of a session."""
        session = self._sessions.get(session_id)
        if not session:
            print(f"Session '{session_id}' not found.")
            return

        print(f"\n{'═'*60}")
        print(f"  SESSION: {session_id} | Channel: {session.channel.upper()}")
        print(f"{'═'*60}")
        for msg in session.messages:
            prefix = {
                "user":   "🧑 Customer",
                "agent":  "🤖 Assistant",
                "system": "⚙️  System",
            }.get(msg.role, msg.role)
            print(f"\n[{msg.timestamp}] {prefix}:")
            for line in msg.text.split("\n"):
                print(f"  {line}")
        print(f"\n{'═'*60}\n")
