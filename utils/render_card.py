import base64
import os
from dataclasses import dataclass
from io import BytesIO

from cairosvg import svg2pdf  # type: ignore
from lxml import etree
from PIL import Image
from svgpathtools import parse_path  # type: ignore

from utils.prepare_pdf import from_pixels_to_point

FRAME_META_SELECTOR = ".//svg:path[@inkscape:label='Artwork-Frame']"
ARTWORK_REPLACE_SELECTOR = (
    ".//svg:path[@id='Artwork-Frame-bg' or @inkscape:label='Artwork-Frame-bg']"
)

# Card media, matching zaparoo-designer's NFCCCsizeCard: 85mm x 54mm. These are
# the physical card dimensions, so they are deliberately not taken from the
# template viewBox - the templates are authored at 619x994 and the designer
# stretches them onto this media.
CARD_MEDIA_PX = (638, 1004)  # (short edge, long edge) at 300 DPI


@dataclass(frozen=True)
class Job:
    system: str
    game: str
    cover_path: str
    template_path: str


@dataclass(frozen=True)
class TemplateMeta:
    frame_width: int
    x: float
    y: float
    target_height: int
    card_size_in_pt: tuple[float, float]


_template_meta_cache: dict[str, TemplateMeta] = {}
_template_bytes_cache: dict[str, bytes] = {}


def _build_nsmap(root):
    nsmap = {k if k else "svg": v for k, v in root.nsmap.items()}
    nsmap.setdefault("svg", "http://www.w3.org/2000/svg")
    nsmap.setdefault("inkscape", "http://www.inkscape.org/namespaces/inkscape")
    nsmap.setdefault("xlink", "http://www.w3.org/1999/xlink")
    return nsmap


def _xpath(root, nsmap, path):
    return root.xpath(path, namespaces=nsmap)


def get_template_meta(svg_path):
    cached = _template_meta_cache.get(svg_path)
    if cached is not None:
        return cached

    tree = etree.parse(svg_path)
    root = tree.getroot()
    nsmap = _build_nsmap(root)

    path_el = _xpath(root, nsmap, FRAME_META_SELECTOR)

    if not path_el:
        raise ValueError("Artwork frame path not found in SVG")

    d = path_el[0].attrib["d"]
    path = parse_path(d)
    xmin, xmax, _, _ = path.bbox()
    frame_width = int(xmax - xmin) - 4

    doc_width = frame_width
    if "viewBox" in root.attrib:
        viewbox = root.attrib["viewBox"].split()
        if len(viewbox) >= 3:
            doc_width = float(viewbox[2])
    elif "width" in root.attrib:
        width_str = root.attrib["width"]
        if width_str.endswith("px"):
            doc_width = float(width_str.replace("px", ""))

    short_edge_px, long_edge_px = CARD_MEDIA_PX
    card_size_in_pt = (
        from_pixels_to_point(short_edge_px),
        from_pixels_to_point(long_edge_px),
    )

    meta = TemplateMeta(
        frame_width=frame_width,
        x=(doc_width - frame_width) / 2,
        y=252.454,
        target_height=721,
        card_size_in_pt=card_size_in_pt,
    )
    _template_meta_cache[svg_path] = meta
    return meta


def _load_template_root(svg_path):
    svg_bytes = _template_bytes_cache.get(svg_path)
    if svg_bytes is None:
        with open(svg_path, "rb") as f:
            svg_bytes = f.read()
        _template_bytes_cache[svg_path] = svg_bytes

    parser_local = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(svg_bytes, parser=parser_local)
    return root


def _is_fresh_output(output_path, input_paths):
    if not os.path.exists(output_path):
        return False

    output_mtime = os.path.getmtime(output_path)
    for input_path in input_paths:
        if os.path.getmtime(input_path) > output_mtime:
            return False
    return True


def _cache_output_path(job, cache_dir):
    img_filename = os.path.basename(job.cover_path)
    img_stem = os.path.splitext(img_filename)[0]
    template_stem = os.path.splitext(os.path.basename(job.template_path))[0]
    system_dir = os.path.join(cache_dir, job.system)
    os.makedirs(system_dir, exist_ok=True)
    return os.path.join(system_dir, f"temp_{img_stem}__{template_stem}.pdf")


def render_card(job, cache_dir, use_cache=True):
    meta = get_template_meta(job.template_path)
    output_pdf_path = _cache_output_path(job, cache_dir)

    if use_cache and _is_fresh_output(
        output_pdf_path, [job.cover_path, job.template_path]
    ):
        return output_pdf_path, True

    root = _load_template_root(job.template_path)
    nsmap = _build_nsmap(root)
    svg_ns = nsmap["svg"]
    xlink_ns = nsmap["xlink"]

    placeholder_elements = _xpath(
        root, nsmap, ".//svg:image[@inkscape:label='placeholder']"
    )
    for elem in placeholder_elements:
        style = elem.attrib.get("style", "")
        if "display:inline" in style:
            elem.attrib["style"] = style.replace(
                "display:inline", "display:none"
            ).strip("; ")

    artwork_nodes = _xpath(root, nsmap, ARTWORK_REPLACE_SELECTOR)
    artwork_element = artwork_nodes[0] if artwork_nodes else None

    if artwork_element is None:
        raise ValueError(f"Artwork path not found in template {job.template_path}")

    with Image.open(job.cover_path) as img:
        img_width, img_height = img.size
        scale = meta.target_height / img_height
        new_width = int(img_width * scale)
        img_resized = img.resize(
            (new_width, meta.target_height), Image.Resampling.BICUBIC
        )

        final_img = Image.new(
            "RGBA", (meta.frame_width, meta.target_height), (0, 0, 0, 255)
        )
        paste_x = (meta.frame_width - new_width) // 2
        final_img.paste(img_resized, (paste_x, 0))

    png_buffer = BytesIO()
    final_img.save(png_buffer, format="PNG")
    image_data_base64 = base64.b64encode(png_buffer.getvalue()).decode("ascii")

    image_el = etree.Element(f"{{{svg_ns}}}image", nsmap=nsmap)
    image_el.set("id", "Cover-Art")
    image_el.set("x", str(meta.x))
    image_el.set("y", str(meta.y - 1))
    image_el.set("width", str(meta.frame_width))
    image_el.set("height", str(meta.target_height))
    image_el.set(f"{{{xlink_ns}}}href", f"data:image/png;base64,{image_data_base64}")
    image_el.set("preserveAspectRatio", "xMidYMid slice")

    parent = artwork_element.getparent()
    if parent is None:
        raise ValueError(f"Artwork parent not found in template {job.template_path}")
    parent.replace(artwork_element, image_el)

    # Cairo sizes the PDF page from the root width/height, so pin it to the
    # card's printed size. That keeps one SVG user unit equal to 1/300in, which
    # puts the embedded cover art at 300 DPI with no resampling.
    card_width_pt, card_height_pt = meta.card_size_in_pt
    root.set("width", f"{card_width_pt:.4f}pt")
    root.set("height", f"{card_height_pt:.4f}pt")

    svg2pdf(
        bytestring=etree.tostring(root, xml_declaration=True, encoding="UTF-8"),
        write_to=output_pdf_path,
        background_color="white",
    )

    return output_pdf_path, False
