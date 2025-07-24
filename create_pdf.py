import argparse
import base64
import hashlib
import json
import os
import shutil

from cairosvg import svg2png  # type: ignore
from lxml import etree
from PIL import Image
from svgpathtools import parse_path  # type: ignore
from yaspin import yaspin

from utils.prepare_pdf import prepare_pdf  # type: ignore

# Base directories
cards_dir = "Cards"
covers_dir = "GameCovers"

parser = argparse.ArgumentParser(description="Generate PDF with game covers.")
parser.add_argument("--crop", action="store_true", help="Enable crop marks")
parser.add_argument("--outline", action="store_true", help="Enable outline")
parser.add_argument(
    "--both", action="store_true", help="Enable both crop marks and outline"
)
# Add argument to specify full card print without the white border, for printing directly on cards
parser.add_argument("--full", action="store_true", help="Enable full card print")
# Add argurment to limit the number of cards to process for testing purposes
parser.add_argument(
    "--limit",
    type=int,
    nargs="?",
    const=10,
    default=None,
    help="Limit the number of cards to process (default: 10 if no value specified)",
)
# Add argument to specify list of systems to process
parser.add_argument(
    "--systems",
    type=str,
    nargs="*",
    default=None,
    help="List of systems to process (default: all systems in GameCovers directory)",
)

# Set up crop marks and outlines based on arguments
print_outlines = False
cut_marks = None
full_print = False

args = parser.parse_args()
if (args.crop and args.outline) or args.both:
    cut_marks = "crop"
    print_outlines = True
elif args.crop:
    cut_marks = "crop"
elif args.outline:
    print_outlines = True
else:
    cut_marks = None

if args.full:
    full_print = True
    cut_marks = None
    print_outlines = False


def get_template_path(game, system):
    config_path = os.path.join(covers_dir, system, f"{game}.json")
    template = f"{system}.svg"

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            if "template" in config:
                template = config["template"]

    return os.path.join(cards_dir, template)


def get_path_bbox(svg_path):
    # Parse the SVG and get the path's bounding box
    tree = etree.parse(svg_path)
    root = tree.getroot()
    nsmap = {k if k else "svg": v for k, v in root.nsmap.items()}

    def xpath(path):
        return root.xpath(path, namespaces=nsmap)

    path_el = xpath(".//svg:path[@inkscape:label='Artwork-Frame1']")
    if not path_el:
        raise ValueError("Artwork-Frame1 not found in SVG.")
    d = path_el[0].attrib["d"]
    # Use svgpathtools to get the bounding box
    path = parse_path(d)
    xmin, xmax, ymin, ymax = path.bbox()
    return xmin, ymin, xmax, ymax


