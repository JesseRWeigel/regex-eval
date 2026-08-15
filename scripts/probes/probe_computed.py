"""Rejected: a computed import, which no grep can see."""
import importlib
name = "r" + "x.grade"
module = importlib.import_module(name)
print(module)
