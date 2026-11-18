"""Refactor invariants: import safety, contract stability, transaction ownership, migrations."""
import ast
import subprocess
import sys
from pathlib import Path
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from backend.app.db.base import Base
from backend.app.tools.export_openapi import ROOT, export


def test_schema_export_never_loads_private_configuration_or_runtime(tmp_path):
    code = '''
import sys
from pathlib import Path

def guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = Path(args[0]).name
        if name == '.env' or (name.startswith('.env.') and name != '.env.example'):
            raise AssertionError('Secret file access attempted')
    if event in {'socket.connect', 'sqlite3.connect'}:
        raise AssertionError('Schema export attempted runtime I/O')
sys.addaudithook(guard)
from backend.app import main
from backend.app.tools.export_openapi import export

def forbidden(*args, **kwargs):
    raise AssertionError('Runtime initialization attempted')
main.settings = forbidden
main.create_database = forbidden
main.load_runtime = forbidden
assert export(Path(sys.argv[1]))
'''
    target = tmp_path/'openapi.json'
    subprocess.run([sys.executable,'-c',code,str(target)],cwd=ROOT,check=True)
    assert target.is_file()


def test_contract_is_current_and_operations_have_unique_explicit_names():
    import json
    assert export(check=True)
    schema=json.loads((ROOT/'contracts/openapi.json').read_text())
    operations=[operation for path in schema['paths'].values() for operation in path.values()]
    names=[operation['operationId'] for operation in operations]
    assert len(names)==len(set(names))==30
    assert all(operation['tags'] for operation in operations)
    assert schema['paths']['/api/books']['get']['responses']['200']['content']['application/json']['schema']['items']['$ref'].endswith('/BookResponse')
    assert 'image/jpeg' in schema['paths']['/api/sessions/{session_id}/image']['get']['responses']['200']['content']


def test_services_do_not_contain_database_queries_and_repositories_do_not_commit():
    for path in (ROOT/'backend/app/modules').glob('*/service.py'):
        tree=ast.parse(path.read_text())
        assert not any(isinstance(node,ast.ImportFrom) and node.module and node.module.startswith('sqlalchemy') for node in ast.walk(tree)),path
        assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in {'execute','scalar','scalars','query'} for node in ast.walk(tree)),path
    for path in (ROOT/'backend/app/modules').glob('*/repository.py'):
        tree=ast.parse(path.read_text())
        assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in {'commit','rollback'} for node in ast.walk(tree)),path


def test_original_migration_still_matches_refactored_models(tmp_path):
    config=Config(str(ROOT/'alembic.ini'))
    config.set_main_option('sqlalchemy.url',f'sqlite:///{tmp_path / "migration.db"}')
    command.upgrade(config,'head')
    engine=create_engine(config.get_main_option('sqlalchemy.url'))
    with engine.connect() as connection:
        differences=compare_metadata(MigrationContext.configure(connection),Base.metadata)
    engine.dispose()
    assert differences==[]


def test_failed_pairing_claim_rolls_back_reading_and_removes_file(client,database,photo,monkeypatch):
    from urllib.parse import urlparse
    from sqlalchemy import func,select
    from backend.app.modules.capture.repository import CaptureRepository
    from backend.app.modules.readings.models import ReadingSession
    book=client.post('/api/books',json={'title':'Rollback test'}).json()
    pairing=client.post(f"/api/books/{book['id']}/pair").json()
    token=urlparse(pairing['url']).path.split('/')[-1]
    monkeypatch.setattr(CaptureRepository,'claim',lambda *args:False)
    response=client.post(f'/api/capture/{token}',files={'image':('book.jpg',photo)})
    assert response.status_code==409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ReadingSession))==0
    assert not list(client.app.runtime.config.data_dir.glob('uploads/*.jpg'))
