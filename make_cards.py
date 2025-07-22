import os
import json
from PIL import Image
from lxml import etree

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
    height = 577 * aspect_ratio - 47  # trim 47px overhang

    # Resize and save temporary image
    img_resized = img.resize((577, int(height)), Image.Resampling.LANCZOS)
    img_resized.convert("RGB").save("temp.png")

    # Insert <image> element
    image_el = etree.Element(f"{{{svg_ns}}}image", nsmap=nsmap)
    image_el.set("x", str(x))
    image_el.set("y", str(y))
    image_el.set("width", str(577))
    image_el.set("height", str(height))
    image_el.set(f"{{{xlink_ns}}}href", "temp.png")
    image_el.set("preserveAspectRatio", "xMidYMid slice")

    # parent.append(image_el)
    parent.replace(elem, image_el)

    # Save the modified SVG next to the cover image
    # So we have Tony Hawk's Pro Skater.svg for example
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
                    replace_path_with_image(template_path, cover_path)
                else:
                    print(f"Template or cover image not found for {game} on {system}")
