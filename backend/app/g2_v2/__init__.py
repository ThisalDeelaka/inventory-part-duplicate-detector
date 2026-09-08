"""Pure GF-6A G2-v2 adapter contracts; no persistence or selection behavior."""

from app.g2_v2.adapter import build_g2_v2_manifest
from app.g2_v2.contracts import *  # noqa: F401,F403
from app.g2_v2.validation import G2V2ManifestValidationError, validate_g2_v2_manifest

__all__ = [
    "build_g2_v2_manifest",
    "G2V2ManifestValidationError",
    "validate_g2_v2_manifest",
]
