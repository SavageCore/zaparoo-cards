import argparse
import os

from pypdf import PdfReader, Transformation  # type: ignore
from reportlab.lib.colors import black  # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore

from utils.prepare_pdf import (  # type: ignore
    CardPlacement,
    from_mm_to_point,
    stamp_cards,
)
from utils.render_card import Job, get_template_meta, render_card  # type: ignore

# The rescued hucard design is the tree at ee8a397^, the commit immediately
# before the cartridge redesign landed.
RESCUE_REF = "ee8a397^"

DEFAULT_LEFT = "Cards/neogeo_old.svg"
DEFAULT_RIGHT = "Cards/neogeo.svg"
DEFAULT_COVER = os.path.join("GameCovers", "neogeo", "Metal Slug X.jpg")

TITLE_FONT = "Helvetica-Bold"
BODY_FONT = "Helvetica"

TITLE_SIZE = 16
SUBTITLE_SIZE = 9
CAPTION_SIZE = 10
NOTE_SIZE = 8

MARGIN = from_mm_to_point(12)
GUTTER = from_mm_to_point(12)
TITLE_GAP = 6
CARD_GAP = 16
CAPTION_GAP = from_mm_to_point(5)
NOTE_GAP = 8


def upright_transform(placement, card_width_pt, card_height_pt):
    """Place a card page without the 270 degree turn the print sheet applies.

    Comparison pages show the artwork the way it was designed. Sheets rotate
    it, because the 85mm edge runs across the paper.
    """
    return Transformation().translate(
        placement.center_x - card_width_pt / 2,
        placement.center_y - card_height_pt / 2,
    )


def render(template_path, cover_path, cache_dir, use_cache):
    job = Job(
        system="compare",
        game=os.path.splitext(os.path.basename(cover_path))[0],
        cover_path=cover_path,
        template_path=template_path,
    )
    return render_card(job, cache_dir, use_cache=use_cache)


def main():
    parser = argparse.ArgumentParser(
        description="Render two card templates from the same cover art side by side."
    )
    parser.add_argument("--left", default=DEFAULT_LEFT, help="Left card template")
    parser.add_argument("--right", default=DEFAULT_RIGHT, help="Right card template")
    parser.add_argument("--left-label", default="Before", help="Caption for left card")
    parser.add_argument("--right-label", default="After", help="Caption for right card")
    parser.add_argument("--cover", default=DEFAULT_COVER, help="Cover art to embed")
    parser.add_argument(
        "--output", default="output_compare.pdf", help="PDF written to this path"
    )
    parser.add_argument(
        "--cache-dir",
        default=os.path.join(".cache", "zaparoo-cards", "rendered"),
        help="Directory used for persistent rendered card cache",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Force a full re-render"
    )
    args = parser.parse_args()

    for path in (args.left, args.right, args.cover):
        if not os.path.exists(path):
            parser.error(f"missing input: {path}")

    os.makedirs(args.cache_dir, exist_ok=True)

    card_pdfs = []
    for template_path in (args.left, args.right):
        output_path, was_cached = render(
            template_path, args.cover, args.cache_dir, not args.no_cache
        )
        state = "cached" if was_cached else "rendered"
        print(f"{state.capitalize()} {os.path.basename(template_path)}")
        card_pdfs.append(output_path)

    # Card pages come out of cairo at the printed media size, portrait, so the
    # same box is used for the comparison page without any rotation.
    card_width_pt, card_height_pt = get_template_meta(args.left).card_size_in_pt

    captions = (args.left_label, args.right_label)
    template_note = "   ".join(
        f"{caption}: {os.path.basename(path)}"
        for caption, path in zip(captions, (args.left, args.right))
    )
    cover_name = os.path.splitext(os.path.basename(args.cover))[0]
    print_note = (
        "Shown upright for comparison. Print sheets rotate cards 90 degrees, "
        "so the 85mm edge runs across the paper."
    )

    page_width = A4[0]
    page_height = (
        MARGIN
        + TITLE_SIZE
        + TITLE_GAP
        + SUBTITLE_SIZE
        + CARD_GAP
        + card_height_pt
        + CAPTION_GAP
        + CAPTION_SIZE
        + NOTE_GAP
        + NOTE_SIZE
        + MARGIN
    )

    block_width = card_width_pt * 2 + GUTTER
    origin_x = (page_width - block_width) / 2

    title_baseline = page_height - MARGIN - TITLE_SIZE
    subtitle_baseline = title_baseline - (TITLE_GAP + SUBTITLE_SIZE)
    cards_top = subtitle_baseline - CARD_GAP
    cards_center_y = cards_top - card_height_pt / 2
    caption_baseline = cards_top - card_height_pt - CAPTION_GAP
    note_baseline = caption_baseline - (NOTE_GAP + NOTE_SIZE)

    c = canvas.Canvas(args.output, pagesize=(page_width, page_height))
    c.setCreator("zaparoo-cards")
    c._doc.info.producer = "zaparoo-cards"

    c.setFont(TITLE_FONT, TITLE_SIZE)
    c.drawCentredString(page_width / 2, title_baseline, f"{cover_name} - card design")

    c.setFont(BODY_FONT, SUBTITLE_SIZE)
    c.drawCentredString(page_width / 2, subtitle_baseline, template_note)

    placements = []
    for index, (card_pdf, caption) in enumerate(zip(card_pdfs, captions)):
        center_x = origin_x + index * (card_width_pt + GUTTER) + card_width_pt / 2

        c.saveState()
        c.setStrokeColor(black)
        c.setLineWidth(0.3)
        c.rect(
            center_x - card_width_pt / 2,
            cards_center_y - card_height_pt / 2,
            card_width_pt,
            card_height_pt,
        )
        c.restoreState()

        c.setFont(TITLE_FONT, CAPTION_SIZE)
        c.drawCentredString(center_x, caption_baseline, caption)

        placements.append(
            CardPlacement(
                page_index=0,
                card_path=card_pdf,
                center_x=center_x,
                center_y=cards_center_y,
            )
        )

    c.setFont(BODY_FONT, NOTE_SIZE)
    c.drawCentredString(page_width / 2, note_baseline, print_note)

    c.showPage()
    c.save()

    stamp_cards(
        args.output,
        placements,
        (card_width_pt, card_height_pt),
        {},
        transform=upright_transform,
    )

    print(f"Wrote {args.output} ({len(PdfReader(args.output).pages)} page)")


if __name__ == "__main__":
    main()
