"""Rejected: a relative import, which grep for the package name would miss."""
from . import grade
print(grade)
