"""Services: orchestration that may touch the database.

Services sit between the API and the pure domain/analytics core. They are the
only place where "read rows, compute, write rows" is allowed to happen.
"""
