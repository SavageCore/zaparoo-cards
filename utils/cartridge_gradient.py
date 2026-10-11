"""The shared gold cartridge gradient.

Both the N64 and NES templates use the same gold sweep for their gold
cartridges, so the definition lives here and each system's colour module drops
it into its own template when a gold cartridge is requested.
"""

from lxml import etree  # type: ignore

GOLD_GRADIENT_ID = "linearGradientGold"
GOLD_GRADIENT_STOPS = (("0%", "#ffd700"), ("50%", "#d4af37"), ("100%", "#bfa54f"))
GOLD_GRADIENT_COORDS = {
    "x1": "-0.12096094",
    "y1": "0.98514783",
    "x2": "0.12096094",
    "y2": "0.014852136",
}


def ensure_gold_gradient(root, nsmap) -> None:
    """Add the shared gold gradient to a parsed template root, once."""
    if root.xpath(f".//svg:linearGradient[@id='{GOLD_GRADIENT_ID}']", namespaces=nsmap):
        return

    defs = root.xpath(".//svg:defs", namespaces=nsmap)
    if defs:
        defs = defs[0]
    else:
        defs = etree.SubElement(root, f"{{{nsmap['svg']}}}defs")

    gradient = etree.SubElement(
        defs,
        f"{{{nsmap['svg']}}}linearGradient",
        {"id": GOLD_GRADIENT_ID, **GOLD_GRADIENT_COORDS},
    )
    for offset, colour in GOLD_GRADIENT_STOPS:
        etree.SubElement(
            gradient,
            f"{{{nsmap['svg']}}}stop",
            {
                "offset": offset,
                "style": f"stop-color:{colour};stop-opacity:1;",
            },
        )
