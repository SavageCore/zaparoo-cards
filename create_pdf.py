import argparse
import base64
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO

from cairosvg import svg2png  # type: ignore
from lxml import etree
from PIL import Image
from svgpathtools import parse_path  # type: ignore
from yaspin import yaspin

from utils.prepare_pdf import prepare_pdf  # type: ignore

# Base directories
cards_dir = "Cards"
covers_dir = "GameCovers"
tmp_dir = "tmp_artwork"

FRAME_META_SELECTOR = ".//svg:path[@inkscape:label='Artwork-Frame']"
ARTWORK_REPLACE_SELECTOR = ".//svg:path[@id='Artwork-Frame-bg' or @inkscape:label='Artwork-Frame-bg']"
default_cache_dir = os.path.join(".cache", "zaparoo-cards", "rendered")
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png")


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


_template_choice_cache: dict[str, str] = {}
_template_meta_cache: dict[str, TemplateMeta] = {}
_template_bytes_cache: dict[str, bytes] = {}


parser = argparse.ArgumentParser(description="Generate PDF with game covers.")
parser.add_argument("--crop", action="store_true", help="Enable crop marks")
parser.add_argument("--outline", action="store_true", help="Enable outline")
parser.add_argument(
    "--both", action="store_true", help="Enable both crop marks and outline"
)
parser.add_argument("--full", action="store_true", help="Enable full card print")
parser.add_argument(
    "--limit",
    type=int,
    nargs="?",
    const=10,
    default=None,
    help="Limit the number of cards to process (default: 10 if no value specified)",
)
parser.add_argument(
    "--systems",
    type=str,
    nargs="*",
    default=None,
    help="List of systems to process (default: all systems in GameCovers directory)",
)
parser.add_argument(
    "--keep",
    action="store_true",
    default=False,
    help="Keep temporary files after processing",
)
parser.add_argument(
    "--workers",
    type=int,
    default=max(1, min(8, os.cpu_count() or 1)),
    help="Number of parallel workers used for card rendering",
)
parser.add_argument(
    "--no-cache",
    action="store_true",
    help="Disable card PNG reuse if existing outputs are already fresh",
)
parser.add_argument(
    "--cache-dir",
    type=str,
    default=default_cache_dir,
    help="Directory used for persistent rendered card cache",
)
parser.add_argument(
    "--render-only",
    action="store_true",
    help="Render card PNGs only and skip PDF generation",
)
parser.add_argument(
    "--benchmark",
    action="store_true",
    help="Print per-stage timing summary",
)
parser.add_argument(
    "--example",
    action="store_true",
    help="Generate output_example.pdf with one card per system and one card per N64 colour template",
)

args = parser.parse_args()


def resolve_print_options():
    print_outlines = False
    cut_marks = None
    full_print = False

    if (args.crop and args.outline) or args.both:
        cut_marks = "crop"
        print_outlines = True
    elif args.crop:
        cut_marks = "crop"
    elif args.outline:
        print_outlines = True

    if args.full:
        full_print = True
        cut_marks = None
        print_outlines = False

    return print_outlines, cut_marks, full_print


def _build_nsmap(root):
    nsmap = {k if k else "svg": v for k, v in root.nsmap.items()}
    nsmap.setdefault("svg", "http://www.w3.org/2000/svg")
    nsmap.setdefault("inkscape", "http://www.inkscape.org/namespaces/inkscape")
    nsmap.setdefault("xlink", "http://www.w3.org/1999/xlink")
    return nsmap


def _xpath(root, nsmap, path):
    return root.xpath(path, namespaces=nsmap)


