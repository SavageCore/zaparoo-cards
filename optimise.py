import os
import subprocess

config_path = "svgo.config.js"  # Adjust if it's in a different location
svgo_path = "C:\\Users\\SavageCore\\AppData\\Local\\pnpm\\svgo.CMD"

for root, dirs, files in os.walk("."):
    # Skip the root directory itself
    if root == ".":
        continue

    # Skip '_optimised' folders
    if "_optimised" in root.split(os.sep):
        continue

    for file in files:
        if file.endswith(".svg"):
            input_path = os.path.join(root, file)
            os.makedirs(root + "/_optimised", exist_ok=True)
            output_path = os.path.join(root + "/_optimised", file)

            result = subprocess.run(
                [
                    svgo_path,
                    "-i",
                    input_path,
                    "-o",
                    output_path,
                    "--config",
                    config_path,
                    "--pretty",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"❌ Error optimizing {file}:\n{result.stderr}")
            else:
                print(f"✅ Optimized {file}")
