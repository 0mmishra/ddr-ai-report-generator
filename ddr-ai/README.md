# DDR AI Report Generator

Production-ready AI web application that accepts two PDFs (Inspection + Thermal), extracts text, generates a structured DDR JSON via OpenRouter, and exports a professional DOCX report.

## Features

- FastAPI backend with robust upload and processing pipeline.
- Streamlit frontend for simple report generation workflow.
- PDF parsing with `pdfplumber` and OCR fallback using `pytesseract`.
- Strict Pydantic validation for schema-safe JSON output.
- Conflict and missing-information handling with `"Not Available"` normalization.
- DOCX export using `python-docx`.

## Architecture (Text Diagram)

```text
[Streamlit Frontend]
        |
        v
POST /generate-ddr (FastAPI)
        |
        v
[Save Uploads] -> [PDF Parser + OCR Fallback] -> [Text Merger/Cleaner]
        |
        v
[OpenRouter Prompting + JSON Validation (Pydantic)]
        |
        v
[DOCX Generator] -> outputs/ddr_report_*.docx
        |
        v
Response: { report_data, download_path }
        |
        v
GET /download-report?file_name=...
```

## Project Structure

```text
ddr-ai/
├── backend/
│   ├── config.py
│   ├── llm_engine.py
│   ├── main.py
│   ├── merger.py
│   ├── parser.py
│   ├── prompts.py
│   ├── report_generator.py
│   └── schemas.py
├── frontend/
│   └── app.py
├── uploads/
├── outputs/
├── .env.example
├── requirements.txt
└── README.md
```

## Setup

1. Create and activate a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows PowerShell
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create `.env` from `.env.example` and set your OpenRouter key.

```env
OPENROUTER_API_KEY=your_real_key
# Optional
OPENROUTER_MODEL=openrouter/auto
```

4. Run backend.

```bash
uvicorn backend.main:app --reload
```

5. Run frontend (in a second terminal).

```bash
streamlit run frontend/app.py
```

## API Summary

- `POST /generate-ddr`
  - Form-data files:
    - `inspection_file` (PDF)
    - `thermal_file` (PDF)
  - Returns:
    - `report_data`: validated DDR JSON
    - `download_path`: generated DOCX path
- `GET /download-report?file_name=<docx-name>`
  - Returns generated DOCX file bytes.

## Limitations

- OCR quality depends on scan quality and Tesseract installation.
- Very large PDFs may increase latency and token usage.
- LLM output quality depends on source document quality and clarity.

## Future Improvements

- Add authentication and role-based access.
- Add async background queue for long-running jobs.
- Add database storage and audit logs.
- Add multi-model fallback and evaluation scoring.
- Add unit/integration tests and CI pipeline.
