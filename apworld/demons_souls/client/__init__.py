"""The Demon's Souls Remake client (context.py). The game-access modules (memory, gamecall, live, flags, params,
addresses, game) import no Archipelago code, so DeSAP's tools use them directly."""


def launch(*args: str) -> None:
    from .context import launch as run
    run(*args)
