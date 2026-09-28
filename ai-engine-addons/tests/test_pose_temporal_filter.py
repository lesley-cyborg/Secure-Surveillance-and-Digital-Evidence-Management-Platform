from surveillance_addons.contracts import BoundingBox, PoseObservation
from surveillance_addons.pose_temporal import PoseConfirmation
BOX=BoundingBox(x_min=0,y_min=0,x_max=.5,y_max=.5)
def obs(posture="falling",confidence=.9): return PoseObservation(posture=posture,confidence=confidence,bounding_box=BOX)
def test_pose_requires_confidence_and_consecutive_frames():
    tracker=PoseConfirmation(required_frames=3,confidence_threshold=.8)
    assert not tracker.update("person-1",(obs(),),now=0)[0].confirmed
    assert not tracker.update("person-1",(obs(),),now=1)[0].confirmed
    assert tracker.update("person-1",(obs(),),now=2)[0].confirmed
    assert not tracker.update("person-1",(obs("standing"),),now=3)[0].confirmed
