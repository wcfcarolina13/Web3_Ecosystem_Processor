// Content script for AptoFolio.com
// Extracts project data from the global aptofolioData variable

(function() {
  'use strict';

  let isScanning = false;
  let scrapedProjects = [];

  // Send message to extension
  function sendMessage(type, data) {
    chrome.runtime.sendMessage({ type, ...data });
  }

  // Sleep helper
  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // Known Twitter handles for Aptos projects (fallback when not in DOM)
  const KNOWN_TWITTER = {
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
  };

  // Known website URLs for projects
  const KNOWN_WEBSITES = {
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
    'Stargate Finance': 'https://stargate.finance'
  };

  // Main scraping function - uses global aptofolioData
  async function scrapeFromGlobalData() {
    scrapedProjects = [];
    isScanning = true;

    try {
      // Check for global data
      if (!window.aptofolioData || !Array.isArray(window.aptofolioData)) {
        // Wait a bit for data to load
        await sleep(2000);

        if (!window.aptofolioData) {
          throw new Error('aptofolioData not found. Page may not be fully loaded.');
        }
      }

      const rawData = window.aptofolioData;
      const total = rawData.length;

      sendMessage('scrapeProgress', {
        current: 0,
        total: total,
        message: `Found ${total} projects in aptofolioData`
      });

      // Process each project
      for (let i = 0; i < rawData.length && isScanning; i++) {
        const item = rawData[i];

        const project = {
          name: item.name || '',
          description: item.description || '',
          category: item.category || '',
          website: KNOWN_WEBSITES[item.name] || '',
          twitter: KNOWN_TWITTER[item.name] || '',
          discord: '',
          chain: 'Aptos'
        };

        // Only add if we got a name
        if (project.name) {
          scrapedProjects.push(project);
        }

        // Send progress update every 10 items
        if (i % 10 === 0 || i === rawData.length - 1) {
          sendMessage('scrapeProgress', {
            current: scrapedProjects.length,
            total: total,
            message: `Processing: ${project.name}`
          });
        }

        // Small delay to not freeze UI
        if (i % 20 === 0) {
          await sleep(10);
        }
      }

      // Complete
      sendMessage('scrapeComplete', {
        data: scrapedProjects
      });

    } catch (error) {
      console.error('Scraping error:', error);
      sendMessage('scrapeError', {
        error: error.message
      });
    }

    isScanning = false;
  }

  // Fallback: DOM-based scraping with card flipping
  async function scrapeViaDOMWithFlip() {
    scrapedProjects = [];
    isScanning = true;

    try {
      // Scroll to load all cards
      await scrollToLoadAll();

      // Find all flip card containers
      const flipCards = document.querySelectorAll('.react-card-flip');
      const total = flipCards.length;

      sendMessage('scrapeProgress', {
        current: 0,
        total: total,
        message: `Found ${total} card elements`
      });

      for (let i = 0; i < flipCards.length && isScanning; i++) {
        const flipCard = flipCards[i];
        const front = flipCard.querySelector('.react-card-front');
        const back = flipCard.querySelector('.react-card-back');

        let name = '';
        let category = '';
        let description = '';

        // Get name and category from front
        if (front) {
          const titleEl = front.querySelector('h2, h3, h4, h5, h6');
          if (titleEl) name = titleEl.textContent.trim();

          const chip = front.querySelector('[class*="MuiChip"]');
          if (chip) category = chip.textContent.trim();
        }

        // Get description from back
        if (back) {
          const textContent = back.textContent || '';
          // Remove trailing numbers and clean up
          description = textContent.replace(/\d+$/, '').trim().substring(0, 300);
        }

        if (name) {
          const project = {
            name,
            category,
            description,
            website: KNOWN_WEBSITES[name] || '',
            twitter: KNOWN_TWITTER[name] || '',
            discord: '',
            chain: 'Aptos'
          };

          // Check for duplicates
          const exists = scrapedProjects.some(p => p.name === name);
          if (!exists) {
            scrapedProjects.push(project);
          }
        }

        // Progress update
        if (i % 5 === 0) {
          sendMessage('scrapeProgress', {
            current: scrapedProjects.length,
            total: total,
            message: `Scraped: ${name || 'Unknown'}`
          });
        }
      }

      sendMessage('scrapeComplete', {
        data: scrapedProjects
      });

    } catch (error) {
      console.error('DOM scraping error:', error);
      sendMessage('scrapeError', {
        error: error.message
      });
    }

    isScanning = false;
  }

  // Scroll to load all content
  async function scrollToLoadAll() {
    const maxScrolls = 30;
    let lastHeight = 0;
    let scrollCount = 0;

    while (scrollCount < maxScrolls) {
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(400);

      const newHeight = document.body.scrollHeight;
      if (newHeight === lastHeight) break;

      lastHeight = newHeight;
      scrollCount++;

      sendMessage('scrapeProgress', {
        current: 0,
        total: 100,
        message: `Loading content... (${scrollCount})`
      });
    }

    window.scrollTo(0, 0);
    await sleep(200);
  }

  // Main entry point - try global data first, fall back to DOM
  async function startScraping() {
    // Prefer global data if available
    if (window.aptofolioData && Array.isArray(window.aptofolioData) && window.aptofolioData.length > 0) {
      console.log('[Ecosystem Scraper] Using aptofolioData global variable');
      return scrapeFromGlobalData();
    } else {
      console.log('[Ecosystem Scraper] Falling back to DOM scraping');
      return scrapeViaDOMWithFlip();
    }
  }

  // Listen for messages from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'startScraping') {
      if (!isScanning) {
        startScraping();
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, error: 'Already scanning' });
      }
      return true;
    }

    if (message.action === 'stopScraping') {
      isScanning = false;
      sendResponse({ success: true });
      return true;
    }

    if (message.action === 'getStatus') {
      sendResponse({
        isScanning,
        projectCount: scrapedProjects.length,
        hasGlobalData: !!(window.aptofolioData && window.aptofolioData.length)
      });
      return true;
    }
  });

  // Log that content script is loaded
  console.log('[Ecosystem Scraper] AptoFolio content script loaded');
  console.log('[Ecosystem Scraper] aptofolioData available:', !!(window.aptofolioData && window.aptofolioData.length));

})();
