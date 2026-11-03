"""Pure domain layer: entities, value objects and invariants.

Nothing in this package may import FastAPI, SQLAlchemy, or anything that
performs I/O. That constraint is what makes the money-critical logic testable
in microseconds and impossible to accidentally couple to a request.
"""
