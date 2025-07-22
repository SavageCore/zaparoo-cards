import base64
import hashlib
import json
import os
import subprocess

from lxml import etree
from PIL import Image, ImageDraw
from svgpathtools import parse_path  # type: ignore

# Base directories
cards_dir = "Cards"
covers_dir = "GameCovers"

inkscape_path = r"C:\Program Files\Inkscape\bin\inkscape.exe"


def get_template_path(game, system):
    config_path = os.path.join(covers_dir, system, f"{game}.json")
    template = f"hucard_{system}.svg"

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
    frame_width = int(xmax - xmin)
    frame_height = int(ymax - ymin)
    x = xmin
    y = ymin

    img = Image.open(image_path)
    img_filename = os.path.basename(image_path)

    img_hash = hashlib.md5(img_filename.encode()).hexdigest()
    if not os.path.exists("tmp_artwork"):
        os.makedirs("tmp_artwork")

    if os.path.exists(f"tmp_artwork/temp_{img_hash}.svg"):
        print(f"Using cached SVG for {img_filename}")
        return

    img_width, img_height = img.size

    # Scale image to frame width, then crop vertically to frame height
    scale = frame_height / img_height
    new_height = frame_height
    new_width = int(img_width * scale)
    img_resized = img.resize((new_width, new_height), Image.Resampling.BICUBIC)

    # Center crop or pad with black bars
    if new_width > frame_width:
        # Crop horizontally to frame width, centering the crop
        left = (new_width - frame_width) // 2
        right = left + frame_width
        img_cropped = img_resized.crop((left, 0, right, frame_height))
    else:
        # Pad with black bars left and right
        img_cropped = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 255))
        paste_x = (frame_width - new_width) // 2
        img_cropped.paste(img_resized, (paste_x, 0))

    # --- Add rounded corners mask ---
    radius = int(
        min(frame_width, frame_height) * 0.045
    )  # Adjust as needed for your design
    mask = Image.new("L", (frame_width, frame_height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [(0, 0), (frame_width, frame_height)], radius=radius, fill=255
    )
    img_cropped.putalpha(mask)
    # --- End rounded corners mask ---

    img_cropped.save(f"tmp_artwork/temp_{img_hash}.png", "PNG")

    # Insert <image> element with correct x, y, width, height
    image_el = etree.Element(f"{{{svg_ns}}}image", nsmap=nsmap)
    image_el.set("id", "Cover-Art")
    image_el.set("x", str(x))
    image_el.set("y", str(y))
    image_el.set("width", str(frame_width))
    image_el.set("height", str(frame_height))
    with open(f"tmp_artwork/temp_{img_hash}.png", "rb") as img:
        image_data = img.read()
    image_data_base64 = base64.b64encode(image_data).decode("utf-8")
    image_el.set(f"{{{xlink_ns}}}href", f"data:image/png;base64,{image_data_base64}")
    image_el.set("preserveAspectRatio", "xMidYMid slice")

    # Remove the temporary image file
    os.remove(f"tmp_artwork/temp_{img_hash}.png")

    parent.replace(elem, image_el)

    # Save the modified SVG
    temp_svg_path = f"tmp_artwork/temp_{img_hash}.svg"
    tree.write(temp_svg_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")

    # Convert SVG to PDF using Inkscape
    result = subprocess.run(
        [
            inkscape_path,
            temp_svg_path,
            "--export-type=pdf",
            f"--export-filename=tmp_artwork/temp_{img_hash}.pdf",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        print("Error occurred while converting SVG to PDF:")
        print(result.stderr.decode())
        return

    # Convert the SVG to PNG using Inkscape
    result = subprocess.run(
        [
            inkscape_path,
            temp_svg_path,
            "--export-type=png",
            f"--export-filename=tmp_artwork/temp_{img_hash}.png",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        print("Error occurred while converting SVG to PNG:")
        print(result.stderr.decode())
        return

    return img_hash


# Process all files and generate PDF with ReportLab
card_images = []
for system in os.listdir(covers_dir):
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
                    hash = replace_path_with_image(template_path, cover_path)
                    card_images.append(f"tmp_artwork/temp_{hash}.pdf")
                else:
                    print(f"Template or cover image not found for {game} on {system}")

                print("")

# Clean up temporary files
# tmp_dir = "tmp_artwork"
# if os.path.exists(tmp_dir):
#     for file in os.listdir(tmp_dir):
#         file_path = os.path.join(tmp_dir, file)
#         if os.path.isfile(file_path):
#             os.remove(file_path)
