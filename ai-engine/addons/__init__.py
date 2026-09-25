"""Optional, isolated AI enrichments for live camera streams."""

from addons.pipeline import AnalysisPipeline
from addons.runtime import AddonRuntime, build_addon_runtime
from addons.schemas import AddonAnalysisResult

__all__ = [
    "AddonAnalysisResult",
    "AddonRuntime",
    "AnalysisPipeline",
    "build_addon_runtime",
]
