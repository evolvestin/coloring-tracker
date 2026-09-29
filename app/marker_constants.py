"""Constants shared by the marker model, API and admin.

Manufacturers intentionally live in code rather than in a database table: the
list is small, stable and must be selected by the user from known values.
"""

MARKER_MANUFACTURERS = (
    ('flysea', 'Flysea'),
    ('guangna', 'GuangNa'),
    ('grasp', 'GRASP'),
    ('infiart', 'Infiart'),
    ('languo', 'Languo'),
    ('rosymeng', 'ROSYMENG'),
    ('nusoulra', 'NuSoulra'),
    ('tooli_art', 'Tooli-Art'),
    ('nicety', 'NICETY'),
    ('posca', 'POSCA'),
)

# Kept only so markers saved before manufacturers became mandatory remain readable.
MARKER_LEGACY_MANUFACTURERS = (('unknown', 'Не указан'),)
MARKER_MANUFACTURER_CHOICES = MARKER_MANUFACTURERS + MARKER_LEGACY_MANUFACTURERS
MARKER_MANUFACTURER_CODES = frozenset(code for code, _ in MARKER_MANUFACTURERS)
MARKER_MANUFACTURER_LABELS = dict(MARKER_MANUFACTURER_CHOICES)

MARKER_TYPES = (
    ('marker', 'Маркер'),
    ('pen', 'Ручка'),
)
MARKER_TYPE_CODES = frozenset(code for code, _ in MARKER_TYPES)
MARKER_TYPE_LABELS = dict(MARKER_TYPES)
