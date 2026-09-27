.PHONY: cards cards-forced example example-outline compare n64

cards:
	uv run create_pdf.py --crop

cards-forced:
	uv run create_pdf.py --crop --no-cache

example:
	uv run create_pdf.py --crop --example --no-cache

example-outline:
	uv run create_pdf.py --outline --example --no-cache

# Side by side of the rescued pre-ee8a397 hucard design and the current one.
compare:
	uv run compare_templates.py \
		--left-label "Before" \
		--right-label "After"

n64:
	uv run generate_n64_templates.py
