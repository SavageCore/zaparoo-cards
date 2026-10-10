"""SNES cartridge colour variants.

The SNES template ships a single grey design, so the handful of coloured
cartridges that actually shipped are recoloured onto a copy of it in memory at
render time. Each game picks a variant with `"colour"` in its
`GameCovers/<system>/<game>.json` file; with no `colour` key the template is
rendered on the standard grey cartridge.

Only the three real coloured SNES carts are supported: Killer Instinct shipped
black, while Doom and Spider-Man & Venom: Maximum Carnage shipped red.
"""

import re
from dataclasses import dataclass

from lxml import etree  # type: ignore


@dataclass(frozen=True)
class CartridgeColour:
    """One SNES cartridge colourway."""

    body: str
    text: str
    shade: str


SNES_COLOURS: dict[str, CartridgeColour] = {
    "black": CartridgeColour("#2b2b2b", "#ffffff", "#1a1a1a"),
    "red": CartridgeColour("#b10000", "#ffffff", "#7d0000"),
}

_BODY_ID = "Header-Background"
_TEXT_ID = "NFC_LOADING"
_SHADE_LABELS = ("vertical-line", "horizontal-line")


def colour_names() -> list[str]:
    return list(SNES_COLOURS)


def normalise_colour(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    if key not in SNES_COLOURS:
        known = ", ".join(SNES_COLOURS)
        raise ValueError(
            f"Unknown SNES cartridge colour {name!r}. Known colours: {known}"
        )
    return key


def apply_cartridge_colour(root, nsmap, colour: str | None) -> None:
    """Recolour a parsed SNES template root in place. No-op without a colour."""
    key = normalise_colour(colour)
    if key is None:
        return

    spec = SNES_COLOURS[key]

    _set_fill_by_id(root, nsmap, _BODY_ID, spec.body)
    _set_fill_by_id(root, nsmap, _TEXT_ID, spec.text)
    for label in _SHADE_LABELS:
        _set_fill_by_label(root, nsmap, label, spec.shade)


def _set_fill_by_id(root, nsmap, id_value: str, fill_value: str) -> None:
    elements = root.xpath(f".//svg:path[@id='{id_value}']", namespaces=nsmap)
    for el in elements:
        _set_fill(el, fill_value)


def _set_fill_by_label(root, nsmap, label_value: str, fill_value: str) -> None:
    elements = root.xpath(
        f".//svg:path[@inkscape:label='{label_value}']", namespaces=nsmap
    )
    for el in elements:
        _set_fill(el, fill_value)


def _set_fill(element: etree._Element, fill_value: str) -> None:
    """Replace the element's fill, keeping any other style properties."""
    style = element.attrib.get("style", "")
    if re.search(r"fill:", style):
        style = re.sub(r"fill:[^;]*", f"fill:{fill_value}", style)
    else:
        style = f"{style};fill:{fill_value}".strip("; ")
    element.attrib["style"] = style
