"""NES cartridge colour variants.

The NES template ships a single grey design, so the gold cartridge Nintendo
used for The Legend of Zelda and Zelda II is recoloured onto a copy of it in
memory at render time. A game picks a variant with `"colour"` in its
`GameCovers/<system>/<game>.json` file; with no `colour` key the template is
rendered on the standard grey cartridge.
"""

import re
from dataclasses import dataclass

from lxml import etree  # type: ignore

from utils.cartridge_gradient import GOLD_GRADIENT_ID, ensure_gold_gradient


@dataclass(frozen=True)
class CartridgeColour:
    """One NES cartridge colourway."""

    body: str
    moulding: str
    groove: str
    gradient: bool = False


NES_COLOURS: dict[str, CartridgeColour] = {
    "gold": CartridgeColour("#ffd700", "#b8912b", "#9c7a24", gradient=True),
}

# The shell body is one path; the grip moulding is the `cartridgelines` group,
# drawn with a light grey for the bars and darker greys for the grooves. The
# controller's start/select background shares the body grey, so the body is
# named by id and the moulding is recoloured inside its group only.
_BODY_ID = "Header-Background"
_MOULDING_GROUP = "cartridgelines"
_MOULDING_SOURCES = ("#999999", "#76787a")
_GROOVE_SOURCES = ("#6b6c70",)


def colour_names() -> list[str]:
    return list(NES_COLOURS)


def normalise_colour(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    if key not in NES_COLOURS:
        known = ", ".join(NES_COLOURS)
        raise ValueError(
            f"Unknown NES cartridge colour {name!r}. Known colours: {known}"
        )
    return key


def apply_cartridge_colour(root, nsmap, colour: str | None) -> None:
    """Recolour a parsed NES template root in place. No-op without a colour."""
    key = normalise_colour(colour)
    if key is None:
        return

    spec = NES_COLOURS[key]

    if spec.gradient:
        ensure_gold_gradient(root, nsmap)
        _set_fill_by_id(root, nsmap, _BODY_ID, f"url(#{GOLD_GRADIENT_ID})")
    else:
        _set_fill_by_id(root, nsmap, _BODY_ID, spec.body)

    groups = root.xpath(
        f".//svg:g[@inkscape:label='{_MOULDING_GROUP}']", namespaces=nsmap
    )
    for group in groups:
        for el in group.iter():
            _set_moulding_fill(el, spec)


def _set_moulding_fill(element, spec: CartridgeColour) -> None:
    style = element.attrib.get("style")
    if not style:
        return
    if any(source in style for source in _MOULDING_SOURCES):
        _set_fill(element, spec.moulding)
    elif any(source in style for source in _GROOVE_SOURCES):
        _set_fill(element, spec.groove)


def _set_fill_by_id(root, nsmap, id_value: str, fill_value: str) -> None:
    elements = root.xpath(f".//svg:path[@id='{id_value}']", namespaces=nsmap)
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
