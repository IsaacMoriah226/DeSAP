"""Addresses in Demon's Souls 01.007.000 (PPSA01341) as KytyPS5 maps it (eboot at 0x900000000), and how each
was found. `SIGNATURES` are the first bytes of every function the client calls: the client refuses to run when
they differ (another game version).

Globals (pointers to the game's singletons):
- FLAG_MANAGER: event flags (see flags.py). From the SetEventFlag Lua binding's handler.
- MAP_MANAGER: [+0x8] block array (block i at [+0x18 + 8 * i]), [+0x60] the block the player is in; a block's map
  id at +0x228 (0x02010000 for m02_01_00_00). This is what the save stores as MAPUID (0x90002df89 calls
  0x9001f7a40 -> 0x9003e5aa0) and what BP_GetAreaId reads (its byte 3).
- PLAYER_GAME_DATA: [+0x10] the player's data (inventory at +0x130: slot count +0x128, entries +0x130, 32 bytes
  each: category, id, count, ...); [+0x94] the death count (AddDeathCount -> 0x900448620).
- CHR_INS_MAN: [+0x258] the player's character (null while no character is loaded).
- GAME_MAN: [+0x8] warp request byte, [+0xc] next map id, [+0x90] next spawn event (WarpNextStage's handler).

Lua bindings (`proxy:` functions; tools/lua_bindings.py lists all 943 with their handlers):
- GetRateItem(category, id, count): GIVE_ITEM, adds the item and shows the "item get" popup (verified in game).
- WarpNextStage(area, block, 0, 0, spawn event): WARP_NEXT_STAGE, the archstones' and the Warp miracle's warp.
- RemoveInventoryEquip(category, id): REMOVE_ITEM, removes one of the item.
"""

FLAG_MANAGER = 0x9027BF328
MAP_MANAGER = 0x9027DF318
PLAYER_GAME_DATA = 0x9027E6948
CHR_INS_MAN = 0x9027CF378
GAME_MAN = 0x9027BF378

# offsets
PLAYER_DATA = 0x10
DEATH_COUNT = 0x94
PLAYER_CHR = 0x258
INVENTORY = 0x130  # in the player's data
INVENTORY_COUNT = 0x128  # in the inventory
INVENTORY_ENTRIES = 0x130
INVENTORY_ENTRY_SIZE = 0x20
MAP_BLOCKS = 0x8
MAP_CURRENT_BLOCK = 0x60
BLOCK_MAP_UID = 0x228

# functions (System V calling convention: rdi, rsi, rdx, rcx, r8, r9)
GIVE_ITEM = 0x900216980  # (_, category, id, count)
WARP_NEXT_STAGE = 0x900216300  # (_, area, block, 0, 0, spawn event id)
REMOVE_ITEM = 0x90021B9D0  # (_, category, id): one of it
TRIGGER_CALLBACK = 0x900452B40  # the dev console command cp11_setShopLvl's callback (we borrow it)
TRIGGER_COMMAND = "+cp11_setShopLvl"
SUICIDE_COMMAND = "+cp11_playerSuicide"  # kills the player (does nothing in the tutorial, verified)

SIGNATURES = {
    GIVE_ITEM: "554889e54157415641554154534883ec",
    WARP_NEXT_STAGE: "554889e54156534883ec104c8b35aebf",
    REMOVE_ITEM: "488b3dc96d59024885ff0f85b095feff",
    TRIGGER_CALLBACK: "554889e5415653488d05fa3d3902bb03",
    0x9003E5AA0: "4889f8b9ffffffff85d278173b56107d",  # a block's map id (checks MAP_MANAGER's layout)
}

# Nexus spawn events in front of each world's archstone (global_event.lua gBPWarpReturnEvents), by area id.
NEXUS_RETURN_EVENT = {2: 1006, 6: 1010, 4: 1008, 3: 1007, 5: 1009}
NEXUS_AREA = 1
TUTORIAL_AREA = 8

CATEGORY = {"weapon": 0x00000000, "armor": 0x10000000, "ring": 0x20000000, "goods": 0x40000000}
