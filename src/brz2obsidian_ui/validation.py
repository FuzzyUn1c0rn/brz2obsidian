"""Parse editable API fields without losing which correction the user needs."""

from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from brz2obsidian.application.contracts import ApiAcquisitionConfig


def api_configuration(base, fields):
    """Return validated configuration and concise errors keyed by field name."""
    values = base.model_dump()
    errors = {}
    address = fields["api_url"]
    try:
        ApiAcquisitionConfig(**{**values, "api_url": address})
    except ValueError:
        credentialed = False
        try:
            parsed = urlsplit(address)
            credentialed = parsed.username is not None or parsed.password is not None
        except ValueError:
            pass
        errors["api_url"] = (
            "Remove the username and password from the address."
            if credentialed
            else "Enter TheBrain’s local API address."
        )
    values["api_url"] = address
    for key in (
        "search_initial_results",
        "search_timeout",
        "search_max_response_bytes",
        "search_max_results",
    ):
        raw = fields[key]
        if key == "search_timeout":
            try:
                seconds = Decimal(raw)
                if not seconds.is_finite() or not Decimal("0.001") <= seconds <= 86400:
                    raise ValueError
                if seconds * 1000 != (seconds * 1000).to_integral_value():
                    errors[key] = "Use up to three decimal places."
                else:
                    values[key] = float(seconds)
            except ValueError, InvalidOperation:
                errors[key] = "Enter 0.001–86,400 seconds."
            continue
        optional = key == "search_max_results"
        byte_limit = key == "search_max_response_bytes"
        if optional and raw == "":
            values[key] = None
            continue
        try:
            number = int(raw)
            if number <= 0:
                raise ValueError
        except ValueError:
            errors[key] = (
                "Enter a positive whole number, or leave blank."
                if optional
                else "Enter a positive whole number of bytes."
                if byte_limit
                else "Enter a positive whole number."
            )
            continue
        maximum = 9223372036854775807 if byte_limit else 2147483647
        if number > maximum:
            errors[key] = (
                "This value exceeds the supported limit."
                if byte_limit
                else "Enter 2,147,483,647 or less, or leave blank."
                if optional
                else "Enter 2,147,483,647 or less."
            )
        else:
            values[key] = number
    return (None, errors) if errors else (ApiAcquisitionConfig(**values), {})
