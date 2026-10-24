"""Tests never touch the real records folder: its in-house references would change the demo results, and
the tests would append rows to the real audit log and signatures. Set before the package is imported."""
import os
import tempfile

os.environ["FTIR_ANALYZER_RECORDS"] = tempfile.mkdtemp(prefix="ftir_test_records_")