def get_template_path(game, system):
    config_path = os.path.join(covers_dir, system, f"{game}.json")
    template = _template_choice_cache.get(config_path)
    if template is None:
        template = f"{system}.svg"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                template = config.get("template", template)
        _template_choice_cache[config_path] = template
    return os.path.join(cards_dir, template)


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

    meta = TemplateMeta(
        frame_width=frame_width,
        x=(doc_width - frame_width) / 2,
        y=252.454,
        target_height=721,
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


def _cache_output_path(job):
    img_filename = os.path.basename(job.cover_path)
    img_stem = os.path.splitext(img_filename)[0]
    template_stem = os.path.splitext(os.path.basename(job.template_path))[0]
    system_dir = os.path.join(args.cache_dir, job.system)
    os.makedirs(system_dir, exist_ok=True)
    return os.path.join(system_dir, f"temp_{img_stem}__{template_stem}.png")


def render_card(job, use_cache=True):
    meta = get_template_meta(job.template_path)
    output_png_path = _cache_output_path(job)

    if use_cache and _is_fresh_output(output_png_path, [job.cover_path, job.template_path]):
        return output_png_path, True

    root = _load_template_root(job.template_path)
    nsmap = _build_nsmap(root)
    svg_ns = nsmap["svg"]
    xlink_ns = nsmap["xlink"]

    placeholder_elements = _xpath(root, nsmap, ".//svg:image[@inkscape:label='placeholder']")
    for elem in placeholder_elements:
        style = elem.attrib.get("style", "")
        if "display:inline" in style:
            elem.attrib["style"] = style.replace("display:inline", "display:none").strip("; ")

    artwork_nodes = _xpath(root, nsmap, ARTWORK_REPLACE_SELECTOR)
    artwork_element = artwork_nodes[0] if artwork_nodes else None

    if artwork_element is None:
        raise ValueError(f"Artwork path not found in template {job.template_path}")

    with Image.open(job.cover_path) as img:
        img_width, img_height = img.size
        scale = meta.target_height / img_height
        new_width = int(img_width * scale)
        img_resized = img.resize((new_width, meta.target_height), Image.Resampling.BICUBIC)

        final_img = Image.new("RGBA", (meta.frame_width, meta.target_height), (0, 0, 0, 255))
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

    svg2png(
        bytestring=etree.tostring(root, xml_declaration=True, encoding="UTF-8"),
        write_to=output_png_path,
        background_color="white",
    )

    return output_png_path, False


def collect_jobs():
    jobs = []
    systems = sorted(os.listdir(covers_dir))
    wanted_systems = set(args.systems) if args.systems else None

    for system in systems:
        if wanted_systems and system not in wanted_systems:
            continue
        system_path = os.path.join(covers_dir, system)
        if not os.path.isdir(system_path):
            continue

        for filename in sorted(os.listdir(system_path)):
            if not filename.lower().endswith(COVER_EXTENSIONS):
                continue

            game = os.path.splitext(filename)[0]
            template_path = get_template_path(game, system)
            cover_path = os.path.join(system_path, filename)

            if os.path.exists(template_path) and os.path.exists(cover_path):
                jobs.append(
                    Job(
                        system=system,
                        game=game,
                        cover_path=cover_path,
                        template_path=template_path,
                    )
                )
            else:
                print(f"Template or cover image not found for {game} on {system}")

            if args.limit is not None and len(jobs) >= args.limit:
                return jobs

    return jobs


def _first_cover_file(system_path):
    for filename in sorted(os.listdir(system_path)):
        if filename.lower().endswith(COVER_EXTENSIONS):
            return filename
    return None


def _collect_n64_example_jobs(system_path):
    jobs = []
    missing_template_mappings = []
    covers = [
        filename
        for filename in sorted(os.listdir(system_path))
        if filename.lower().endswith(COVER_EXTENSIONS)
    ]
    if not covers:
        return jobs

    base_jobs_by_template = {}
    all_cover_jobs = []
    for filename in covers:
        game = os.path.splitext(filename)[0]
        template_path = get_template_path(game, "n64")
        cover_path = os.path.join(system_path, filename)
        if os.path.exists(template_path) and os.path.exists(cover_path):
            job = Job(
                system="n64",
                game=game,
                cover_path=cover_path,
                template_path=template_path,
            )
            all_cover_jobs.append(job)
            base_jobs_by_template.setdefault(os.path.basename(template_path), []).append(job)

    n64_template_variants = []
    base_template = "n64.svg"
    if os.path.exists(os.path.join(cards_dir, base_template)):
        n64_template_variants.append(base_template)

    n64_template_variants.extend(
        sorted(
            filename
            for filename in os.listdir(cards_dir)
            if filename.startswith("n64_") and filename.endswith(".svg")
        )
    )

    if not n64_template_variants:
        if base_jobs_by_template:
            first_template = sorted(base_jobs_by_template.keys())[0]
            jobs.append(base_jobs_by_template[first_template][0])
        return jobs

    used_cover_paths = set()

    for template_filename in n64_template_variants:
        template_path = os.path.join(cards_dir, template_filename)
        if not os.path.exists(template_path):
            continue

        matching_jobs = base_jobs_by_template.get(template_filename)
        if matching_jobs:
            selected = next(
                (job for job in matching_jobs if job.cover_path not in used_cover_paths),
                matching_jobs[0],
            )
            used_cover_paths.add(selected.cover_path)
            jobs.append(selected)
            continue

        missing_template_mappings.append(template_filename)
        fallback_source = next(
            (job for job in all_cover_jobs if job.cover_path not in used_cover_paths),
            all_cover_jobs[0] if all_cover_jobs else None,
        )
        if fallback_source is not None:
            used_cover_paths.add(fallback_source.cover_path)
            jobs.append(
                Job(
                    system="n64",
                    game=fallback_source.game,
                    cover_path=fallback_source.cover_path,
                    template_path=template_path,
                )
            )

    if missing_template_mappings:
        print(
            "Warning: no explicit N64 game mapping found for template(s): "
            + ", ".join(missing_template_mappings)
            + ". Using fallback games for those colours in --example mode."
        )

    return jobs


def collect_example_jobs():
    jobs = []
    systems = sorted(os.listdir(covers_dir))

    for system in systems:
        system_path = os.path.join(covers_dir, system)
        if not os.path.isdir(system_path):
            continue

        if system == "n64":
            jobs.extend(_collect_n64_example_jobs(system_path))
            continue

        filename = _first_cover_file(system_path)
        if not filename:
            continue

        game = os.path.splitext(filename)[0]
        template_path = get_template_path(game, system)
        cover_path = os.path.join(system_path, filename)

        if os.path.exists(template_path) and os.path.exists(cover_path):
            jobs.append(
                Job(
                    system=system,
                    game=game,
                    cover_path=cover_path,
                    template_path=template_path,
                )
            )
        else:
            print(f"Template or cover image not found for {game} on {system}")

    return jobs


def process_jobs(jobs):
    card_images = [None] * len(jobs)
    cached_hits = 0
    workers = max(1, args.workers)

    with yaspin(text=f"Rendering {len(jobs)} cards...", color="cyan") as spinner:
        try:
            if workers == 1:
                for i, job in enumerate(jobs):
                    output_path, was_cached = render_card(job, use_cache=not args.no_cache)
                    card_images[i] = output_path
                    cached_hits += int(was_cached)
            else:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_index = {
                        executor.submit(render_card, job, not args.no_cache): i
                        for i, job in enumerate(jobs)
                    }
                    for future in as_completed(future_to_index):
                        i = future_to_index[future]
                        output_path, was_cached = future.result()
                        card_images[i] = output_path
                        cached_hits += int(was_cached)

            spinner.ok("✅ ")
        except Exception as e:
            spinner.fail("💥 ")
            raise RuntimeError(f"Failed to render card images: {e}") from e

    print(f"Rendered {len(jobs)} cards ({cached_hits} cached, {len(jobs) - cached_hits} new).")
    return [path for path in card_images if path is not None]


def print_benchmark(stage_times, card_count):
    total = stage_times.get("total", 0.0)
    discover = stage_times.get("discover", 0.0)
    render = stage_times.get("render", 0.0)
    pdf = stage_times.get("pdf", 0.0)
    per_card = (render / card_count) if card_count else 0.0

    print("\nBenchmark summary")
    print(f"- discover: {discover:.3f}s")
    print(f"- render:   {render:.3f}s ({per_card:.4f}s/card)")
    print(f"- pdf:      {pdf:.3f}s")
    print(f"- total:    {total:.3f}s")


def main():
    total_start = time.perf_counter()
    stage_times = {}

    print_outlines, cut_marks, full_print = resolve_print_options()
    output_pdf_path = "output_example.pdf" if args.example else "output.pdf"

    discover_start = time.perf_counter()
    jobs = collect_example_jobs() if args.example else collect_jobs()
    stage_times["discover"] = time.perf_counter() - discover_start
    if not jobs:
        print("No valid card images found to process.")
        return

    if args.example:
        print(f"Example mode selected {len(jobs)} cards.")

    os.makedirs(args.cache_dir, exist_ok=True)

    render_start = time.perf_counter()
    card_images = process_jobs(jobs)
    stage_times["render"] = time.perf_counter() - render_start

    if args.render_only:
        print("Skipping PDF generation (--render-only).")
        stage_times["pdf"] = 0.0
        stage_times["total"] = time.perf_counter() - total_start
        if args.benchmark:
            print_benchmark(stage_times, len(card_images))
        if os.path.exists(tmp_dir) and not args.keep:
            shutil.rmtree(tmp_dir)
        return

    if card_images:
        pdf_start = time.perf_counter()
        with yaspin(text="Generating PDF with card images...", color="cyan") as spinner:
            try:
                prepare_pdf(
                    card_images,
                    print_outlines=print_outlines,
                    cut_marks=cut_marks,
                    full_print=full_print,
                    output_path=output_pdf_path,
                )
                spinner.ok("✅ ")
            except Exception as e:
                spinner.fail("💥 ")
                print(f"Failed to generate PDF: {e}")
        stage_times["pdf"] = time.perf_counter() - pdf_start

    if os.path.exists(tmp_dir) and not args.keep:
        shutil.rmtree(tmp_dir)

    stage_times["total"] = time.perf_counter() - total_start
    if args.benchmark:
        print_benchmark(stage_times, len(card_images))


if __name__ == "__main__":
    main()