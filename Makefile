.PHONY: cards cards-forced example example-outline compare

cards:
	uv run create_pdf.py --crop

cards-forced:
	uv run create_pdf.py --crop --no-cache

example:
	uv run create_pdf.py --crop --example --no-cache

example-outline:
	uv run create_pdf.py --outline --example --no-cache

# Side by side of a card design and matching Cards/<system>_old.svg
#   make compare SYSTEM=saturn
#   make compare-saturn
SYSTEM ?= neogeo

COVER_neogeo := Metal Slug X.jpg
COVER_saturn := Guardian Heroes.jpg

compare:
	uv run compare_templates.py \
		--left "Cards/$(SYSTEM)_old.svg" \
		--right "Cards/$(SYSTEM).svg" \
		--cover "GameCovers/$(SYSTEM)/$(COVER_$(SYSTEM))" \
		--left-label "Before" \
		--right-label "After" \
		--output "output_compare_$(SYSTEM).pdf"

compare-%:
	@$(MAKE) --no-print-directory compare SYSTEM=$*
