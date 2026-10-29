"""Passive seed seat; millimetres, Z-up, bottom face at z=0.

Authored assumptions; an ideal seed fit does not establish physical pickup.
"""
from opencad import Part

BASE_X = 40.0
BASE_Y = 30.0
BASE_THICKNESS = 4.0
POST_RADIUS = 4.0
POST_HEIGHT = 8.0
SEAT_MOUTH_RADIUS = 1.4


def build_fixture() -> Part:
    """Join the centered base/post and subtract a 45-degree conical seed seat."""
    base = Part(name="Bench base").box(BASE_X, BASE_Y, BASE_THICKNESS)
    base.translate((0.0, 0.0, BASE_THICKNESS / 2))
    post = Part(name="Seed pedestal").cylinder(POST_RADIUS, POST_HEIGHT)
    post.translate((0.0, 0.0, BASE_THICKNESS + POST_HEIGHT / 2))
    base.union(post, name="Integral pedestal")
    # Cones start at z=0; cylinders and boxes are centered. Extend the cutter
    # 1 mm above the rim, so its cap cannot leave a coincident top face.
    floor_radius = SEAT_MOUTH_RADIUS / 10
    cutter_height = SEAT_MOUTH_RADIUS + 1.0 - floor_radius
    seat = Part(name="Seat cutter").cone(floor_radius, SEAT_MOUTH_RADIUS + 1.0, cutter_height)
    seat.translate((0.0, 0.0, BASE_THICKNESS + POST_HEIGHT - SEAT_MOUTH_RADIUS + floor_radius))
    return base.cut(seat, name="45-degree seed seat")


parts = {"seed-seat": build_fixture()}
