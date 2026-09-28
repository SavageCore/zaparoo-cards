# A script to process and generate PDFs for Zaparoo game cards

> With bonus hucard style card templates for most systems in the `Cards/` directory.

Like [Zaparoo Designer](https://design.zaparoo.org/) but this time CLI

### Usage

You will need Python installed and to run `pip install -r requirements.txt` to install the required dependencies.

#### Generating PDFs to print
1. Ensure you have cover images in the `GameCovers` directory split by console type.
   - The directory structure should look like this:
     ```
     GameCovers/
       ├── megadrive/
       │   └── Streets of Rage.jpg
       ├── snes/
       │   └── Super Mario World.jpg
       └── nes/
           └── Super Mario Bros.jpg
     ```
   - Each cover image should be named as `Game Title.jpg` and placed in the appropriate console subdirectory.
   - The console subdirectories should match the names used in the `Cards/` directory.
2. Run `python create_pdf.py` to generate a PDF.
   - This will create a PDF file named `output.pdf` in the current directory.
   - The PDF will contain all game covers layed out in a grid format, ready for printing on A4 paper.

##### Configuring

You can enable Crop Marks, Outline or Both by passing the `--crop`, `--outline` or `--both` flags respectively.

Cards print at their full media size, 85mm x 54mm, with no white surround, so a sheet can be printed and then cut up along the crop marks.

To limit the number of cards processed use the `--limit` flag followed by a number, e.g. `--limit 20`, passing `--limit` without a number will default to 10.

Limiting systems to process is done by passing the `--systems` flag followed by the system names, e.g. `--systems snes nes`.

Use `--example` to generate `output_example.pdf` with one card per system, and for `n64` one card per cartridge colour.

Passing the `--keep` flag will keep the temporary files created during processing, otherwise they will be deleted after the PDF is generated.

#### Comparing two card designs

`compare_templates.py` renders two card templates from the same cover art onto one page so designs can be diffed. Cards are shown upright rather than in the rotated print orientation, and the only raster content is the cover, everything else stays vector.

```sh
uv run compare_templates.py \
  --left Cards/neogeo_old.svg --left-label "Before" \
  --right Cards/neogeo.svg --right-label "After"
```

or, for the Neo Geo designs specifically:

```sh
make compare
```

`Cards/neogeo_old.svg` is the Neo Geo design as it stood at `ee8a397^`, rescued before the cartridge redesign landed. It is not wired into any system by default, so normal runs ignore it. Point a game at it by adding a `json` file next to its cover, e.g. `GameCovers/neogeo/Metal Slug X.json` containing `{"template": "neogeo_old.svg"}`.

Performance options:
- Use `--workers N` to render cards in parallel (default is auto-selected based on CPU cores).
- Rendered cards are cached persistently as single page vector PDFs in `.cache/zaparoo-cards/rendered` by default. Each card is drawn into the sheet as vectors, so only the cover artwork is raster, at 300 DPI.
- Use `--cache-dir <path>` to change where persistent cache files are stored.
- Use `--render-only` to skip PDF creation when you only want to warm/build the render cache.
- Use `--benchmark` to print stage timings (discover, render, pdf, total).
- Use `--no-cache` if you want to force a full re-render.

#### Optimising SVGs

This script will remove text SVGs which is useful for thenounproject which include attribution text in their SVGs. Next it will ensure the drawing is fit to page as once we've removed the text the SVG may not be centred on the page. Finally it will optimise the SVG with [SVGO](https://svgo.dev/) (Node) to reduce file size.

1. Run `python process.py`.
   - This will process all SVG files in the `Cartridges/`, `Consoles/`, `Controllers/`, `Logos/` directories.

### N64 Cartridge Colours

The N64 template is drawn once and recoloured at render time, so a game just names the cartridge colour it should print as. Create a `json` file in the `GameCovers/n64` directory named after the artwork file, e.g. `GameCovers/n64/Super Mario 64.json`:

```json
{
    "colour": "gold"
}
```

Available colours are `black`, `blue`, `gold`, `green`, `red` and `yellow`. With no `json` file the game prints on the standard grey cartridge.

### Sources / Attributions

If I have used your work and not given you credit please submit a PR or issue and I will add it.

https://thenounproject.com/browse/collection-icon/video-game-controllers-7766/

https://thenounproject.com/browse/collection-icon/gamepads-31128/

https://thenounproject.com/icon/game-controller-193793/

https://thenounproject.com/browse/collection-icon/nintendo-handhelds-43424/

https://thenounproject.com/icon/game-boy-44989/

https://thenounproject.com/browse/collection-icon/console-game-glyph-61149/

https://pixabay.com/vectors/gamegear-game-sega-handheld-arcade-3432581/

https://thenounproject.com/icon/sega-saturn-6123819/

https://thenounproject.com/browse/collection-icon/arcade-machines-2d-39704/

https://archive.org/details/console-logos-professionally-redrawn-plus-official-versions
