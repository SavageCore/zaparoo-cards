import os
import subprocess

from lxml import etree

inkscape_path = r"C:\Program Files\Inkscape\bin\inkscape.exe"
svgo_config_path = "svgo.config.js"  # Adjust if it's in a different location
svgo_path = "C:\\Users\\SavageCore\\AppData\\Local\\pnpm\\svgo.CMD"

for root, dirs, files in os.walk("."):
    # Skip the root directory itself
    if root == ".":
        continue
    # Skip the Cards directory
    if os.path.basename(root) == "Cards":
        print(f"Skipping directory: {root}")
        continue
    for file in files:
        if file.endswith(".svg"):
            input_path = os.path.join(root, file)
            output_path = os.path.join(root, file)

            print(f"Processing: {file}")

            text_removed = False

            # Remove <text> elements from SVG
            parser = etree.XMLParser(remove_blank_text=True)
            tree = etree.parse(input_path, parser)
            svg_root = tree.getroot()

            # Match all <text> elements regardless of namespace
            for text in svg_root.xpath("//*[local-name()='text']"):
                text.getparent().remove(text)
                text_removed = True

            # Save the modified SVG
            tree.write(input_path, pretty_print=True, xml_declaration=True, encoding="utf-8")

            if text_removed:
                print("✅ Removed <text> elements")

            # Fit to page
            result = subprocess.run(
                [
                    inkscape_path,
                    input_path,
                    "--export-area-drawing",
                    "--export-plain-svg",
                    f"--export-filename={output_path}",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"❌ Error fitting to page:\n{result.stderr}")
            else:
                print("✅ Fit to page")

            # Optimise with SVGO
            result = subprocess.run(
                [
                    svgo_path,
                    "-i",
                    input_path,
                    "-o",
                    output_path,
                    "--config",
                    svgo_config_path,
                    "--pretty",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"❌ Error optimizing:\n{result.stderr}")
            else:
                print("✅ Optimized")

            print("")
