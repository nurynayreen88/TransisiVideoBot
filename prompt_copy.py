"""Consistent English instructions for generated spoken promotional copy."""


def spoken_copy_direction(language="Malay"):
    """Keep prompt instructions English while selecting the language actually spoken."""
    if str(language or "Malay").casefold() == "english":
        return (
            "Write a fresh, product-specific hook, one verified detail or plausible use, "
            "and a concise CTA in natural English. Avoid generic repeated openings and unsupported claims."
        )
    return (
        "Write a fresh, product-specific hook, one verified detail or plausible use, "
        "and a concise CTA in natural Bahasa Melayu Malaysia. Avoid Indonesian vocabulary, "
        "generic repeated openings and unsupported claims."
    )
