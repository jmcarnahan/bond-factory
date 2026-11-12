"""Shared test support for the due-instant, permissions and write-path tests: fakes and fixtures. Loaded by
conftest as a pytest plugin.

conftest's ``Base`` already has a ``tasks`` table. A test that needs a Task model with extra app columns must
declare its own ``declarative_base()`` rather than a second ``tasks`` table on that Base.
"""
