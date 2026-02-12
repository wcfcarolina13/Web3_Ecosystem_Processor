// AptoFolio site config — global variable (preferred) + flip-card DOM fallback
window.EcoScraperSites = window.EcoScraperSites || [];
window.EcoScraperSites.push({
  id: 'aptofolio',
  name: 'AptoFolio',
  matchPatterns: [
    'https://*.aptofolio.com/*',
    'https://aptofolio.com/*'
  ],

  defaultChain: 'Aptos',

  // Strategy selection: prefer global variable, fall back to DOM scraping
  selectStrategy: function(loc) {
    // Can't check window.aptofolioData here (content script context),
    // but the engine's readPageGlobal will handle the detection.
    // Default to json_embedded; the engine will get an error and we'd
    // need a fallback. Instead, we use customScrape for full control.
    return 'custom';
  },

  strategies: {
    // Placeholder — actual logic is in customScrape below
    custom: {}
  },

  // Full custom scrape since AptoFolio has two very different code paths
  customScrape: async function(engine) {
    var projects = [];

    // Try global variable first
    try {
      engine.reportProgress(0, 100, 'Checking for aptofolioData...');
      var rawData = await engine.readPageGlobal('aptofolioData', 2000);

      if (rawData && Array.isArray(rawData) && rawData.length > 0) {
        var total = rawData.length;
        engine.reportProgress(0, total, 'Found ' + total + ' projects in aptofolioData');

        for (var i = 0; i < rawData.length && engine.isScanning(); i++) {
          var item = rawData[i];
          var project = {
            name: item.name || '',
            description: item.description || '',
            category: item.category || '',
            website: '',
            twitter: '',
            discord: '',
            chain: 'Aptos'
          };

          if (project.name) {
            projects.push(project);
          }

          if (i % 10 === 0 || i === rawData.length - 1) {
            engine.reportProgress(projects.length, total, 'Processing: ' + (project.name || '...'));
          }
          if (i % 20 === 0) {
            await engine.sleep(10);
          }
        }

        return projects;
      }
    } catch (e) {
      // Global variable not available, fall through to DOM scraping
    }

    // Fallback: DOM-based scraping with flip cards
    engine.reportProgress(0, 100, 'Falling back to DOM scraping...');
    await engine.scrollToLoadAll({ maxScrolls: 30, delay: 400 });

    var flipCards = document.querySelectorAll('.react-card-flip');
    var total = flipCards.length;
    engine.reportProgress(0, total, 'Found ' + total + ' card elements');

    var seen = {};
    for (var i = 0; i < flipCards.length && engine.isScanning(); i++) {
      var flipCard = flipCards[i];
      var front = flipCard.querySelector('.react-card-front');
      var back = flipCard.querySelector('.react-card-back');

      var name = '';
      var category = '';
      var description = '';

      if (front) {
        var titleEl = front.querySelector('h2, h3, h4, h5, h6');
        if (titleEl) name = titleEl.textContent.trim();
        var chip = front.querySelector('[class*="MuiChip"]');
        if (chip) category = chip.textContent.trim();
      }

      if (back) {
        var textContent = back.textContent || '';
        description = textContent.replace(/\d+$/, '').trim().substring(0, 300);
      }

      if (name && !seen[name]) {
        seen[name] = true;
        projects.push({
          name: name,
          category: category,
          description: description,
          website: '',
          twitter: '',
          discord: '',
          chain: 'Aptos'
        });
      }

      if (i % 5 === 0) {
        engine.reportProgress(projects.length, total, 'Scraped: ' + (name || 'Unknown'));
      }
    }

    return projects;
  },

  // Known data for projects that don't expose twitter/website in the DOM
  fallbackData: {
    twitter: {
      'Tortuga Finance': '@TortugaFinance',
      'Livepeer': '@Livepeer',
      'Bruh Bears': '@BruhBearsNFT',
      'Wormhole': '@wormholecrypto',
      'Pontem Wallet': '@PontemNetwork',
      'Apscan': '@ApscanExplorer',
      'Fewcha': '@FewchaWallet',
      'Defy': '@defydotapp',
      'Animeswap': '@AnimeSwap_Org',
      'Ziptos': '@ZiptosBot',
      'AptoRobos': '@AptoRobos',
      'Proud Lions Club': '@ProudLionsClub',
      'Panora': '@PanoraExchange',
      'Werewolf vs Witch': '@WerewolfVsWitch',
      'GUI Coinflip': '@GUICoinflip',
      'Aptin': '@AptinLabs',
      'Liquidswap': '@PontemNetwork',
      'NetSepio': '@NetSepio',
      'BRAWL3R': '@Brawl3rGame',
      'Aptos Shaker': '@AptosShaker',
      'Eragon': '@EragonGames',
      'Meso Finance': '@MesoFinance',
      'SShift DAO': '@SShiftDAO',
      'PancakeSwap': '@PancakeSwap',
      'BlockEden': '@BlockEdenHQ',
      'Spooks': '@SpooksNFT',
      'NFTScan': '@nftscan',
      'Gemfocus': '@GemfocusIO',
      'Pixel Pirates': '@PixelPiratesNFT',
      'BaptSwap': '@BaptSwap',
      'Mokshya Protocol': '@MokshyaProtocol',
      'The Loonies': '@TheLooniesNFT',
      'Chingari': '@ChingariApp',
      'OtterSec': '@osec_io',
      'Undying City': '@UndyingCity',
      'Blast API by Bware Labs': '@BwareLabs',
      'GUI INU': '@GUIINU',
      'Supervillain Labs': '@supervlabs',
      'Everstake': '@everstake_pool',
      'Aries Markets': '@AriesMarkets',
      'Yuppies Club': '@YuppiesClub',
      'Echelon': '@EchelonMarket',
      'Move Developers DAO': '@MoveDevDAO',
      'Aptos Creature': '@AptosCreature',
      'KYD Labs': '@KYDLabs',
      'Kana Labs': '@KanaLabs',
      'MAVRIK': '@MavrikNFT',
      'Baptman': '@BaptmanToken',
      'Tradeport': '@TradeportXYZ',
      'Hair Token': '@HairToken',
      'Amnis Finance': '@AmnisFinance',
      'Uptos': '@UptosToken',
      'SimpleSwap': '@SimpleSwap_io',
      'Echo Protocol': '@Echo_Protocol',
      'AA Club': '@AAClubNFT',
      'Ooga Republic': '@OogaRepublic',
      'Aptopad': '@Aptopad',
      'Aptools': '@AptoolsIO',
      'Cash Markets': '@CashMarketsIO',
      'Merkle Trade': '@MerkleTrade',
      'Sonar Watch': '@SonarWatch',
      'Cellana Finance': '@CellanaFi',
      'Wapal': '@wapal_official',
      'Topaz': '@TopazMarket',
      'Thala Labs': '@ThalaLabs',
      'Nightly': '@NightlyConnect',
      'Aptos Name Service': '@AptosNames',
      'VibrantXFinance': '@VibrantXFi',
      'Econia': '@EconiaLabs',
      'Mirage Protocol': '@MirageProtocol',
      'BlueMove': '@BlueMoveNFT',
      'Gizmo Times': '@GizmoTimes',
      'BlockPi Network': '@BlockPIHQ',
      'Seam Money': '@SeamMoney',
      'Fliptos': '@FliptosGame',
      'Aptos Monkeys': '@AptosMonkeys',
      'Wolves of Aptos': '@WolvesOfAptos',
      'Monke Sanctuaries': '@MonkeSanctuaries',
      'Petra Wallet': '@PetraWallet',
      'Martian Wallet': '@MartianWallet',
      'TowneSquare': '@TowneSquareApp',
      'GUI Gang': '@GUIGangNFT',
      'Chewy': '@ChewyCoin',
      'Donk': '@DonkCoin',
      'LOON': '@LoonOnAptos',
      'Aptomingos': '@Aptomingos',
      'Pontem Space Pirates': '@PontemPirates',
      'Indexer': '@TheIndexer',
      'Overmind': '@OvermindXYZ',
      'Aptos Arena': '@AptosArena',
      'MSafe': '@MomentumSafe',
      'Stargate Finance': '@StargateFinance',
      'LayerZero': '@LayerZero_Labs'
    },
    website: {
      'Tortuga Finance': 'https://tortuga.finance',
      'Livepeer': 'https://livepeer.org',
      'Wormhole': 'https://wormhole.com',
      'Pontem Wallet': 'https://pontem.network',
      'Liquidswap': 'https://liquidswap.com',
      'PancakeSwap': 'https://pancakeswap.finance',
      'Aries Markets': 'https://ariesmarkets.xyz',
      'Thala Labs': 'https://thalalabs.xyz',
      'Echelon': 'https://echelon.market',
      'Panora': 'https://panora.exchange',
      'Merkle Trade': 'https://merkle.trade',
      'SimpleSwap': 'https://simpleswap.io',
      'Echo Protocol': 'https://echo.xyz',
      'Aptin': 'https://aptin.io',
      'Wapal': 'https://wapal.io',
      'Topaz': 'https://topaz.so',
      'BlueMove': 'https://bluemove.net',
      'Petra Wallet': 'https://petra.app',
      'Martian Wallet': 'https://martianwallet.xyz',
      'Nightly': 'https://nightly.app',
      'Fewcha': 'https://fewcha.app',
      'Stargate Finance': 'https://stargate.finance',
      'MSafe': 'https://msafe.io'
    }
  }
});
