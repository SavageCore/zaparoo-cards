"""N64 cartridge colour variants.

The N64 template ships a single design, so alternative cartridge colours are
recoloured onto a copy of it in memory at render time. Each game picks a
variant with `"colour"` in its `GameCovers/<system>/<game>.json` file; with no
`colour` key the template is rendered exactly as authored.
"""

import re
from dataclasses import dataclass

from utils.cartridge_gradient import GOLD_GRADIENT_ID, ensure_gold_gradient


@dataclass(frozen=True)
class CartridgeColour:
    """One N64 cartridge colourway.

    `badge_plate` is False for the colours the yellow plate would disappear
    into, leaving the white badge to sit straight on the cartridge body.
    """

    body: str
    text: str
    shade: str
    badge_plate: bool = True
    gradient: bool = False


CARTRIDGE_COLOURS: dict[str, CartridgeColour] = {
    "black": CartridgeColour("#2b2b2b", "#ffffff", "#222222"),
    "blue": CartridgeColour("#0047ab", "#ffffff", "#003366"),
    "gold": CartridgeColour(
        "#ffd700", "#000000", "#a98c2c", badge_plate=False, gradient=True
    ),
    "green": CartridgeColour("#2baf2b", "#000000", "#228c22"),
    "red": CartridgeColour("#c80000", "#000000", "#a00000"),
    "yellow": CartridgeColour("#ffd700", "#000000", "#ccac00", badge_plate=False),
}

# The gradient cartridge gets a gradient body rather than a flat fill.
BADGE_YELLOW_BG_LABEL = "only-for-n64-yellow-bg"

_TEXT_LABELS = ("body", "dpad", "stick")
_SHADE_LABELS = ("left-indent", "vertical-line")


def colour_names() -> list[str]:
    return list(CARTRIDGE_COLOURS)


def normalise_colour(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    if key not in CARTRIDGE_COLOURS:
        known = ", ".join(CARTRIDGE_COLOURS)
        raise ValueError(
            f"Unknown N64 cartridge colour {name!r}. Known colours: {known}"
        )
    return key


def apply_cartridge_colour(root, nsmap, colour: str | None) -> None:
    """Recolour a parsed N64 template root in place. No-op without a colour."""
    key = normalise_colour(colour)
    if key is None:
        return

    spec = CARTRIDGE_COLOURS[key]

    if spec.gradient:
        ensure_gold_gradient(root, nsmap)
        _set_fill_by_id(root, nsmap, "Header-Background", f"url(#{GOLD_GRADIENT_ID})")
    else:
        _set_fill_by_id(root, nsmap, "Header-Background", spec.body)

    _set_fill_by_id(root, nsmap, "NFC_LOADING", spec.text)
    for label in _TEXT_LABELS:
        _set_fill_by_label(root, nsmap, label, spec.text)
    for label in _SHADE_LABELS:
        _set_fill_by_label(root, nsmap, label, spec.shade)

    _set_display_by_label(root, nsmap, BADGE_YELLOW_BG_LABEL, spec.badge_plate)


def _set_fill_by_id(root, nsmap, id_value: str, fill_value: str) -> None:
    elements = root.xpath(f".//svg:path[@id='{id_value}']", namespaces=nsmap)
    if elements:
        elements[0].attrib["style"] = f"fill:{fill_value};fill-opacity:1"


def _set_fill_by_label(root, nsmap, label_value: str, fill_value: str) -> None:
    elements = root.xpath(
        f".//svg:path[@inkscape:label='{label_value}']", namespaces=nsmap
    )
    if elements:
        elements[0].attrib["style"] = f"fill:{fill_value};fill-opacity:1"


def _set_display_by_label(root, nsmap, label_value: str, visible: bool) -> None:
    elements = root.xpath(
        f".//svg:g[@inkscape:label='{label_value}']"
        f" | .//svg:image[@inkscape:label='{label_value}']",
        namespaces=nsmap,
    )
    for el in elements:
        style = el.attrib.get("style", "")
        new_style = re.sub(r"display\s*:\s*(inline|none)", "", style).strip("; ")
        display = "inline" if visible else "none"
        el.attrib["style"] = f"display:{display};{new_style}".strip("; ")
