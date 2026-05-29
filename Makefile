.PHONY: install dev test

install:
	.venv/bin/python -m pip install -r requirements.txt

dev:
	.venv/bin/uvicorn dashboard:app --host 127.0.0.1 --port 8765 --reload

test:
	PYTHONPYCACHEPREFIX=/private/tmp/ds4-dashboard-pycache .venv/bin/python -m unittest discover -s tests
