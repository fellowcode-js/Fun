"""Refuse to reproduce a named brand's logo or trade dress. General skill only."""
from __future__ import annotations

import re

BRANDS = ["google", "facebook", "meta", "instagram", "whatsapp", "apple", "iphone", "amazon", "netflix", "twitter",
          "microsoft", "windows", "airbnb", "spotify", "uber", "coca-cola", "coke", "pepsi", "nike", "adidas",
          "starbucks", "mcdonald", "disney", "youtube", "tiktok", "linkedin", "paypal", "stripe", "slack", "github",
          "openai", "anthropic", "samsung", "tesla", "ikea", "visa", "mastercard", "bank of america", "chase"]
COPY_WORDS = r"(logo|clone|copy|replica|exact|look(s)? (exactly )?like|trade ?dress|brand(ing)?|imitat|pixel[- ]perfect|same as|identical|login page|sign[- ]in page)"


def check(prompt: str) -> str | None:
    """Returns a refusal message, or None if the request is fine."""
    p = prompt.lower()
    hits = [b for b in BRANDS if re.search(rf"\b{re.escape(b)}\b", p)]
    if hits and re.search(COPY_WORDS, p):
        return (f"XON won't reproduce the logo, branding or trade dress of {', '.join(hits)}. "
                "Describe the layout and style you want in generic terms and XON will design an original page.")
    return None
