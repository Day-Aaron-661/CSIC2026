"""Keep tests away from the developer database.

Importing ``app.main`` builds the module-level ``app``, which opens
``CP2_DB_PATH`` (default ``backend/data/cp2.sqlite3``). Point it at a
throwaway file before any test module imports the app, so tests never
migrate or depend on a local dev database. Each test still passes its own
``tmp_path`` database to ``create_app``.
"""
import os
import tempfile

os.environ["CP2_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cp2-tests-"), "import.sqlite3")
