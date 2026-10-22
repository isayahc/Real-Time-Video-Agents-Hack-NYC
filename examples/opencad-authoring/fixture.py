"""Deterministic CAD regression fixture, not a model-generated or validated machine."""
from opencad import Part, Sketch

WIDTH = 80.0
DEPTH = 50.0
THICKNESS = 8.0
HOLE_RADIUS = 3.0


def mounting_plate(width: float, depth: float, thickness: float) -> Part:
    """Create a filleted plate with four through mounting holes."""
    profile = Sketch(plane="XY", name="Mounting plate profile")
    profile.rect(width, depth, origin=(-width / 2, -depth / 2))
    plate = Part(name="Mounting plate").extrude(profile, depth=thickness)
    plate.fillet(edges="top", radius=1.0, name="Plate edge finish")
    for x in (-25.0, 25.0):
        for y in (-15.0, 15.0):
            hole = Sketch(plane="XY", origin=(0, 0, -1), name="Mounting hole profile")
            hole.circle(HOLE_RADIUS, center=(x, y))
            cutter = Part(name="Temporary hole tool").extrude(hole, depth=thickness + 2)
            plate.cut(cutter, name="Through mounting hole")
    return plate


base = mounting_plate(WIDTH, DEPTH, THICKNESS)
lower = Sketch(plane="XY", origin=(0, 0, THICKNESS), name="Collar lower section")
lower.circle(14)
upper = Sketch(plane="XY", origin=(0, 0, THICKNESS + 20), name="Collar upper section")
upper.circle(10)
collar = Part(name="Tapered collar").loft([lower, upper], name="Tapered collar loft")
bore = Sketch(plane="XY", origin=(0, 0, THICKNESS - 1), name="Collar bore profile")
bore.circle(6)
tool = Part(name="Temporary bore tool").extrude(bore, depth=22)
collar.cut(tool, name="Through collar bore")
parts = {"mount": base, "collar": collar}
