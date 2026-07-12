/*
 * RAM bridge for Pokémon Red/Blue running inside EmulatorJS.
 *
 * The bridge deliberately avoids modules so it works from file://. It attempts
 * known EmulatorJS memory hooks first and falls back to deterministic demo data
 * when browser-core RAM is not exposed by the loaded emulator build.
 */
(function (global) {
  'use strict';

  const ADDR = Object.freeze({
    // Player state, matching src/core/ram_reader.py
    wPlayerY: 0xD361,
    wPlayerX: 0xD362,
    wCurMap: 0xD35E,
    wWalkCounter: 0xCFC5,

    // Party state requested for the browser overlay
    wPartyCount: 0xD163,
    wPartyMons: 0xD16B,
    partyMonSize: 44,

    // Screen and UI indicators, matching src/core/ram_reader.py where present
    wTileMap: 0xC3A0,
    wTextBoxFrame: 0xCF2B,
    wTextScrollPrompt: 0xCF4C,
    wIsInBattle: 0xD057,
    wBattleType: 0xD05A,
    wCurOpponent: 0xD058,
    wTopMenuItemY: 0xCC24,
    wTopMenuItemX: 0xCC25,
    wCurrentMenuItem: 0xCC26,
    wMaxMenuItem: 0xCC28,
    wLastMenuItem: 0xCC2A,
    wListMenuID: 0xCF88,
    wNamingScreenType: 0xCC47,
    wNamingScreenNameLength: 0xCC48,
    wNamingScreenSubmitName: 0xCC4A,
    wAlphabetCase: 0xCC4D,
    wNamingScreenLetter: 0xCC4F
  });

  const MAP_NAMES = Object.freeze({
    0x00: 'Pallet Town',
    0x01: 'Viridian City',
    0x02: 'Pewter City',
    0x03: 'Cerulean City',
    0x04: 'Lavender Town',
    0x05: 'Vermilion City',
    0x06: 'Celadon City',
    0x07: 'Fuchsia City',
    0x08: 'Cinnabar Island',
    0x09: 'Indigo Plateau',
    0x0A: 'Saffron City',
    0x0C: 'Route 1',
    0x0D: 'Route 2',
    0x0E: 'Route 3',
    0x0F: 'Route 4',
    0x10: 'Route 5',
    0x11: 'Route 6',
    0x12: 'Route 7',
    0x13: 'Route 8',
    0x14: 'Route 9',
    0x15: 'Route 10',
    0x16: 'Route 11',
    0x17: 'Route 12',
    0x18: 'Route 13',
    0x19: 'Route 14',
    0x1A: 'Route 15',
    0x1B: 'Route 16',
    0x1C: 'Route 17',
    0x1D: 'Route 18',
    0x1E: 'Route 19',
    0x1F: 'Route 20',
    0x20: 'Route 21',
    0x21: 'Route 22',
    0x22: 'Route 23',
    0x24: "Red's House 1F",
    0x25: "Red's House 2F",
    0x26: "Blue's House",
    0x27: "Oak's Lab"
  });

  const SPECIES_NAMES = Object.freeze({
    1: 'Rhydon', 2: 'Kangaskhan', 3: 'Nidoran♂', 4: 'Clefairy',
    5: 'Spearow', 6: 'Voltorb', 7: 'Nidoking', 8: 'Slowbro',
    9: 'Ivysaur', 10: 'Exeggutor', 11: 'Lickitung', 12: 'Exeggcute',
    13: 'Grimer', 14: 'Gengar', 15: 'Nidoran♀', 16: 'Nidoqueen',
    17: 'Cubone', 18: 'Rhyhorn', 19: 'Lapras', 20: 'Arcanine',
    21: 'Mew', 22: 'Gyarados', 23: 'Shellder', 24: 'Tentacool',
    25: 'Gastly', 26: 'Scyther', 27: 'Staryu', 28: 'Blastoise',
    29: 'Pinsir', 30: 'Tangela', 33: 'Growlithe', 34: 'Onix',
    35: 'Fearow', 36: 'Pidgey', 37: 'Slowpoke', 38: 'Kadabra',
    39: 'Graveler', 40: 'Chansey', 41: 'Machoke', 42: 'Mr. Mime',
    43: 'Hitmonlee', 44: 'Hitmonchan', 45: 'Arbok', 46: 'Parasect',
    47: 'Psyduck', 48: 'Drowzee', 49: 'Golem', 51: 'Magmar',
    53: 'Electabuzz', 54: 'Magneton', 55: 'Koffing', 57: 'Mankey',
    58: 'Seel', 59: 'Diglett', 60: 'Tauros', 63: "Farfetch'd",
    64: 'Venonat', 65: 'Dragonite', 67: 'Doduo', 68: 'Poliwag',
    69: 'Jynx', 70: 'Moltres', 71: 'Articuno', 72: 'Zapdos',
    73: 'Ditto', 74: 'Meowth', 75: 'Krabby', 77: 'Vulpix',
    78: 'Ninetales', 79: 'Pikachu', 80: 'Raichu', 83: 'Dratini',
    84: 'Dragonair', 85: 'Kabuto', 86: 'Kabutops', 87: 'Horsea',
    88: 'Seadra', 90: 'Sandshrew', 91: 'Sandslash', 92: 'Omanyte',
    93: 'Omastar', 94: 'Jigglypuff', 95: 'Wigglytuff', 96: 'Eevee',
    97: 'Flareon', 98: 'Jolteon', 99: 'Vaporeon', 100: 'Machop',
    101: 'Zubat', 102: 'Ekans', 103: 'Paras', 104: 'Poliwhirl',
    105: 'Poliwrath', 106: 'Weedle', 107: 'Kakuna', 108: 'Beedrill',
    110: 'Dodrio', 111: 'Primeape', 112: 'Dugtrio', 113: 'Venomoth',
    114: 'Dewgong', 117: 'Caterpie', 118: 'Metapod', 119: 'Butterfree',
    120: 'Machamp', 123: 'Golduck', 124: 'Hypno', 125: 'Golbat',
    126: 'Mewtwo', 127: 'Snorlax', 128: 'Magikarp', 131: 'Muk',
    133: 'Kingler', 134: 'Cloyster', 136: 'Electrode', 137: 'Clefable',
    138: 'Weezing', 139: 'Persian', 140: 'Marowak', 142: 'Haunter',
    143: 'Abra', 144: 'Alakazam', 145: 'Pidgeotto', 146: 'Pidgeot',
    147: 'Starmie', 148: 'Bulbasaur', 149: 'Venusaur', 150: 'Tentacruel',
    152: 'Goldeen', 153: 'Seaking', 157: 'Ponyta', 158: 'Rapidash',
    159: 'Rattata', 160: 'Raticate', 161: 'Nidorino', 162: 'Nidorina',
    163: 'Geodude', 164: 'Porygon', 165: 'Aerodactyl', 167: 'Magnemite',
    170: 'Charmander', 171: 'Charmeleon', 172: 'Charizard', 174: 'Oddish',
    175: 'Gloom', 176: 'Vileplume', 177: 'Bellsprout', 178: 'Weepinbell',
    179: 'Victreebel', 185: 'MissingNo.'
  });

  const WRAM_START = 0xC000;
  const WRAM_END = 0xDFFF;

  function isTypedArray(value) {
    return value && value.buffer instanceof ArrayBuffer && typeof value.length === 'number';
  }

  function asCallableReader(candidate, label) {
    if (!candidate) {
      return null;
    }

    const readMethods = ['readByte', 'read8', 'read_u8', 'getByte', 'getUint8'];
    for (const method of readMethods) {
      if (typeof candidate[method] === 'function') {
        return {
          source: `${label}.${method}()`,
          readByte: (addr) => candidate[method](addr) & 0xFF
        };
      }
    }

    if (isTypedArray(candidate) || Array.isArray(candidate)) {
      return typedArrayReader(candidate, label);
    }

    const nestedFields = ['memory', 'mem', 'ram', 'wram', 'data'];
    for (const field of nestedFields) {
      const nested = asCallableReader(candidate[field], `${label}.${field}`);
      if (nested) {
        return nested;
      }
    }

    return null;
  }

  function typedArrayReader(memory, label) {
    const length = memory.length;

    if (length >= 0x10000 && length <= 0x20000) {
      return {
        source: `${label}[gb-address]`,
        readByte: (addr) => memory[addr] & 0xFF
      };
    }

    if (length >= 0x2000 && length < 0x10000) {
      return {
        source: `${label}[wram-offset]`,
        readByte: (addr) => {
          if (addr < WRAM_START || addr > WRAM_END) {
            return 0;
          }
          return memory[addr - WRAM_START] & 0xFF;
        }
      };
    }

    return null;
  }

  function getPotentialMemoryTargets() {
    const ejs = global.EJS_emulator;
    const gameboy = ejs && ejs.gameboy;
    const manager = ejs && ejs.gameManager;
    const managerGameboy = manager && manager.gameboy;
    const emulator = manager && manager.emulator;

    return [
      ['EJS_emulator.gameboy.getMemory()', gameboy && typeof gameboy.getMemory === 'function' ? gameboy.getMemory() : null],
      ['EJS_emulator.gameboy.memory', gameboy && gameboy.memory],
      ['EJS_emulator.gameboy.mem', gameboy && gameboy.mem],
      ['EJS_emulator.gameboy.ram', gameboy && gameboy.ram],
      ['EJS_emulator.gameManager.gameboy.getMemory()', managerGameboy && typeof managerGameboy.getMemory === 'function' ? managerGameboy.getMemory() : null],
      ['EJS_emulator.gameManager.gameboy.memory', managerGameboy && managerGameboy.memory],
      ['EJS_emulator.gameManager.emulator.getMemory()', emulator && typeof emulator.getMemory === 'function' ? emulator.getMemory() : null],
      ['EJS_emulator.getMemory()', ejs && typeof ejs.getMemory === 'function' ? ejs.getMemory() : null],
      ['EJS_emulator.memory', ejs && ejs.memory],
      ['EJS_emulator.mem', ejs && ejs.mem]
    ];
  }

  function getMemoryAccessor() {
    for (const [label, target] of getPotentialMemoryTargets()) {
      const reader = asCallableReader(target, label);
      if (reader) {
        return reader;
      }
    }
    return null;
  }

  function readU16(readByte, addr) {
    return readByte(addr) | (readByte(addr + 1) << 8);
  }

  function mapName(mapId) {
    return MAP_NAMES[mapId] || `Map_${mapId.toString(16).padStart(2, '0').toUpperCase()}`;
  }

  function speciesName(speciesId) {
    return SPECIES_NAMES[speciesId] || `Species_${speciesId}`;
  }

  function clampPartyCount(value) {
    return Number.isFinite(value) && value >= 0 && value <= 6 ? value : 0;
  }

  function getScreenType(readByte) {
    const battle = readByte(ADDR.wIsInBattle);
    const textFrame = readByte(ADDR.wTextBoxFrame);
    const textPrompt = readByte(ADDR.wTextScrollPrompt);
    const naming = readByte(ADDR.wNamingScreenType);
    const listMenu = readByte(ADDR.wListMenuID);
    const maxMenuItem = readByte(ADDR.wMaxMenuItem);

    if (battle !== 0) {
      return battle === 2 ? 'trainer_battle' : 'battle';
    }
    if (textFrame !== 0 || textPrompt !== 0) {
      return 'dialog';
    }
    if (naming !== 0) {
      return 'name_entry';
    }
    if (listMenu !== 0 || (maxMenuItem > 0 && maxMenuItem < 12)) {
      return 'menu';
    }

    return 'overworld';
  }

  function readParty(readByte) {
    const count = clampPartyCount(readByte(ADDR.wPartyCount));
    const party = [];

    for (let index = 0; index < count; index += 1) {
      const base = ADDR.wPartyMons + index * ADDR.partyMonSize;
      const species = readByte(base);
      if (species === 0 || species === 0xFF) {
        continue;
      }

      const hp = readU16(readByte, base + 1);
      const level = readByte(base + 33);
      const maxHp = readU16(readByte, base + 34);
      const status = readByte(base + 4);

      party.push({
        slot: index + 1,
        speciesId: species,
        name: speciesName(species),
        level,
        hp,
        maxHp,
        status
      });
    }

    return party;
  }

  function demoState() {
    const now = Date.now();
    const step = Math.floor(now / 1000);
    const path = [
      [1, 3], [1, 2], [2, 2], [2, 3], [3, 3], [3, 2], [2, 2], [1, 2]
    ];
    const [playerX, playerY] = path[step % path.length];
    const screens = ['overworld', 'overworld', 'dialog', 'overworld', 'menu'];

    return {
      ramAvailable: false,
      source: 'demo',
      playerX,
      playerY,
      mapId: 0x25,
      mapName: "Red's House 2F",
      screenType: screens[Math.floor(step / 4) % screens.length],
      party: [
        { slot: 1, speciesId: 79, name: 'Pikachu', level: 5, hp: 19, maxHp: 19, status: 0 },
        { slot: 2, speciesId: 170, name: 'Charmander', level: 5, hp: 18, maxHp: 18, status: 0 }
      ],
      raw: {
        note: 'EmulatorJS RAM was not exposed; showing simulated overlay data.'
      }
    };
  }

  function getRAMState() {
    const memory = getMemoryAccessor();
    if (!memory) {
      return demoState();
    }

    try {
      const readByte = memory.readByte;
      const rawX = readByte(ADDR.wPlayerX);
      const rawY = readByte(ADDR.wPlayerY);
      const mapId = readByte(ADDR.wCurMap);
      const party = readParty(readByte);

      return {
        ramAvailable: true,
        source: memory.source,
        playerX: rawX - 4,
        playerY: rawY - 4,
        rawPlayerX: rawX,
        rawPlayerY: rawY,
        mapId,
        mapName: mapName(mapId),
        screenType: getScreenType(readByte),
        party,
        raw: {
          walkCounter: readByte(ADDR.wWalkCounter),
          battle: readByte(ADDR.wIsInBattle),
          textBoxFrame: readByte(ADDR.wTextBoxFrame),
          textPrompt: readByte(ADDR.wTextScrollPrompt),
          namingScreenType: readByte(ADDR.wNamingScreenType),
          listMenuId: readByte(ADDR.wListMenuID),
          partyCount: readByte(ADDR.wPartyCount)
        }
      };
    } catch (error) {
      const state = demoState();
      state.raw.note = `RAM access failed (${error.message}); showing simulated overlay data.`;
      return state;
    }
  }

  function getMemoryStatus() {
    const memory = getMemoryAccessor();
    return memory ? { ramAvailable: true, source: memory.source } : { ramAvailable: false, source: 'demo' };
  }

  global.PokemonRAMBridge = {
    ADDR,
    getRAMState,
    getMemoryStatus
  };
  global.getRAMState = getRAMState;
})(window);
