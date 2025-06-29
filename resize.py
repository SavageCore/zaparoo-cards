import os
import subprocess

inkscape_path = r"C:\Program Files\Inkscape\bin\inkscape.exe"

for root, dirs, files in os.walk("."):
    # Skip the root directory itself
    if root == ".":
        continue
    for file in files:
        if file.endswith(".svg"):
            input_path = os.path.join(root, file)
            os.makedirs(root + "/_trimmed", exist_ok=True)
            output_path = os.path.join(root + "/_trimmed", file)

            print(f"Trimming: {file}")

            subprocess.run(
                [
                    inkscape_path,
                    input_path,
                    "--export-area-drawing",
                    "--export-plain-svg",
                    f"--export-filename={output_path}",
                ]
            )
