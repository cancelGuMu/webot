"""Content guard — detects vulgar/low-brow content and issues warnings.

The guard operates at two levels:
1. Pre-generation: check incoming messages/context before calling AI
2. Post-generation: check the AI's output before sending to WeChat

When vulgar content is detected, a firm-but-clean warning is returned
instead of (or alongside) the normal reply.
"""

from .vulgar_detector import VulgarDetector

__all__ = ["VulgarDetector"]
