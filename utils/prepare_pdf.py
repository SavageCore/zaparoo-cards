import math
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader, PdfWriter, Transformation  # type: ignore
from reportlab.lib.colors import black  # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore

covers_dir = "GameCovers"
artwork_dir = "tmp_artwork"

# zaparoo-designer's NFCCCsizeCard has rx/ry 35 and strokeWidth 2, and divides
# both by the same factors it uses for the print scale.
OUTLINE_RADIUS_PT = 35 / 4
OUTLINE_WIDTH_PT = 2 / 10
CROP_MARK_WIDTH_PT = 2 / 10


def from_mm_to_point(x):
    """Convert millimeters to points."""
    return (x / 25.4) * 72


def from_pixels_to_point(x):
    """Convert pixels to points (assuming 300 DPI)."""
    return (x / 300) * 72


@dataclass(frozen=True)
class CardPlacement:
    """Where one card PDF has to be stamped onto a finished sheet."""

    page_index: int
    card_path: str
    center_x: float
    center_y: float


def card_transform(placement, card_width_in_pt, card_height_in_pt):
    """Build the matrix placing a card page's box into its grid cell.

    Reproduces the sequence the raster pipeline used via reportlab:
    translate(cell centre) -> rotate(270) -> translate(-w/2, -h/2).
    Card pages are emitted by cairo with a zero origin MediaBox, so the page's
    own coordinates are the ones the matrix maps.
    """
    return Transformation(
        (
            0.0,
            -1.0,
            1.0,
            0.0,
            placement.center_x - card_height_in_pt / 2,
            placement.center_y + card_width_in_pt / 2,
        )
    )


