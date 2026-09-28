import numpy as np
from surveillance_addons.contracts import BoundingBox
from surveillance_addons.plate_processing import read_plate
def test_plate_crop_is_preprocessed_before_ocr():
    seen=[]
    def ocr(crop): seen.append(crop); return "ABC123", .9
    text, confidence=read_plate(np.full((10,20,3),255,dtype=np.uint8),BoundingBox(x_min=0,y_min=0,x_max=.5,y_max=1),ocr)
    assert text=="ABC123" and confidence==.9 and seen[0].ndim==2
