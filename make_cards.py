import base64
import json
import os

from lxml import etree
from PIL import Image

# Base directories
cards_dir = "Cards"
covers_dir = "GameCovers"


def get_template_path(game, system):
    config_path = os.path.join(covers_dir, system, f"{game}.json")
    template = f"hucard_{system}.svg"

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            if "template" in config:
                template = config["template"]

    return os.path.join(cards_dir, template)


def replace_path_with_image(svg_path, image_path, game):
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

    # Calculate image size
    x, y = 20.425, 250.525
    img = Image.open(image_path)
    img_width, img_height = img.size
    aspect_ratio = img_height / img_width
    target_height = 577 * aspect_ratio - 47  # trim 47px overhang

    # Resize and crop image losslessly using PNG
    img_resized = img.resize((577, int(577 * aspect_ratio)), Image.Resampling.BICUBIC)
    # Crop the bottom 47px
    crop_box = (0, 0, 577, int(target_height))
    img_cropped = img_resized.crop(crop_box)
    img_cropped.save(f"tmp_artwork/temp_{game}.png", "PNG")  # Save as PNG for lossless

    # Insert <image> element with ID "Cover-Art"
    image_el = etree.Element(f"{{{svg_ns}}}image", nsmap=nsmap)
    image_el.set("id", "Cover-Art")
    image_el.set("x", str(x))
    image_el.set("y", str(y))
    image_el.set("width", str(577))
    image_el.set("height", str(target_height))
    # Embed the image directly in the SVG
    with open(f"tmp_artwork/temp_{game}.png", "rb") as img:
        image_data = img.read()
    image_data_base64 = base64.b64encode(image_data).decode("utf-8")
    image_el.set(f"{{{xlink_ns}}}href", f"data:image/png;base64,{image_data_base64}")
    image_el.set("preserveAspectRatio", "xMidYMid slice")

    parent.replace(elem, image_el)

    # Save the modified SVG next to the cover image
    output_path = os.path.splitext(image_path)[0] + ".svg"
    tree.write(output_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    print(f"Saved: {output_path}")


# Process all files in GameCovers
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
                print("")
                cover_path = os.path.join(system_path, filename)
                if os.path.exists(template_path) and os.path.exists(cover_path):
                    replace_path_with_image(template_path, cover_path, game)
                else:
                    print(f"Template or cover image not found for {game} on {system}")

# Empty the temporary directory
tmp_dir = "tmp_artwork"
if os.path.exists(tmp_dir):
    for file in os.listdir(tmp_dir):
        file_path = os.path.join(tmp_dir, file)
        if os.path.isfile(file_path):
            os.remove(file_path)
