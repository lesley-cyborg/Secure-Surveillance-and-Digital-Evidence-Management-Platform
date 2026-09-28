from __future__ import  annotations
from collections.abc import Callable
from .contracts import BoundingBox
from .model_adapters import FrameArray

def crop_normalized(frame: FrameArray, box: BoundingBox) -> FrameArray:
    height, width = frame.shape[:2]
    x1=max(0,min(width-1,int(box.x_min*width))); y1=max(0,min(height-1,int(box.y_min*height)))
    x2=max(x1+1,min(width,int(box.x_max*width))); y2=max(0,y1+1,min(height,int(box.y_max*height)))
    crop=frame[y1:y2,x1:x2]
    if crop.size == 0: raise ValueError("plate crop is empty")
    return crop.copy()

def preprocess_plate(crop: FrameArray) -> FrameArray:
    if crop.ndim == 3:
        gray = np.mean(crop, axis=2).astype(np.uint8)
    else:
        gray = crop
        return np.where(gray >= 128, 255, 0).astype(np.uint8)
    
class PlateOCR(Callable[[FrameArray], tuple[str, float]]):
    pass

def read_plate(frame: FrameArray, box: BoundingBox, ocr: Callable[[FrameArray], tuple[str, float]]) -> tuple[str, float]:
    return ocr(preprocess_plate(crop_normalized(frame,box)))
























