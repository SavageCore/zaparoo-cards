.PHONY: cards cards-forced example

cards:
	uv run create_pdf.py --crop

cards-forced:
	uv run create_pdf.py --crop --no-cache

example:
	uv run create_pdf.py --crop --example --no-cache

example-outline:
	uv run create_pdf.py --outline --example --no-cache