def crop_marks_layer(paper_size, segments):
    """Build a one page PDF holding nothing but the crop mark segments.

    The marks are stamped after the cards so they sit on top of the artwork,
    while the print outlines reportlab drew stay underneath it.
    """
    buffer = BytesIO()
    marks = canvas.Canvas(buffer, pagesize=paper_size)
    marks.setLineWidth(CROP_MARK_WIDTH_PT)
    marks.setStrokeColor(black)
    for x0, y0, x1, y1 in segments:
        marks.line(x0, y0, x1, y1)
    marks.showPage()
    marks.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def stamp_cards(
    output_path, placements, card_size_in_pt, crop_marks, transform=card_transform
):
    """Overlay the card PDFs onto the sheets reportlab laid out.

    reportlab keeps ownership of the page furniture (grid, print outlines,
    document metadata). The card artwork is stamped on afterwards so it stays
    vector instead of being resampled from a full card raster.
    """
    if not placements:
        return

    card_width_in_pt, card_height_in_pt = card_size_in_pt

    reader = PdfReader(output_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    metadata = reader.metadata
    if metadata:
        writer.add_metadata(
            {str(key): str(value) for key, value in metadata.items() if value}
        )

    placements_by_page = defaultdict(list)
    for placement in placements:
        placements_by_page[placement.page_index].append(placement)

    for page_index, page_placements in placements_by_page.items():
        page = writer.pages[page_index]
        for placement in page_placements:
            card = PdfReader(placement.card_path).pages[0]
            # Under the print outlines reportlab drew. zaparoo-designer also
            # strokes the outline before the card, but its card background is
            # inset from the clip edge so the stroke survives intact and reads at
            # the full 0.2pt. Ours is full bleed, so the card has to go beneath
            # the outline to get the same result - measured 0.2012pt of ink
            # against the designer's 0.2012pt at 1200dpi, where a covered stroke
            # would only show 0.0812pt.
            page.merge_transformed_page(
                card,
                transform(placement, card_width_in_pt, card_height_in_pt),
                over=False,
            )

        segments = crop_marks.get(page_index)
        if segments:
            # Last of all, matching the designer drawing the marks once the page
            # is full. The foot marks are top_margin + 1 long and so reach up
            # over the bottom row of cards, which needs them on top.
            page.merge_page(
                crop_marks_layer(
                    (page.mediabox.width, page.mediabox.height), segments
                ),
                over=True,
            )

    with open(output_path, "wb") as handle:
        writer.write(handle)


def prepare_pdf(
    cards,
    card_size_in_pt,
    layout="vertical",
    print_outlines=False,
    cut_marks=None,
    output_path="output.pdf",
):
    grid_size = [0, 0]
    left_margin = 3
    top_margin = 10
    columns = 0
    rows = 0
    right_margin = 3
    bottom_margin = 5
    _tmp_columns = 0
    _tmp_rows = 0
    _tmp_grid_size = [0, 0]

    c = canvas.Canvas(output_path, pagesize=A4)
    c.setCreator("zaparoo-cards")
    # ReportLab does not expose a public setProducer API; override default producer directly.
    c._doc.info.producer = "zaparoo-cards"
    paper_width_in_pt = A4[0]  # 595.27 points
    paper_height_in_pt = A4[1]  # 841.89 points
    top_margin_in_pt = from_mm_to_point(top_margin)
    left_margin_in_pt = from_mm_to_point(left_margin)
    right_margin_in_pt = from_mm_to_point(right_margin)
    bottom_margin_in_pt = from_mm_to_point(bottom_margin)

    card_width_in_pt, card_height_in_pt = card_size_in_pt
    # The grid maths runs in the rotated (landscape) frame, so seed it with the
    # card's long and short edges. The "vertical" branch below swaps them back
    # to the card page's own portrait dimensions, which is also what the
    # placement matrix needs.
    width_in_pt = card_height_in_pt
    height_in_pt = card_width_in_pt
    avail_paper_width = paper_width_in_pt - left_margin_in_pt - right_margin_in_pt
    avail_paper_height = paper_height_in_pt - top_margin_in_pt - bottom_margin_in_pt

    neutral_template = layout

    if _tmp_columns == 0 or _tmp_rows == 0:
        possible_rows = int(avail_paper_height / height_in_pt)
        possible_columns = int(avail_paper_width / width_in_pt)
        straight_labels = possible_rows * possible_columns
        possible_rows_rotated = int(avail_paper_height / width_in_pt)
        possible_columns_rotated = int(avail_paper_width / height_in_pt)
        rotated_labels = possible_rows_rotated * possible_columns_rotated

        if straight_labels == rotated_labels:
            margins_w = avail_paper_width - possible_columns * width_in_pt
            margins_h = avail_paper_height - possible_rows * height_in_pt
            margins_w_r = avail_paper_width - possible_columns_rotated * height_in_pt
            margins_h_r = avail_paper_height - possible_rows_rotated * width_in_pt

            if abs(margins_w - margins_h) > abs(margins_w_r - margins_h_r):
                rows = possible_rows_rotated
                columns = possible_columns_rotated
                neutral_template = "vertical"
            else:
                rows = possible_rows
                columns = possible_columns
        elif straight_labels > rotated_labels:
            rows = possible_rows
            columns = possible_columns
        else:
            neutral_template = "vertical"
            rows = possible_rows_rotated
            columns = possible_columns_rotated

    if neutral_template == "vertical":
        width_in_pt, height_in_pt = height_in_pt, width_in_pt

    grid_size = [
        from_mm_to_point(_tmp_grid_size[0]),
        from_mm_to_point(_tmp_grid_size[1]),
    ]
    if grid_size[0] == 0:
        grid_size[0] = avail_paper_width / columns
        grid_size[1] = avail_paper_height / rows

    labels_per_page = rows * columns

    # Crop mark helpers - sets to store unique x and y positions
    cut_helper_x = set()
    cut_helper_y = set()
    crop_marks = {}

    def collect_crop_marks(page_idx):
        """Gather this page's crop mark segments for stamping after the cards."""
        segments = []

        # Vertical lines at x positions
        for x_value in sorted(cut_helper_x):
            segments.append(
                (
                    x_value,
                    paper_height_in_pt - top_margin_in_pt,
                    x_value,
                    paper_height_in_pt,
                )
            )  # Top
            # zaparoo-designer draws the foot mark as
            # `paperHeight - topMargin - 1` to `paperHeight`, which lands it at
            # the bottom of the page and makes it 1pt longer than the head mark.
            # Reproduced so the two match mark for mark.
            segments.append((x_value, 0, x_value, top_margin_in_pt + 1))  # Bottom

        # Horizontal lines at y positions
        for y_value in sorted(cut_helper_y):
            segments.append(
                (
                    paper_width_in_pt - left_margin_in_pt,
                    y_value,
                    paper_width_in_pt,
                    y_value,
                )
            )  # Right edge inward
            segments.append((0, y_value, left_margin_in_pt, y_value))  # Left edge outward

        cut_helper_x.clear()
        cut_helper_y.clear()

        if segments:
            crop_marks[page_idx] = segments

    placements = []

    # Process cards
    for page_idx in range(math.ceil(len(cards) / labels_per_page)):
        for idx in range(labels_per_page):
            card_idx = page_idx * labels_per_page + idx
            if card_idx >= len(cards):
                break
            row = idx // columns
            col = idx % columns
            if row >= rows:
                continue

            x = left_margin_in_pt + col * grid_size[0]
            y = paper_height_in_pt - top_margin_in_pt - (row + 1) * grid_size[1]

            center_x = x + grid_size[0] / 2
            center_y = y + grid_size[1] / 2

            # Collect crop mark positions
            if cut_marks == "crop":
                # Marks sit on the card's printed edge. The card is drawn portrait
                # then rotated 270, so its long edge runs across the page.
                half_x = height_in_pt / 2
                half_y = width_in_pt / 2
                cut_helper_x.update([center_x - half_x, center_x + half_x])
                cut_helper_y.update([center_y - half_y, center_y + half_y])

            placements.append(
                CardPlacement(
                    page_index=page_idx,
                    card_path=cards[card_idx],
                    center_x=center_x,
                    center_y=center_y,
                )
            )

            if print_outlines:
                c.saveState()
                c.translate(center_x, center_y)
                c.rotate(270)
                c.setStrokeColor(black)
                c.setLineWidth(OUTLINE_WIDTH_PT)
                c.roundRect(
                    -width_in_pt / 2,
                    -height_in_pt / 2,
                    width_in_pt,
                    height_in_pt,
                    radius=OUTLINE_RADIUS_PT,
                )
                c.restoreState()

        if cut_marks == "crop":
            collect_crop_marks(page_idx)

        c.showPage()

    c.save()

    stamp_cards(output_path, placements, card_size_in_pt, crop_marks)
