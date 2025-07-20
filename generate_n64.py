import shutil
from pathlib import Path

from lxml import etree

# Define cartridge colours (main, text, shade)
cartridge_colors = {
    "Black": ("#2b2b2b", "#ffffff", "#222222"),
    "Blue": ("#0047ab", "#ffffff", "#003366"),
    "Gold": ("#ffd700", "#000000", "#a98c2c"),
    "Green": ("#2baf2b", "#000000", "#228c22"),
    "Red": ("#c80000", "#000000", "#a00000"),
    "Yellow": ("#ffd700", "#000000", "#ccac00"),
}


def create_n64_svg(base_svg_path: str, output_dir, colors: dict):
    created_files = []
    base_svg = Path(base_svg_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    for color_name, (cart_color, text_color, shade_color) in colors.items():
        output_path = output_dir / Path(f"hucard_n64_{color_name.lower()}.svg")
        shutil.copy(base_svg, output_path)

        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(str(output_path), parser)
        root = tree.getroot()

        # Assign a prefix to the default (svg) namespace
        nsmap = {k if k else "svg": v for k, v in root.nsmap.items()}

        def xpath(path):
            return root.xpath(path, namespaces=nsmap)

        def set_fill_by_id(id_value, fill_value):
            el = xpath(f".//svg:path[@id='{id_value}']")
            if el:
                el[0].attrib["style"] = f"fill:{fill_value};fill-opacity:1"

        def set_fill_by_inkscape_label(label_value, fill_value):
            el = xpath(f".//svg:path[@inkscape:label='{label_value}']")
            if el:
                el[0].attrib["style"] = f"fill:{fill_value};fill-opacity:1"

        # Handle gold gradient
        if color_name == "Gold":
            defs = xpath(".//svg:defs")
            if defs:
                defs = defs[0]
            else:
                defs = etree.SubElement(root, f"{{{nsmap['svg']}}}defs")

            gradient = xpath(".//svg:linearGradient[@id='linearGradientGold']")
            if not gradient:
                gradient = etree.SubElement(
                    defs,
                    f"{{{nsmap['svg']}}}linearGradient",
                    {
                        "id": "linearGradientGold",
                        "x1": "-0.12096094",
                        "y1": "0.98514783",
                        "x2": "0.12096094",
                        "y2": "0.014852136",
                    },
                )
                stops = [("0%", "#ffd700"), ("50%", "#d4af37"), ("100%", "#bfa54f")]
                for offset, color in stops:
                    etree.SubElement(
                        gradient,
                        f"{{{nsmap['svg']}}}stop",
                        {
                            "offset": offset,
                            "style": f"stop-color:{color};stop-opacity:1;",
                        },
                    )
            set_fill_by_id("Header-Background", "url(#linearGradientGold)")
        else:
            set_fill_by_id("Header-Background", cart_color)

        # Apply colour replacements
        set_fill_by_id("NFC_LOADING", text_color)
        set_fill_by_inkscape_label("body", text_color)
        set_fill_by_inkscape_label("dpad", text_color)
        set_fill_by_inkscape_label("stick", text_color)
        set_fill_by_inkscape_label("left-indent", shade_color)
        set_fill_by_inkscape_label("vertical-line", shade_color)

        # Save the modified file
        tree.write(
            str(output_path), pretty_print=True, xml_declaration=True, encoding="UTF-8"
        )
        created_files.append(str(output_path))

    return created_files


def main():
    base_svg_path = "Cards/hucard_n64.svg"
    output_dir = "Cards"
    created = create_n64_svg(base_svg_path, output_dir, cartridge_colors)
    print("Created the following SVG files:")
    for f in created:
        print(f)


if __name__ == "__main__":
    main()