def replace_path_with_image(svg_path, image_path):
    # Load SVG using lxml
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(svg_path, parser)
    root = tree.getroot()

    # Namespace handling
    nsmap = {k if k else "svg": v for k, v in root.nsmap.items()}
    svg_ns = nsmap["svg"]
    xlink_ns = nsmap.get("xlink", "http://www.w3.org/1999/xlink")

    def xpath(path):
        return root.xpath(path, namespaces=nsmap)

    # Hide inkscape:label="placeholder"
    placeholder_elements = xpath(".//svg:image[@inkscape:label='placeholder']")
    for elem in placeholder_elements:
        style = elem.attrib.get("style", "")
        new_style = style.replace("display:inline", "display:none").strip("; ")
        elem.attrib["style"] = new_style

    # Find the path to replace
    artwork_path = xpath(".//svg:path[@id='Artwork-Frame']")
    if not artwork_path:
        print("Artwork path not found.")
        return

    elem = artwork_path[0]
    parent = elem.getparent()

    xmin, ymin, xmax, ymax = get_path_bbox(svg_path)
    frame_width = int(xmax - xmin) - 4

    # Get document width from viewBox or width attribute
    doc_width = frame_width  # Default to frame_width as fallback
    if "viewBox" in root.attrib:
        viewbox = root.attrib["viewBox"].split()
        if len(viewbox) >= 3:
            doc_width = float(viewbox[2])  # Width is the third value in viewBox
    elif "width" in root.attrib:
        width_str = root.attrib["width"]
        if width_str.endswith("px"):
            doc_width = float(width_str.replace("px", ""))

    x = (doc_width - frame_width) / 2  # Center frame within document
    y = 252.454  # Exact y from Inkscape

    img = Image.open(image_path)
    img_filename = os.path.basename(image_path)

    img_hash = hashlib.md5(img_filename.encode()).hexdigest()
    if not os.path.exists("tmp_artwork"):
        os.makedirs("tmp_artwork")

    if os.path.exists(f"tmp_artwork/temp_{img_filename}.svg"):
        print(f"Using cached SVG for {img_filename}")
        return

    img_width, img_height = img.size

    # Scale image vertically to match the fixed height of 721 px
    target_height = 721
    scale = target_height / img_height
    new_height = int(target_height)
    new_width = int(img_width * scale)

    img_resized = img.resize((new_width, new_height), Image.Resampling.BICUBIC)

    # Create a new image with frame_width and target_height, filling with black
    final_img = Image.new("RGBA", (frame_width, int(target_height)), (0, 0, 0, 255))
    paste_x = (frame_width - new_width) // 2  # Center within frame width
    paste_y = 0  # Align with top
    final_img.paste(img_resized, (paste_x, paste_y))

    # Save the final image
    final_img.save(f"tmp_artwork/temp_{img_hash}.png", "PNG")

    # Insert <image> element with correct x, y, width, height
    image_el = etree.Element(f"{{{svg_ns}}}image", nsmap=nsmap)
    image_el.set("id", "Cover-Art")
    image_el.set("x", str(x))
    image_el.set("y", str(y - 1))
    image_el.set("width", str(frame_width))
    image_el.set("height", str(target_height))  # Use exact height
    with open(f"tmp_artwork/temp_{img_hash}.png", "rb") as img:
        image_data = img.read()
    image_data_base64 = base64.b64encode(image_data).decode("utf-8")
    image_el.set(f"{{{xlink_ns}}}href", f"data:image/png;base64,{image_data_base64}")
    image_el.set("preserveAspectRatio", "xMidYMid slice")

    # Remove the temporary image file
    os.remove(f"tmp_artwork/temp_{img_hash}.png")

    parent.replace(elem, image_el)

    # Create system directory if it doesn't exist
    if not os.path.exists(f"tmp_artwork/{system}"):
        os.makedirs(f"tmp_artwork/{system}")

    # Save the modified SVG
    temp_svg_path = f"tmp_artwork/{system}/temp_{img_filename}.svg"
    tree.write(temp_svg_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")

    # Convert SVG to PNG using CairoSVG
    output_png_path = f"tmp_artwork/{system}/temp_{img_filename}.png"
    svg2png(url=temp_svg_path, write_to=output_png_path, background_color="white")

    return img_filename


# Create cards from templates and covers
for system in os.listdir(covers_dir):
    if args.systems and system not in args.systems:
        continue
    system_path = os.path.join(covers_dir, system)
    if os.path.isdir(system_path):
        for filename in os.listdir(system_path):
            if filename.lower().endswith((".jpg", ".jpeg")):
                game = os.path.splitext(filename)[0]
                template_path = get_template_path(game, system)
                print("")
                print(f"Processing {game} on {system}")
                print(f"Template path: {template_path}")
                cover_path = os.path.join(system_path, filename)
                if os.path.exists(template_path) and os.path.exists(cover_path):
                    replace_path_with_image(template_path, cover_path)
                else:
                    print(f"Template or cover image not found for {game} on {system}")

                print("")

card_images = []

# Collect card images from the temporary artwork directory to prepare for PDF generation
# Ensure they're alphabetically sorted by system and game name
for system in os.listdir("tmp_artwork"):
    system_path = os.path.join("tmp_artwork", system)
    if os.path.isdir(system_path):
        for filename in sorted(os.listdir(system_path)):
            if filename.lower().endswith(".png"):
                card_images.append(os.path.join(system_path, filename))

# Limit to specified number of cards for testing purposes
if args.limit is not None:
    print(f"Limiting to {args.limit} cards for testing.")
    card_images = card_images[: args.limit]

# Create a PDF with all card images
if card_images:
    with yaspin(text="Generating PDF with card images...", color="cyan") as spinner:
        try:
            prepare_pdf(
                card_images,
                print_outlines=print_outlines,
                cut_marks=cut_marks,
                full_print=full_print,
            )
            # prepare_pdf(card_images, print_outlines=False)
            spinner.ok("✅ ")
        except Exception as e:
            spinner.fail("💥 ")
            print(f"Failed to generate PDF: {e}")

# Clean up temporary files
tmp_dir = "tmp_artwork"
if os.path.exists(tmp_dir):
    shutil.rmtree(tmp_dir)
