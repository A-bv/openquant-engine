.PHONY: install test api app dev

install:        ## one-time: install the engine (editable) + the app deps
	pip install -e ".[api,dev]"
	cd app && npm install

test:           ## run the offline test suite (exam oracles included)
	pytest -q -m "not live"

api:            ## run the API on :8000
	python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

app:            ## run the React app on :5173
	cd app && npm run dev

dev:            ## run API and app together; Ctrl-C stops both
	@trap 'kill 0' EXIT; \
	python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 & \
	( cd app && npm run dev ) & \
	wait
