"""SpeakLoop phoneme scoring core.

    from speakloop.phoneme import assess
    result = assess("attempt.wav", "She walked to the shops.")

Heavy dependencies (torch, transformers) are imported lazily, so importing
this package is cheap; the model loads on the first ``assess`` call.
"""

from .assess import assess, assess_emissions
from .g2p import arpa_to_ipa, g2p_words
from .rules import load_rules

__all__ = ["assess", "assess_emissions", "g2p_words", "arpa_to_ipa", "load_rules"]
