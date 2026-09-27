import argparse
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from yaspin import yaspin

from utils.prepare_pdf import prepare_pdf  # type: ignore
from utils.render_card import (  # type: ignore
    Job,
    get_template_meta,
    render_card as render_card_to_pdf,
)

# Base directories
cards_dir = "Cards"
covers_dir = "GameCovers"
tmp_dir = "tmp_artwork"

default_cache_dir = os.path.join(".cache", "zaparoo-cards", "rendered")
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png")

_template_choice_cache: dict[str, str] = {}


parser = argparse.ArgumentParser(description="Generate PDF with game covers.")
parser.add_argument("--crop", action="store_true", help="Enable crop marks")
parser.add_argument("--outline", action="store_true", help="Enable outline")
parser.add_argument(
    "--both", action="store_true", help="Enable both crop marks and outline"
)
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

    if (args.crop and args.outline) or args.both:
        cut_marks = "crop"
        print_outlines = True
    elif args.crop:
        cut_marks = "crop"
    elif args.outline:
        print_outlines = True

    return print_outlines, cut_marks


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


def render_card(job, use_cache=True):
    return render_card_to_pdf(job, args.cache_dir, use_cache=use_cache)


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
    card_pdfs = [None] * len(jobs)
    cached_hits = 0
    workers = max(1, args.workers)

    with yaspin(text=f"Rendering {len(jobs)} cards...", color="cyan") as spinner:
        try:
            if workers == 1:
                for i, job in enumerate(jobs):
                    output_path, was_cached = render_card(job, use_cache=not args.no_cache)
                    card_pdfs[i] = output_path
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
                        card_pdfs[i] = output_path
                        cached_hits += int(was_cached)

            spinner.ok("✅ ")
        except Exception as e:
            spinner.fail("💥 ")
            raise RuntimeError(f"Failed to render card images: {e}") from e

    print(f"Rendered {len(jobs)} cards ({cached_hits} cached, {len(jobs) - cached_hits} new).")
    return [path for path in card_pdfs if path is not None]


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

    print_outlines, cut_marks = resolve_print_options()
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
    card_pdfs = process_jobs(jobs)
    stage_times["render"] = time.perf_counter() - render_start

    if args.render_only:
        print("Skipping PDF generation (--render-only).")
        stage_times["pdf"] = 0.0
        stage_times["total"] = time.perf_counter() - total_start
        if args.benchmark:
            print_benchmark(stage_times, len(card_pdfs))
        if os.path.exists(tmp_dir) and not args.keep:
            shutil.rmtree(tmp_dir)
        return

    if card_pdfs:
        # Every template shares a viewBox, so the first job defines the sheet's
        # card box for all of them.
        card_size_in_pt = get_template_meta(jobs[0].template_path).card_size_in_pt
        pdf_start = time.perf_counter()
        with yaspin(text="Generating PDF with card images...", color="cyan") as spinner:
            try:
                prepare_pdf(
                    card_pdfs,
                    card_size_in_pt,
                    print_outlines=print_outlines,
                    cut_marks=cut_marks,
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
        print_benchmark(stage_times, len(card_pdfs))


if __name__ == "__main__":
    main()