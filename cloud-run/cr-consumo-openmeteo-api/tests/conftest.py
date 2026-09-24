import os

# Debe fijarse antes de que cualquier módulo importe src.app.core.config,
# ya que GCS_BUCKET_NAME es obligatoria (falla al importar si no está seteada).
os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket-for-unit-tests")

import pytest

from src.app.main import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client
