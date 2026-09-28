from surveillance_addons.contracts import BoundingBox, PoseObservation
from surveillance_addons.pose_temporal import PoseConfirmation

BOX = BoundingBox(x_min=0, y_min=0, x_max=0.5, y_max=0.5)
def observation():
    return PoseObservation(posture="falling", confidence=0.9, bounding_box=BOX)

def test_pose_requires_consecutive_frames():
    tracker = PoseConfirmation(required_frames=2)
    assert tracker.update("person-1", (observation(),))[0].confirmed is False
    assert tracker.update("person-1", (observation(),))[0].confirmed is True
