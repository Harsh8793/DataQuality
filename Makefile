# DataPilot AI — developer tasks
# Usage: make <target>

.PHONY: help install backend frontend seed dev clean

help:
	@echo "DataPilot AI"
	@echo "  make install    Install backend + frontend dependencies"
	@echo "  make seed       Generate samples + seed demo user/dataset"
	@echo "  make backend    Run the FastAPI backend (http://localhost:8000)"
	@echo "  make frontend   Run the Vite frontend (http://localhost:5173)"

install:
	cd backend && python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt
	cd frontend && npm install

seed:
	cd backend && ./.venv/Scripts/python.exe -m scripts.seed

backend:
	cd backend && ./.venv/Scripts/python.exe main.py

frontend:
	cd frontend && npm run dev

clean:
	rm -f backend/data/datapilot.db
	rm -rf backend/data/parquet/* backend/data/uploads/* backend/data/reports/*
