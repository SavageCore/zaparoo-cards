import math

from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore
from reportlab.lib.colors import black  # type: ignore

covers_dir = "GameCovers"
artwork_dir = "tmp_artwork"


def from_mm_to_point(x):
    """Convert millimeters to points."""
    return (x / 25.4) * 72


def from_pixels_to_point(x):
    """Convert pixels to points (assuming 300 DPI)."""
    return (x / 300) * 72


def prepare_pdf(cards, layout="vertical", print_outlines=False, cut_marks=None):
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

    c = canvas.Canvas("output.pdf", pagesize=A4)
    paper_width_in_pt = A4[0]  # 595.27 points
    paper_height_in_pt = A4[1]  # 841.89 points
    top_margin_in_pt = from_mm_to_point(top_margin)
    left_margin_in_pt = from_mm_to_point(left_margin)
    right_margin_in_pt = from_mm_to_point(right_margin)
    bottom_margin_in_pt = from_mm_to_point(bottom_margin)

    width_in_pt = from_pixels_to_point(1004)  # 240.96 points (vertical: 153.12)
    height_in_pt = from_pixels_to_point(638)  # 153.12 points (vertical: 240.96)
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

    # Crop marks helpers - sets to store unique x and y positions
    cut_helper_x = set()
    cut_helper_y = set()

    def make_crop_marks():
        """Draw crop marks at collected positions"""
        c.setLineWidth(0.2)
        c.setStrokeColor(black)

        # Vertical lines at x positions
        for x_value in cut_helper_x:
            c.line(
                x_value,
                paper_height_in_pt - top_margin_in_pt,
                x_value,
                paper_height_in_pt,
            )  # Top
            c.line(x_value, 0, x_value, top_margin_in_pt)  # Bottom

        # Horizontal lines at y positions
        for y_value in cut_helper_y:
            c.line(
                paper_width_in_pt - left_margin_in_pt,
                y_value,
                paper_width_in_pt,
                y_value,
            )  # Right edge inward
            c.line(0, y_value, left_margin_in_pt, y_value)  # Left edge outward

        cut_helper_x.clear()
        cut_helper_y.clear()

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

            # Apply scaling for border
            scale_factor = 0.99
            scaled_width = width_in_pt * scale_factor
            scaled_height = height_in_pt * scale_factor
            padding_x = (width_in_pt - scaled_width) / 2
            padding_y = (height_in_pt - scaled_height) / 2

            # Collect crop mark positions
            if cut_marks == "crop":
                if neutral_template == "vertical":
                    # Card corners after 270-degree rotation
                    center_x = x + grid_size[0] / 2
                    center_y = y + grid_size[1] / 2
                    # Top-left corner: (-width_in_pt / 2, -height_in_pt / 2) after rotation
                    tl_x = center_x - height_in_pt / 2
                    tl_y = center_y + width_in_pt / 2
                    # Top-right corner: (-width_in_pt / 2, height_in_pt / 2)
                    tr_x = center_x + height_in_pt / 2
                    tr_y = center_y + width_in_pt / 2
                    # Bottom-left corner: (width_in_pt / 2, -height_in_pt / 2)
                    bl_x = center_x - height_in_pt / 2
                    bl_y = center_y - width_in_pt / 2
                    # Bottom-right corner: (width_in_pt / 2, height_in_pt / 2)
                    br_x = center_x + height_in_pt / 2
                    br_y = center_y - width_in_pt / 2
                    cut_helper_x.update([tl_x, tr_x, bl_x, br_x])
                    cut_helper_y.update([tl_y, tr_y, bl_y, br_y])
                else:
                    cut_helper_x.update([x, x + width_in_pt])
                    cut_helper_y.update([y, y + height_in_pt])

            c.saveState()

            if neutral_template == "vertical":
                c.translate(x + grid_size[0] / 2, y + grid_size[1] / 2)
                c.rotate(270)

                c.drawImage(
                    cards[card_idx],
                    -scaled_width / 2,
                    -scaled_height / 2,
                    width=scaled_width,
                    height=scaled_height,
                )

                if print_outlines:
                    c.setStrokeColor(black)
                    c.setLineWidth(0.2)
                    c.roundRect(
                        -width_in_pt / 2,
                        -height_in_pt / 2,
                        width_in_pt,
                        height_in_pt,
                        radius=35 / 4,
                    )
            else:
                c.drawImage(
                    cards[card_idx],
                    x + padding_x,
                    y + padding_y,
                    width=scaled_width,
                    height=scaled_height,
                )

                if print_outlines:
                    c.setStrokeColor(black)
                    c.setLineWidth(0.2)
                    c.roundRect(
                        x + padding_x,
                        y + padding_y,
                        width_in_pt,
                        height_in_pt,
                        radius=35 / 4,
                    )

            c.restoreState()

        if cut_marks == "crop":
            make_crop_marks()

        c.showPage()

    c.save()
