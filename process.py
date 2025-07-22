import os
import subprocess

from lxml import etree

inkscape_path: str = r"C:\Program Files\Inkscape\bin\inkscape.exe"
svgo_config_path: str = "svgo.config.js"  # Adjust if it's in a different location
svgo_path: str = r"C:\Users\SavageCore\AppData\Local\pnpm\svgo.CMD"


def process_svg_files() -> None:
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
                input_path: str = os.path.join(root, file)
                output_path: str = os.path.join(root, file)

                print(f"Processing: {file}")

                text_removed: bool = False

                # Remove <text> elements from SVG
                parser = etree.XMLParser(remove_blank_text=True)
                tree = etree.parse(input_path, parser)
                svg_root = tree.getroot()

                # Match all <text> elements regardless of namespace
                # Assert that xpath returns a list of _Element objects
                text_elements = svg_root.xpath("//*[local-name()='text']")
                if not isinstance(text_elements, list):
                    raise ValueError("Unexpected xpath result type")
                for text in text_elements:
                    if isinstance(text, etree._Element):
                        parent = text.getparent()
                        if parent is not None:
                            parent.remove(text)
                            text_removed = True

                # Save the modified SVG
                tree.write(
                    input_path,
                    pretty_print=True,
                    xml_declaration=True,
                    encoding="utf-8",
                )

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

                # Optimize with SVGO
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


if __name__ == "__main__":
    process_svg_files()
