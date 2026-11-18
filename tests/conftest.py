import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app import main
from backend.app.ai import client as ai
from backend.app.core.config import Settings
from backend.app.core.runtime import Runtime
from backend.app.db.base import Base
from backend.app.db import models  # noqa: F401
from backend.app.db.session import configure_engine
from backend.app.modules.readings import processing


@pytest.fixture
def database(monkeypatch,tmp_path):
    # model_construct uses only declared defaults and these dummy values, no settings sources.
    config=Settings.model_construct(data_dir=tmp_path, database_url='sqlite://',deepinfra_api_key=SecretStr('test-key-not-a-real-credential'), knowledge_enabled=False)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    configure_engine(engine)
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    runtime=Runtime(config,factory,'isolated-test-owner')
    app=main.create_app(runtime,background_jobs=False,serve_frontend=False)
    monkeypatch.setattr(main,'app',app,raising=False)
    processor=processing.ReadingProcessor(factory,config)
    monkeypatch.setattr(processing,'process_stage',processor.process_stage,raising=False)
    monkeypatch.setattr(ai,'settings',lambda:config)
    yield factory
    engine.dispose()


@pytest.fixture
def client(database):
    client=TestClient(main.app,base_url='http://localhost',client=('127.0.0.1',1234))
    assert client.post('/api/bootstrap').status_code==200
    yield client
    client.close()


@pytest.fixture
def photo():
    buffer=io.BytesIO()
    Image.new('RGB',(1200,700),'white').save(buffer,format='JPEG')
    return buffer.getvalue()
