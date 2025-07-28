
import asyncio
from edge_tts import VoicesManager
from typing import Optional
async def _list_supported_voices_async(filter_lang: Optional[str] = None):
    vm = await VoicesManager.create()
    voices = vm.voices
    if filter_lang:
        voices = [v for v in voices if v["Locale"].startswith(filter_lang)]
    return voices
async def list_supported_voices(
    filter_lang: Optional[str] = None,
    human_readable: bool = False
):
    """Query available edge-tts voices.

    Parameters
    ----------
    filter_lang : str, optional
        Return only voices whose locale starts with this prefix.
    human_readable : bool, optional
        If ``True`` print a formatted table; otherwise return the raw list.

    Returns
    -------
    list of dict or None
        The raw voice dictionaries if ``human_readable`` is ``False``,
        otherwise ``None``.
    """
    voices = await _list_supported_voices_async(filter_lang)
    if not human_readable:
        return voices

    # Table header including the Personalities column
    header = (
        f"{'ShortName':25} {'Locale':10} {'Gender':8} "
        f"{'Personalities':30} {'FriendlyName'}"
    )
    separator = "-" * len(header)
    print(header)
    print(separator)

    for v in voices:
        short = v.get("ShortName", "")[:25]
        loc   = v.get("Locale", "")[:10]
        gen   = v.get("Gender", "")[:8]
        # Extract the personalities list and join with commas
        pers_list = v.get("VoiceTag", {}).get("VoicePersonalities", [])
        pers = ", ".join(pers_list)[:30]
        # Use FriendlyName as the display name
        disp  = v.get("FriendlyName", v.get("Name", ""))

        print(f"{short:25} {loc:10} {gen:8} {pers:30} {disp}")
