translator: uvicorn translator_service.app:app --port 8001 --reload
identity: uvicorn backend.identity_service.app.main:app --port 8002 --reload
query: uvicorn backend.query_service.app.main:app --port 8003 --reload
terminology: uvicorn backend.terminology_service.app.main:app --port 8004 --reload
orchestrator: uvicorn backend.orchestrator_service.app.main:app --port 8000 --reload