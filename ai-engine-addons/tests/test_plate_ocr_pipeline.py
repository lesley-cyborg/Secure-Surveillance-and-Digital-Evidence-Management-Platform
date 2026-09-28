import numpy as np
import pytest
from surveillance_addons.contracts import BoundingBox, PlateObservation
from surveillance_addons.pipeline import AnalysisPipeline
class Plates:
    is_ready=True
    def detect(self, frame): return (PlateObservation(text="pending",confidence=.5,bounding_box=BoundingBox(x_min=0,y_min=0,x_max=.5,y_max=1)),)
class OCR:
    is_ready=True
    def read(self, crop): return "ABC123", .91
@pytest.mark.asyncio
async def test_plate_model_crop_ocr_sequence():
    result=await AnalysisPipeline(plates=Plates(),plate_ocr=OCR()).analyze(np.full((10,20,3),255,dtype=np.uint8))
    assert result.plates[0].text=="ABC123" and result.plates[0].confidence==.91
