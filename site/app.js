(() => {
  'use strict';

  const STORAGE = {
    watchlist: 'deltaconvert-watchlist-v2',
    portfolio: 'deltaconvert-portfolio-v2',
    alerts: 'deltaconvert-alerts-v2',
    digest: 'deltaconvert-digest-v2',
    focus: 'deltaconvert-focus-v2'
  };

  const STOCKS = [
    { symbol: 'AAPL', name: 'Apple', sector: 'Technology', price: 234.40, move: 1.24, momentum: 92, quality: 96, volatility: 38, income: 44, signal: 'Persistent', range: '$226–236', volume: '1.2×', note: 'Price strength remains above its short-term trend while volume is orderly.' },
    { symbol: 'NVDA', name: 'NVIDIA', sector: 'Semiconductors', price: 141.25, move: 2.83, momentum: 98, quality: 88, volatility: 82, income: 14, signal: 'Accelerating', range: '$132–143', volume: '1.8×', note: 'Buyers returned after a shallow pullback. The sample signal remains strong, though daily swings are wider.' },
    { symbol: 'HSBA', name: 'HSBC', sector: 'Financials', price: 7.14, move: 0.42, momentum: 63, quality: 84, volatility: 31, income: 91, signal: 'Steady', range: '£6.96–7.19', volume: '0.9×', note: 'The price trend is gradual. Income and capital return provide more of the sample score than momentum.' },
    { symbol: 'TSLA', name: 'Tesla', sector: 'Automotive', price: 248.90, move: -1.78, momentum: 54, quality: 59, volatility: 96, income: 0, signal: 'Unsettled', range: '$238–263', volume: '1.5×', note: 'The range is wide and the sample trend is mixed. Short-term price action carries more risk than the other names on this wall.' },
    { symbol: 'AZN', name: 'AstraZeneca', sector: 'Healthcare', price: 121.68, move: 0.18, momentum: 58, quality: 92, volatility: 24, income: 66, signal: 'Defensive', range: '£119–123', volume: '0.8×', note: 'Low realised movement and stable earnings expectations give the sample profile a defensive character.' },
    { symbol: 'MSFT', name: 'Microsoft', sector: 'Technology', price: 501.16, move: 1.06, momentum: 89, quality: 97, volatility: 35, income: 38, signal: 'Broad', range: '$488–504', volume: '1.1×', note: 'The sample signal combines strong price persistence with a high quality score and moderate realised movement.' },
    { symbol: 'SHEL', name: 'Shell', sector: 'Energy', price: 27.84, move: -0.36, momentum: 47, quality: 78, volatility: 42, income: 86, signal: 'Range-bound', range: '£27.20–28.25', volume: '0.9×', note: 'The sample price sits inside a stable range. Cash returns remain the main feature of the profile.' },
    { symbol: 'AMZN', name: 'Amazon', sector: 'Consumer', price: 226.31, move: 0.74, momentum: 82, quality: 86, volatility: 51, income: 0, signal: 'Constructive', range: '$218–229', volume: '1.0×', note: 'The sample trend is positive and above its medium-term average. Volatility remains close to the market median.' },
    { symbol: 'LLOY', name: 'Lloyds', sector: 'Financials', price: 0.67, move: 0.91, momentum: 76, quality: 71, volatility: 43, income: 89, signal: 'Improving', range: '£0.63–0.68', volume: '1.3×', note: 'The sample signal has improved with UK rate expectations. Income remains a large part of the total score.' }
  ];

  const DEFAULT_PORTFOLIO = [
    { symbol: 'MSFT', name: 'Microsoft', units: 70, price: 388.40, day: 1.06, category: 'Technology' },
    { symbol: 'AZN', name: 'AstraZeneca', units: 180, price: 121.68, day: 0.18, category: 'Healthcare' },
    { symbol: 'HSBA', name: 'HSBC', units: 3100, price: 7.14, day: 0.42, category: 'Financials' },
    { symbol: 'SHEL', name: 'Shell', units: 900, price: 27.84, day: -0.36, category: 'Infrastructure' },
    { symbol: 'CASH', name: 'Cash reserve', units: 1, price: 32105.40, day: 0, category: 'Cash' }
  ];

  const DEFAULT_ALERTS = [
    { id: cryptoId(), asset: 'GBP/USD', condition: 'rises above', threshold: '1.30', unit: 'rate', channel: 'In-app', active: true },
    { id: cryptoId(), asset: 'NVDA', condition: 'moves by more than', threshold: '4', unit: '%', channel: 'Email', active: true },
    { id: cryptoId(), asset: 'FTSE 100', condition: 'falls below', threshold: '8,000', unit: 'level', channel: 'In-app', active: false }
  ];

  /* Sample rates, EUR base, used only when the backend is unreachable so
     the interface still has numbers to render. Approximate and static;
     the pages say so on screen whenever these are in use. Cross pairs are
     derived the same way as the live ones. */
  const SAMPLE_RATES = {
    EUR: 1, AUD: 1.6467, BRL: 6.0500, CAD: 1.4908, CHF: 0.9400, CNY: 7.8500,
    CZK: 25.200, DKK: 7.4600, GBP: 0.8417, HKD: 8.4800, HUF: 395.00, IDR: 17600,
    ILS: 4.0500, INR: 90.500, ISK: 150.00, JPY: 171.38, KRW: 1490.0, MXN: 20.100,
    MYR: 5.0500, NOK: 11.600, NZD: 1.7900, PHP: 62.500, PLN: 4.2800, RON: 4.9700,
    SEK: 11.350, SGD: 1.4600, THB: 39.200, TRY: 38.500, USD: 1.0886, ZAR: 19.800
  };


  /* === Live data layer ==================================================
     The pages talk to the DeltaConvert API. The base path comes from a
     meta tag so local testing against a bare backend only needs one edit
     in the HTML head. Everything else on the site stays demo data. */

  const API_BASE = document.querySelector('meta[name="api-base"]')?.content?.trim() || '/api/v1';

  const FALLBACK_CURRENCIES = ['AUD','BRL','CAD','CHF','CNY','CZK','DKK','EUR','GBP','HKD','HUF','IDR','ILS','INR','ISK','JPY','KRW','MXN','MYR','NOK','NZD','PHP','PLN','RON','SEK','SGD','THB','TRY','USD','ZAR'];
  let CURRENCIES = [...FALLBACK_CURRENCIES];
  let FORECASTABLE = null;   // null until the backend answers

  let latestRatesCache = null;
  const historyCache = new Map();

  async function fetchJson(path, options = {}) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15000);
    try {
      const headers = { Accept: 'application/json' };
      if (options.body) headers['Content-Type'] = 'application/json';
      const response = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal });
      if (!response.ok) {
        let detail = `Request failed (${response.status})`;
        try {
          const data = await response.json();
          if (data && data.detail) detail = data.detail;
        } catch (ignored) { /* body was not JSON */ }
        throw new Error(detail);
      }
      return await response.json();
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function getLatestRates(force = false) {
    if (latestRatesCache && !force) return latestRatesCache;
    latestRatesCache = await fetchJson('/rates/latest');
    return latestRatesCache;
  }

  function crossRate(rates, from, to) {
    return rates[to] / rates[from];
  }

  async function getHistory(base, quote, days) {
    const key = `${base}/${quote}/${days}`;
    if (historyCache.has(key)) return historyCache.get(key);
    const query = new URLSearchParams({ base, quote, days: String(days) });
    const data = await fetchJson(`/rates/history?${query.toString()}`);
    historyCache.set(key, data.points);
    return data.points;
  }

  function clearLiveCaches() {
    latestRatesCache = null;
    historyCache.clear();
  }

  function isCurrencyCode(value) {
    return typeof value === 'string' && /^[A-Z]{3}$/.test(value);
  }

  function symbolFor(code) {
    try {
      const parts = new Intl.NumberFormat('en-GB', { style: 'currency', currency: code, currencyDisplay: 'narrowSymbol' }).formatToParts(1);
      const found = parts.find(part => part.type === 'currency');
      return found ? found.value : code;
    } catch (error) {
      return code;
    }
  }

  function formatRate(value) {
    return formatNumber(value, Math.abs(value) >= 100 ? 2 : 4);
  }

  function amountDecimals(code) {
    return ['JPY', 'KRW', 'IDR', 'HUF', 'ISK'].includes(code) ? 0 : 2;
  }

  function dayLabel(dateText) {
    const date = new Date(`${dateText}T00:00:00`);
    return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  }

  function movePercent(points) {
    if (!points || points.length < 2) return null;
    const previous = points[points.length - 2].rate;
    const latest = points[points.length - 1].rate;
    if (!previous) return null;
    return ((latest - previous) / previous) * 100;
  }

  function applyMove(node, percent) {
    if (!node) return;
    if (percent === null) {
      node.textContent = '·';
      return;
    }
    const sign = percent >= 0 ? '+' : '−';
    node.textContent = `${sign}${formatNumber(Math.abs(percent))}%`;
    node.classList.remove('positive', 'negative');
    node.classList.add(percent >= 0 ? 'positive' : 'negative');
  }

  function populateCurrencySelects(rebuild = false) {
    const ROLES = { fromCurrency: 'from', toCurrency: 'to', forecastFrom: 'from', forecastTo: 'to' };
    Object.keys(ROLES).forEach(id => {
      const select = document.getElementById(id);
      if (!select) return;
      const previous = select.value;
      select.innerHTML = CURRENCIES.map(code => `<option value="${escapeHtml(code)}">${escapeHtml(code)}</option>`).join('');
      const preferred = ROLES[id] === 'from' ? ['GBP', 'EUR', 'USD'] : ['EUR', 'USD', 'INR'];
      const fallback = preferred.find(code => CURRENCIES.includes(code))
        || CURRENCIES[ROLES[id] === 'from' ? 0 : 1] || CURRENCIES[0];
      select.value = CURRENCIES.includes(previous) ? previous : fallback;

      // The themed dropdown copies the options once, so it needs a fresh
      // build whenever the list changes after the first render.
      if (rebuild) {
        const wrapper = select.closest('.select-shell');
        if (wrapper) {
          wrapper.parentNode.insertBefore(select, wrapper);
          customSelects.delete(wrapper);
          wrapper.remove();
          select.classList.remove('native-select-hidden');
          delete select.dataset.customSelect;
        }
      }
    });
    if (rebuild) initCustomSelects();
  }

  /* Asks the backend what it can actually do. A deployment that supports
     a trimmed currency list, or that has only some models trained, then
     shows exactly those options rather than 30 that mostly fail. */
  async function loadCapabilities() {
    try {
      const data = await fetchJson('/currencies');
      // Codes from the API end up in markup and request URLs, so only
      // three-letter codes are accepted, whatever the backend sends.
      const listed = Array.isArray(data.supported) ? data.supported.filter(isCurrencyCode) : [];
      if (listed.length >= 2) {
        // EUR is the base every rate is quoted against; a payload without
        // it means the backend is misconfigured, and dropping EUR from the
        // interface would break the default pair and the sample fallbacks
        // too. Keep the interface whole and let the rate lookups fall back
        // to sample figures for anything the backend cannot price.
        const supported = listed.includes('EUR')
          ? listed
          : [...listed, 'EUR'].sort();
        const changed = supported.join(',') !== CURRENCIES.join(',');
        CURRENCIES = supported;
        if (changed) populateCurrencySelects(true);
      }
      FORECASTABLE = Array.isArray(data.forecastable) ? data.forecastable.filter(isCurrencyCode) : null;
    } catch (error) {
      FORECASTABLE = null;   // offline: assume nothing and say so on demand
    }
  }

  const CATEGORY_COLOURS = { Technology: '#66f2e0', Healthcare: '#fc6540', Financials: '#2cb4a4', Infrastructure: '#18785d', Cash: '#cfcfc9', Energy: '#fc6540' };

  // Category names come from stored data, so names such as "constructor"
  // or "__proto__" must not reach Object.prototype through a plain lookup.
  function categoryColour(category) {
    return Object.prototype.hasOwnProperty.call(CATEGORY_COLOURS, category) ? CATEGORY_COLOURS[category] : '#cfcfc9';
  }

  function cryptoId() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function readStore(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      if (!value) return structuredClone(fallback);
      const parsed = JSON.parse(value);
      // Stored data is outside the page's control (another script, an old
      // version, a hand edit). A value of the wrong shape falls back to the
      // defaults, so the page keeps working.
      const sameShape = Array.isArray(fallback)
        ? Array.isArray(parsed)
        : parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed);
      return sameShape ? parsed : structuredClone(fallback);
    } catch (error) {
      return JSON.parse(JSON.stringify(fallback));
    }
  }

  function writeStore(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function formatNumber(value, digits = 2) {
    // Intl.NumberFormat happily prints "NaN", so anything non-finite is
    // caught here, which covers every rate and amount on the site through
    // formatRate as well.
    const number = Number(value);
    if (!Number.isFinite(number)) return '—';
    return new Intl.NumberFormat('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(number);
  }

  function formatMoney(value, currency = 'GBP') {
    const number = Number(value);
    if (!Number.isFinite(number)) return '—';
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency, maximumFractionDigits: 2 }).format(number);
  }

  function toast(title, detail = '') {
    const region = document.getElementById('toastRegion');
    if (!region) return;
    const item = document.createElement('div');
    item.className = 'toast';
    item.innerHTML = `<strong>${escapeHtml(title)}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ''}`;
    region.appendChild(item);
    window.setTimeout(() => item.remove(), 3600);
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
  }

  function setBodyLock(locked) {
    document.body.classList.toggle('is-locked', locked);
  }

  const customSelects = new Set();

  function selectControlName(select) {
    const names = {
      fromCurrency: 'Source currency',
      toCurrency: 'Destination currency',
      rateDirection: 'Rate direction',
      alertAsset: 'Alert asset',
      alertCondition: 'Alert condition',
      alertUnit: 'Alert unit',
      digestFrequency: 'Digest frequency'
    };
    if (select.getAttribute('aria-label')) return select.getAttribute('aria-label');
    if (names[select.id]) return names[select.id];
    const label = select.closest('label');
    if (!label) return 'Choose an option';
    const text = [...label.childNodes]
      .filter(node => node.nodeType === Node.TEXT_NODE)
      .map(node => node.textContent.trim())
      .filter(Boolean)
      .join(' ');
    return text || 'Choose an option';
  }

  function closeCustomSelect(wrapper, restoreFocus = false) {
    if (!wrapper) return;
    const trigger = wrapper.querySelector('.select-trigger');
    const menu = wrapper.querySelector('.select-menu');
    wrapper.classList.remove('is-open', 'opens-up');
    trigger?.setAttribute('aria-expanded', 'false');
    if (menu) menu.hidden = true;
    if (restoreFocus) trigger?.focus();
  }

  function closeAllCustomSelects(except = null) {
    customSelects.forEach(wrapper => {
      if (wrapper !== except) closeCustomSelect(wrapper);
    });
  }

  function syncCustomSelect(select) {
    const wrapper = select?.closest('.select-shell');
    if (!wrapper) return;
    const selected = select.options[select.selectedIndex];
    const label = wrapper.querySelector('.select-trigger-label');
    if (label) label.textContent = selected?.textContent || '';
    wrapper.querySelectorAll('.select-option').forEach((option, index) => {
      const isSelected = index === select.selectedIndex;
      option.classList.toggle('is-selected', isSelected);
      option.setAttribute('aria-selected', String(isSelected));
    });
  }

  function openCustomSelect(wrapper) {
    closeAllCustomSelects(wrapper);
    const trigger = wrapper.querySelector('.select-trigger');
    const menu = wrapper.querySelector('.select-menu');
    if (!trigger || !menu) return;
    wrapper.classList.add('is-open');
    trigger.setAttribute('aria-expanded', 'true');
    menu.hidden = false;
    window.requestAnimationFrame(() => {
      const triggerRect = trigger.getBoundingClientRect();
      const menuHeight = Math.min(menu.scrollHeight, 280) + 14;
      const roomBelow = window.innerHeight - triggerRect.bottom;
      wrapper.classList.toggle('opens-up', roomBelow < menuHeight && triggerRect.top > menuHeight);
      const selected = menu.querySelector('.select-option.is-selected') || menu.querySelector('.select-option');
      selected?.focus({ preventScroll: true });
    });
  }

  function initCustomSelects() {
    document.querySelectorAll('select:not([data-custom-select])').forEach(select => {
      select.dataset.customSelect = 'ready';
      const wrapper = document.createElement('div');
      const inline = Boolean(select.closest('.rule-sentence'));
      const dark = Boolean(select.closest('.money-input, .panel-dark, .rule-studio, .pair-inline'));
      wrapper.className = `select-shell ${inline ? 'is-inline' : dark ? 'is-dark' : 'is-light'}`;
      wrapper.dataset.selectId = select.id || '';

      const longest = Math.max(...[...select.options].map(option => option.textContent.trim().length), 6);
      wrapper.style.setProperty('--select-width', `${longest + 3}ch`);

      select.parentNode.insertBefore(wrapper, select);
      wrapper.appendChild(select);
      select.classList.add('native-select-hidden');

      const menuId = `${select.id || `select-${customSelects.size + 1}`}-menu`;
      const trigger = document.createElement('button');
      trigger.type = 'button';
      trigger.className = 'select-trigger';
      trigger.setAttribute('aria-haspopup', 'listbox');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.setAttribute('aria-controls', menuId);
      trigger.setAttribute('aria-label', selectControlName(select));
      trigger.innerHTML = '<span class="select-trigger-label"></span>';

      const menu = document.createElement('div');
      menu.className = 'select-menu';
      menu.id = menuId;
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('aria-label', selectControlName(select));
      menu.hidden = true;

      [...select.options].forEach((sourceOption, index) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'select-option';
        option.setAttribute('role', 'option');
        option.dataset.optionIndex = String(index);
        option.textContent = sourceOption.textContent;
        option.disabled = sourceOption.disabled;
        option.addEventListener('click', event => {
          event.stopPropagation();
          select.selectedIndex = index;
          select.dispatchEvent(new Event('input', { bubbles: true }));
          select.dispatchEvent(new Event('change', { bubbles: true }));
          closeCustomSelect(wrapper, true);
        });
        option.addEventListener('keydown', event => {
          const options = [...menu.querySelectorAll('.select-option:not(:disabled)')];
          const current = options.indexOf(option);
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const step = event.key === 'ArrowDown' ? 1 : -1;
            options[(current + step + options.length) % options.length]?.focus();
          }
          if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            options[event.key === 'Home' ? 0 : options.length - 1]?.focus();
          }
          if (event.key === 'Escape') {
            event.preventDefault();
            closeCustomSelect(wrapper, true);
          }
        });
        menu.appendChild(option);
      });

      wrapper.append(trigger, menu);
      customSelects.add(wrapper);
      syncCustomSelect(select);

      trigger.addEventListener('click', event => {
        event.stopPropagation();
        wrapper.classList.contains('is-open') ? closeCustomSelect(wrapper) : openCustomSelect(wrapper);
      });
      trigger.addEventListener('keydown', event => {
        if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
          event.preventDefault();
          openCustomSelect(wrapper);
        }
        if (event.key === 'Escape') closeCustomSelect(wrapper);
      });
      select.addEventListener('change', () => syncCustomSelect(select));
    });

    document.addEventListener('click', () => closeAllCustomSelects());
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeAllCustomSelects();
    });
    document.addEventListener('reset', event => {
      window.setTimeout(() => {
        event.target.querySelectorAll('select[data-custom-select]').forEach(syncCustomSelect);
      }, 0);
    }, true);
    window.addEventListener('resize', () => closeAllCustomSelects());
    window.addEventListener('scroll', () => closeAllCustomSelects(), { passive: true });
    window.addEventListener('pageshow', () => closeAllCustomSelects());
    closeAllCustomSelects();
  }

  function randomSeries(points, base, spread, trend = 0) {
    const series = [];
    let current = base;
    for (let index = 0; index < points; index += 1) {
      current += (Math.random() - 0.47) * spread + trend;
      series.push(current);
    }
    return series;
  }

  /* === Chart engine ======================================================
     One interactive canvas chart used across the site. Draws a value axis
     with labels, a date axis with as many ticks as the width allows, an
     optional forecast section with a confidence band, and a crosshair with
     a tooltip that follows the pointer. Redraws on container resize, so it
     always fills its card. */

  const CHART_LINE = '#18785d';        // deep teal, as the template drew it
  const CHART_FILL_TOP = 'rgba(102, 242, 224, .42)';
  const CHART_FILL_BOTTOM = 'rgba(44, 180, 164, 0)';
  const CHART_ORANGE = '#fc6540';
  const CHART_BAND = 'rgba(102, 242, 224, .45)';
  const CHART_GRID = 'rgba(24, 25, 25, .09)';
  const CHART_AXIS_TEXT = '#7e8684';

  function niceStep(range, targetTicks) {
    const raw = range / Math.max(1, targetTicks);
    if (!isFinite(raw) || raw <= 0) return 1;
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const normalised = raw / magnitude;
    let factor = 10;
    if (normalised <= 1) factor = 1;
    else if (normalised <= 2) factor = 2;
    else if (normalised <= 2.5) factor = 2.5;
    else if (normalised <= 5) factor = 5;
    return factor * magnitude;
  }

  function decimalsForStep(step) {
    if (step >= 100) return 0;
    if (step >= 1) return 2;
    return Math.min(6, Math.max(2, Math.ceil(-Math.log10(step)) + 1));
  }

  class RateChart {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.options = options;
      this.model = null;
      this.hoverIndex = null;
      this.holder = canvas.closest('.chart-holder') || canvas.parentElement;
      this.tooltip = this.holder ? this.holder.querySelector('.chart-tooltip') : null;

      this.handleMove = event => {
        const rect = this.canvas.getBoundingClientRect();
        const point = event.touches ? event.touches[0] : event;
        this.pick(point.clientX - rect.left);
      };
      this.handleLeave = () => {
        this.hoverIndex = null;
        if (this.tooltip) this.tooltip.hidden = true;
        this.render();
      };

      canvas.addEventListener('mousemove', this.handleMove);
      canvas.addEventListener('mouseleave', this.handleLeave);
      canvas.addEventListener('touchstart', this.handleMove, { passive: true });
      canvas.addEventListener('touchmove', this.handleMove, { passive: true });
      canvas.addEventListener('touchend', this.handleLeave);

      if (typeof ResizeObserver === 'function' && this.holder) {
        this.observer = new ResizeObserver(() => this.render());
        this.observer.observe(this.holder);
      } else {
        window.addEventListener('resize', () => this.render());
      }
    }

    setData(model) {
      // Rows with non-finite values would poison the axis calculation and
      // leave the whole card blank, so they are dropped at the door.
      const finite = row => Number.isFinite(row.rate)
        && (row.lower === undefined || (Number.isFinite(row.lower) && Number.isFinite(row.upper)));
      this.model = model ? {
        ...model,
        history: (model.history || []).filter(finite),
        forecast: (model.forecast || []).filter(finite)
      } : null;
      this.hoverIndex = null;
      if (this.tooltip) this.tooltip.hidden = true;
      this.render();
    }

    get rows() {
      if (!this.model) return [];
      return [...(this.model.history || []), ...(this.model.forecast || [])];
    }

    pick(offsetX) {
      const geometry = this.geometry;
      const rows = this.rows;
      if (!geometry || rows.length < 2) return;
      const ratio = (offsetX - geometry.left) / geometry.plotWidth;
      const index = Math.round(ratio * (rows.length - 1));
      this.hoverIndex = Math.min(rows.length - 1, Math.max(0, index));
      this.render();
      this.placeTooltip();
    }

    placeTooltip() {
      const rows = this.rows;
      const geometry = this.geometry;
      if (!this.tooltip || this.hoverIndex === null || !geometry) return;
      const row = rows[this.hoverIndex];
      const isForecast = row.upper !== undefined;
      const unit = this.model.unit || '';
      const lines = [
        `<strong>${formatRate(row.rate)}${unit ? ` <em>${escapeHtml(unit)}</em>` : ''}</strong>`,
        `<span>${escapeHtml(dayLabel(row.date))}${isForecast ? ' · forecast' : ''}</span>`
      ];
      if (isForecast) lines.push(`<span>80% band ${formatRate(row.lower)} – ${formatRate(row.upper)}</span>`);
      this.tooltip.innerHTML = lines.join('');
      this.tooltip.hidden = false;
      const x = geometry.left + (this.hoverIndex / (rows.length - 1)) * geometry.plotWidth;
      const width = this.tooltip.offsetWidth || 140;
      const clamped = Math.min(Math.max(x, width / 2 + 4), geometry.width - width / 2 - 4);
      this.tooltip.style.left = `${clamped}px`;
    }

    render() {
      const canvas = this.canvas;
      const rows = this.rows;
      if (!canvas) return;
      if (rows.length < 2) {
        const context = canvas.getContext('2d');
        if (context) context.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }

      const cssWidth = Math.max(240, this.holder ? this.holder.clientWidth : canvas.clientWidth);
      const cssHeight = this.options.height || 280;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(cssWidth * ratio);
      canvas.height = Math.round(cssHeight * ratio);
      canvas.style.width = '100%';
      canvas.style.height = `${cssHeight}px`;
      const context = canvas.getContext('2d');
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, cssWidth, cssHeight);
      context.font = '600 10px "Helvetica Neue", Helvetica, Arial, sans-serif';

      // --- value scale -------------------------------------------------
      const values = [];
      rows.forEach(row => {
        values.push(row.rate);
        if (row.lower !== undefined) values.push(row.lower, row.upper);
      });
      let low = Math.min(...values);
      let high = Math.max(...values);
      if (high === low) { high = low * 1.001 || 1; low = low * 0.999 || 0; }
      const step = niceStep(high - low, 4);
      const decimals = decimalsForStep(step);
      const axisMin = Math.floor(low / step) * step;
      const axisMax = Math.ceil(high / step) * step;
      const ticks = [];
      for (let value = axisMin; value <= axisMax + step / 2; value += step) ticks.push(value);

      const labels = ticks.map(value => formatNumber(value, decimals));
      const labelWidth = Math.max(...labels.map(text => context.measureText(text).width));
      const left = Math.round(labelWidth) + 18;
      const right = 14;
      const top = 16;
      const bottom = 30;
      const plotWidth = Math.max(40, cssWidth - left - right);
      const plotHeight = Math.max(40, cssHeight - top - bottom);
      this.geometry = { left, top, plotWidth, plotHeight, width: cssWidth, height: cssHeight };

      const x = index => left + (index / (rows.length - 1)) * plotWidth;
      const y = value => top + (1 - (value - axisMin) / (axisMax - axisMin)) * plotHeight;

      // --- gridlines and value labels ----------------------------------
      context.textBaseline = 'middle';
      context.textAlign = 'right';
      ticks.forEach((value, index) => {
        const position = y(value);
        context.beginPath();
        context.moveTo(left, position);
        context.lineTo(left + plotWidth, position);
        context.lineWidth = 1;
        context.strokeStyle = CHART_GRID;
        context.stroke();
        context.fillStyle = CHART_AXIS_TEXT;
        context.fillText(labels[index], left - 8, position);
      });

      const historyLength = (this.model.history || []).length;
      const forecast = this.model.forecast || [];

      // --- confidence band ---------------------------------------------
      if (forecast.length) {
        const anchor = historyLength - 1;
        context.beginPath();
        context.moveTo(x(anchor), y(rows[anchor].rate));
        forecast.forEach((row, index) => context.lineTo(x(historyLength + index), y(row.upper)));
        for (let index = forecast.length - 1; index >= 0; index -= 1) {
          context.lineTo(x(historyLength + index), y(forecast[index].lower));
        }
        context.closePath();
        context.fillStyle = CHART_BAND;
        context.fill();

        context.beginPath();
        context.moveTo(x(anchor), top);
        context.lineTo(x(anchor), top + plotHeight);
        context.setLineDash([3, 4]);
        context.lineWidth = 1;
        context.strokeStyle = 'rgba(24,25,25,.3)';
        context.stroke();
        context.setLineDash([]);
      }

      // --- history area fill ---------------------------------------------
      const baseline = top + plotHeight;
      const gradient = context.createLinearGradient(0, top, 0, baseline);
      gradient.addColorStop(0, CHART_FILL_TOP);
      gradient.addColorStop(1, CHART_FILL_BOTTOM);
      context.beginPath();
      context.moveTo(x(0), baseline);
      for (let index = 0; index < historyLength; index += 1) {
        context.lineTo(x(index), y(rows[index].rate));
      }
      context.lineTo(x(historyLength - 1), baseline);
      context.closePath();
      context.fillStyle = gradient;
      context.fill();

      // --- history line -------------------------------------------------
      context.beginPath();
      for (let index = 0; index < historyLength; index += 1) {
        const px = x(index);
        const py = y(rows[index].rate);
        if (index === 0) context.moveTo(px, py);
        else context.lineTo(px, py);
      }
      context.lineWidth = 3;
      context.lineCap = 'round';
      context.lineJoin = 'round';
      context.strokeStyle = CHART_LINE;
      context.stroke();

      // --- forecast line -------------------------------------------------
      if (forecast.length) {
        context.beginPath();
        context.moveTo(x(historyLength - 1), y(rows[historyLength - 1].rate));
        forecast.forEach((row, index) => context.lineTo(x(historyLength + index), y(row.rate)));
        context.setLineDash([7, 6]);
        context.strokeStyle = CHART_ORANGE;
        context.stroke();
        context.setLineDash([]);
      }

      // --- end markers ---------------------------------------------------
      const mark = (index, colour, radius) => {
        context.beginPath();
        context.arc(x(index), y(rows[index].rate), radius, 0, Math.PI * 2);
        context.fillStyle = colour;
        context.fill();
      };
      if (forecast.length) {
        mark(historyLength - 1, CHART_LINE, 3.5);
        mark(rows.length - 1, CHART_ORANGE, 5);
      } else {
        mark(rows.length - 1, CHART_ORANGE, 5);
      }

      // --- date axis ------------------------------------------------------
      context.textBaseline = 'top';
      context.fillStyle = CHART_AXIS_TEXT;
      const maxLabels = Math.max(2, Math.floor(plotWidth / 82));
      const stride = Math.max(1, Math.ceil((rows.length - 1) / (maxLabels - 1)));
      const shown = new Set();
      for (let index = 0; index < rows.length; index += stride) shown.add(index);
      shown.add(rows.length - 1);
      if (forecast.length) shown.add(historyLength - 1);
      [...shown].sort((a, b) => a - b).forEach(index => {
        const position = x(index);
        context.textAlign = index === 0 ? 'left' : index === rows.length - 1 ? 'right' : 'centre';
        // Canvas uses "center"; keep both spellings safe.
        context.textAlign = index === 0 ? 'left' : index === rows.length - 1 ? 'right' : 'center';
        context.fillText(dayLabel(rows[index].date), position, top + plotHeight + 9);
      });

      // --- crosshair -------------------------------------------------------
      if (this.hoverIndex !== null && this.hoverIndex < rows.length) {
        const row = rows[this.hoverIndex];
        const px = x(this.hoverIndex);
        context.beginPath();
        context.moveTo(px, top);
        context.lineTo(px, top + plotHeight);
        context.setLineDash([2, 3]);
        context.lineWidth = 1;
        context.strokeStyle = 'rgba(24,25,25,.45)';
        context.stroke();
        context.setLineDash([]);
        context.beginPath();
        context.arc(px, y(row.rate), 5, 0, Math.PI * 2);
        context.fillStyle = row.upper !== undefined ? CHART_ORANGE : CHART_LINE;
        context.fill();
        context.lineWidth = 2;
        context.strokeStyle = '#ffffff';
        context.stroke();
      }
    }
  }

  function drawDoughnut(canvas, segments, hoverIndex = null) {
    if (!canvas) return null;
    const holder = canvas.closest('.chart-holder') || canvas.parentElement;
    const cssWidth = Math.max(180, holder ? holder.clientWidth : canvas.clientWidth || 310);
    const cssHeight = cssWidth;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(cssWidth * ratio);
    canvas.height = Math.round(cssHeight * ratio);
    canvas.style.width = '100%';
    canvas.style.height = 'auto';
    const context = canvas.getContext('2d');
    if (!context) return null;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const total = segments.reduce((sum, segment) => sum + segment.value, 0) || 1;
    const centreX = cssWidth / 2;
    const centreY = cssHeight / 2;
    const radius = Math.min(cssWidth, cssHeight) * 0.41;
    const inner = radius * 0.62;
    let angle = -Math.PI / 2;
    const arcs = [];
    context.clearRect(0, 0, cssWidth, cssHeight);
    segments.forEach((segment, index) => {
      const sweep = (segment.value / total) * Math.PI * 2;
      const lift = index === hoverIndex ? 4 : 0;
      context.beginPath();
      context.arc(centreX, centreY, radius + lift, angle, angle + sweep);
      context.arc(centreX, centreY, inner, angle + sweep, angle, true);
      context.closePath();
      context.fillStyle = segment.colour;
      context.fill();
      arcs.push({ start: angle, end: angle + sweep, index });
      angle += sweep;
    });
    return { centreX, centreY, radius, inner, arcs, total };
  }


  function initGlobal() {
    const menuButton = document.querySelector('[data-action="menu"]');
    const closeMenu = () => {
      document.body.classList.remove('menu-open');
      menuButton?.setAttribute('aria-expanded', 'false');
    };
    menuButton?.addEventListener('click', () => {
      const open = document.body.classList.toggle('menu-open');
      menuButton.setAttribute('aria-expanded', String(open));
    });
    document.querySelector('[data-action="close-menu"]')?.addEventListener('click', closeMenu);
    document.querySelectorAll('.nav-link').forEach(link => link.addEventListener('click', closeMenu));

    const command = document.getElementById('commandPalette');
    const commandInput = document.getElementById('commandInput');
    const commandItems = [...document.querySelectorAll('[data-command-item]')];
    const openCommand = () => {
      command.hidden = false;
      setBodyLock(true);
      window.setTimeout(() => commandInput?.focus(), 10);
    };
    const closeCommand = () => {
      command.hidden = true;
      setBodyLock(false);
      if (commandInput) {
        commandInput.value = '';
        commandItems.forEach(item => { item.hidden = false; });
      }
    };
    document.querySelectorAll('.js-command').forEach(button => button.addEventListener('click', openCommand));
    document.querySelector('[data-action="close-command"]')?.addEventListener('click', closeCommand);
    command?.addEventListener('click', event => { if (event.target === command) closeCommand(); });
    commandInput?.addEventListener('input', () => {
      const query = commandInput.value.trim().toLowerCase();
      commandItems.forEach(item => { item.hidden = !item.textContent.toLowerCase().includes(query); });
    });

    const profileButton = document.querySelector('.js-profile');
    const profileMenu = document.getElementById('profileMenu');
    profileButton?.addEventListener('click', event => {
      event.stopPropagation();
      const nextHidden = !profileMenu.hidden;
      profileMenu.hidden = nextHidden;
      profileButton.setAttribute('aria-expanded', String(!nextHidden));
    });
    document.addEventListener('click', event => {
      if (!profileMenu?.hidden && !profileMenu.contains(event.target) && event.target !== profileButton) {
        profileMenu.hidden = true;
        profileButton?.setAttribute('aria-expanded', 'false');
      }
    });

    const focusActive = localStorage.getItem(STORAGE.focus) === 'true';
    document.body.classList.toggle('focus-mode', focusActive);

    document.querySelector('[data-action="focus-mode"]')?.addEventListener('click', () => {
      const active = document.body.classList.toggle('focus-mode');
      localStorage.setItem(STORAGE.focus, String(active));
      profileMenu.hidden = true;
      toast(active ? 'Focus mode is on' : 'Focus mode is off', 'The navigation and header will fade until you move over them.');
    });

    document.querySelector('[data-action="clear-local-data"]')?.addEventListener('click', () => {
      Object.values(STORAGE).forEach(key => localStorage.removeItem(key));
      toast('Demo data reset', 'The page will reload with its starting values.');
      window.setTimeout(() => window.location.reload(), 700);
    });

    document.querySelectorAll('.js-refresh').forEach(button => {
      button.addEventListener('click', () => {
        document.querySelectorAll('.js-refresh').forEach(item => item.classList.add('is-spinning'));
        window.setTimeout(() => {
          document.querySelectorAll('.js-refresh').forEach(item => item.classList.remove('is-spinning'));
          document.querySelectorAll('[data-last-updated]').forEach(item => { item.textContent = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); });
          document.dispatchEvent(new CustomEvent('demo:refresh'));
          toast('Feed refreshed', 'Live rates were re-checked and demo figures recalculated.');
        }, 550);
      });
    });

    document.addEventListener('keydown', event => {
      const commandKey = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
      if (commandKey) {
        event.preventDefault();
        command.hidden ? openCommand() : closeCommand();
      }
      if (event.key === 'Escape') {
        if (!command.hidden) closeCommand();
        closeMenu();
        closeStockDrawer();
        closeHoldingModal();
      }
      if (event.key === '/' && document.body.dataset.page === 'markets' && document.activeElement?.tagName !== 'INPUT') {
        event.preventDefault();
        document.getElementById('marketSearch')?.focus();
      }
    });
  }

  function getWatchlist() {
    return readStore(STORAGE.watchlist, ['AAPL', 'NVDA', 'HSBA']);
  }

  function toggleWatch(symbol) {
    const list = getWatchlist();
    const index = list.indexOf(symbol);
    if (index >= 0) list.splice(index, 1);
    else list.push(symbol);
    writeStore(STORAGE.watchlist, list);
    toast(index >= 0 ? `${symbol} removed` : `${symbol} added`, index >= 0 ? 'The name has left your watchlist.' : 'The name is now in your watchlist.');
    document.dispatchEvent(new CustomEvent('watchlist:change'));
  }

  function initDashboard() {
    const container = document.querySelector('[data-dashboard-watchlist]');
    if (!container) return;

    const render = () => {
      const selected = getWatchlist().map(symbol => STOCKS.find(stock => stock.symbol === symbol)).filter(Boolean).slice(0, 5);
      container.innerHTML = selected.length ? selected.map(stock => `
        <div class="watch-row">
          <span class="watch-row-name"><strong>${stock.symbol}</strong><small>${stock.name}</small></span>
          <strong>${stock.symbol === 'LLOY' ? '£' : '$'}${formatNumber(stock.price)}</strong>
          <button class="watch-toggle is-watched" type="button" data-dashboard-watch="${stock.symbol}" aria-label="Remove ${stock.symbol} from watchlist">−</button>
        </div>`).join('') : '<div class="watch-summary-empty">Your watchlist is empty. Open Markets to pin a stock.</div>';
    };

    container.addEventListener('click', event => {
      const button = event.target.closest('[data-dashboard-watch]');
      if (button) toggleWatch(button.dataset.dashboardWatch);
    });
    document.addEventListener('watchlist:change', render);
    document.addEventListener('demo:refresh', () => {
      const pulse = document.querySelector('[data-pulse-number]');
      if (pulse) pulse.textContent = String(Math.round(58 + Math.random() * 18));
    });
    render();
  }

  function initExchange() {
    const fromAmount = document.getElementById('fromAmount');
    if (!fromAmount) return;

    const fromCurrency = document.getElementById('fromCurrency');
    const toCurrency = document.getElementById('toCurrency');
    const fromSymbol = document.getElementById('fromSymbol');
    const toSymbol = document.getElementById('toSymbol');
    const toAmount = document.getElementById('toAmount');
    const routeCode = document.getElementById('routeCode');
    const quoteRate = document.getElementById('quoteRate');
    const quoteFee = document.getElementById('quoteFee');
    const chartRate = document.getElementById('chartRate');
    const chartTitle = document.getElementById('rateChartTitle');
    const chartUnit = document.getElementById('rateChartUnit');
    const chartMove = document.getElementById('chartMove');
    const sourceNote = document.getElementById('rateSourceNote');

    const forecastTitle = document.getElementById('forecastTitle');
    const forecastUnit = document.getElementById('forecastUnit');
    const forecastStatus = document.getElementById('forecastStatus');
    const forecastSummary = document.getElementById('forecastSummary');
    const forecastEndRate = document.getElementById('forecastEndRate');
    const forecastChange = document.getElementById('forecastChange');
    const forecastBand = document.getElementById('forecastBand');
    const forecastBody = document.getElementById('forecastTableBody');
    const forecastTableWrap = document.getElementById('forecastTableWrap');
    const forecastFrom = document.getElementById('forecastFrom');
    const forecastTo = document.getElementById('forecastTo');
    const scoreboard = document.getElementById('forecastScoreboard');

    const liveChart = new RateChart(document.getElementById('fxChart'), { height: 300 });
    const forecastChart = new RateChart(document.getElementById('forecastChart'), { height: 320 });

    const RANGE_DAYS = { '1W': 7, '1M': 30, '6M': 182, '1Y': 365 };
    let feeRate = 0.0016;
    let range = '1M';
    let horizon = 30;
    let timer = 30;
    let timerHandle;
    let liveRates = null;
    // Each forecast run takes a ticket; a response only renders if its
    // ticket is still the newest, so rapid pair or horizon changes cannot
    // paint a stale forecast over a fresh one.
    let runSeq = 0;

    const pairText = () => `1 ${fromCurrency.value} in ${toCurrency.value}`;

    /* One selected pair, two controls. The converter selects at the top and
       the pair control beside the horizon pills are views of the same state:
       writing goes through setPair, which also repairs anything invalid, so
       an empty or unknown value (browser form restoration is one source)
       self-heals to a sensible default instead of surfacing as NaN. */
    const setPair = (from, to) => {
      if (!CURRENCIES.includes(from)) from = CURRENCIES.includes('GBP') ? 'GBP' : CURRENCIES[0];
      if (!CURRENCIES.includes(to) || to === from) {
        to = ['EUR', 'USD', 'GBP'].find(code => code !== from && CURRENCIES.includes(code))
          || CURRENCIES.find(code => code !== from);
      }
      [fromCurrency, forecastFrom].forEach(select => { if (select) select.value = from; });
      [toCurrency, forecastTo].forEach(select => { if (select) select.value = to; });
      [fromCurrency, toCurrency, forecastFrom, forecastTo].forEach(select => { if (select) syncCustomSelect(select); });
    };

    const rateFor = (from, to) => {
      // A valid currency code can still be absent from a payload (a trimmed
      // backend, a partial outage), and dividing by a missing entry yields
      // NaN. Anything non-finite becomes null so callers take their
      // fallback paths instead of painting NaN into the page.
      let rate = null;
      if (liveRates) rate = crossRate(liveRates.rates, from, to);
      if (!Number.isFinite(rate) && SAMPLE_RATES[from] && SAMPLE_RATES[to]) rate = crossRate(SAMPLE_RATES, from, to);
      return Number.isFinite(rate) ? rate : null;
    };

    const setSourceNote = () => {
      if (!sourceNote) return;
      sourceNote.textContent = liveRates
        ? `European Central Bank reference rates for ${dayLabel(liveRates.rate_date)}, published once each business day. Indicative only; bank and card rates differ. Fees and settlement paces on this page are demo values.`
        : 'Live rates unavailable — sample figures shown. Use Refresh to try again.';
    };

    // --- live rate chart -------------------------------------------------
    const drawLive = async () => {
      const from = fromCurrency.value;
      const to = toCurrency.value;
      try {
        const points = await getHistory(from, to, RANGE_DAYS[range]);
        if (from !== fromCurrency.value || to !== toCurrency.value) return;
        liveChart.setData({ history: points, forecast: [], unit: `${to} per 1 ${from}` });
        chartRate.textContent = formatRate(points[points.length - 1].rate);
        applyMove(chartMove, movePercent(points));
      } catch (error) {
        const rate = rateFor(from, to);
        if (rate === null) return;
        const spread = { '1W': rate * .0017, '1M': rate * .0032, '6M': rate * .006, '1Y': rate * .008 }[range];
        const values = randomSeries(RANGE_DAYS[range] > 60 ? 90 : 40, rate * .994, spread, rate * .00003);
        values[values.length - 1] = rate;
        const cursor = new Date();
        const dates = [];
        cursor.setDate(cursor.getDate() - 1);
        while (dates.length < values.length) {
          if (cursor.getDay() !== 0 && cursor.getDay() !== 6) dates.push(isoDate(cursor));
          cursor.setDate(cursor.getDate() - 1);
        }
        dates.reverse();
        liveChart.setData({
          history: values.map((value, index) => ({ date: dates[index], rate: Number(value.toFixed(6)) })),
          forecast: [],
          unit: `${to} per 1 ${from}`
        });
        chartRate.textContent = formatRate(rate);
        if (chartMove) chartMove.textContent = '·';
      }
    };

    const resetTimer = () => {
      window.clearInterval(timerHandle);
      timer = 30;
      const timerNode = document.getElementById('quoteTimer');
      if (!timerNode) return;
      timerNode.textContent = '00:30';
      timerHandle = window.setInterval(() => {
        timer -= 1;
        timerNode.textContent = `00:${String(Math.max(0, timer)).padStart(2, '0')}`;
        if (timer <= 0) {
          window.clearInterval(timerHandle);
          timerNode.textContent = 'Expired';
        }
      }, 1000);
    };

    const calculate = (redraw = true) => {
      setPair(fromCurrency.value, toCurrency.value);
      const amount = Math.max(0, Number(fromAmount.value) || 0);
      const rate = rateFor(fromCurrency.value, toCurrency.value);
      fromSymbol.textContent = symbolFor(fromCurrency.value);
      toSymbol.textContent = symbolFor(toCurrency.value);
      routeCode.textContent = `${fromCurrency.value}/${toCurrency.value}`;
      chartTitle.textContent = `${fromCurrency.value} to ${toCurrency.value}`;
      if (chartUnit) chartUnit.textContent = `${toCurrency.value} per 1 ${fromCurrency.value}`;
      if (forecastTitle) forecastTitle.textContent = pairText();
      if (forecastUnit) forecastUnit.textContent = `${toCurrency.value} per 1 ${fromCurrency.value}`;
      if (rate === null) {
        toAmount.textContent = '—';
        quoteRate.textContent = '—';
        quoteFee.textContent = '—';
      } else {
        const fee = amount * feeRate;
        toAmount.textContent = formatNumber(Math.max(0, amount - fee) * rate, amountDecimals(toCurrency.value));
        quoteRate.textContent = formatRate(rate);
        quoteFee.textContent = `${symbolFor(fromCurrency.value)}${formatNumber(fee)}`;
      }
      setSourceNote();
      if (redraw) drawLive();
      resetTimer();
    };

    // --- forecast ---------------------------------------------------------
    const renderForecastTable = forecast => {
      if (!forecastBody) return;
      forecastBody.innerHTML = forecast.map(row => `<tr>
        <td>${escapeHtml(dayLabel(row.date))}</td>
        <td><strong>${formatRate(row.rate)}</strong></td>
        <td>${formatRate(row.lower)}</td>
        <td>${formatRate(row.upper)}</td>
      </tr>`).join('');
      if (forecastTableWrap) forecastTableWrap.hidden = false;
    };

    const showForecast = (history, forecast, note) => {
      const nowRate = history[history.length - 1].rate;
      const endPoint = forecast[forecast.length - 1];
      const changePct = ((endPoint.rate - nowRate) / nowRate) * 100;
      forecastEndRate.textContent = formatRate(endPoint.rate);
      forecastChange.textContent = `${changePct >= 0 ? '+' : '−'}${formatNumber(Math.abs(changePct))}%`;
      forecastBand.textContent = `${formatRate(endPoint.lower)} – ${formatRate(endPoint.upper)}`;
      forecastSummary.hidden = false;
      forecastChart.setData({
        history,
        forecast,
        unit: `${toCurrency.value} per 1 ${fromCurrency.value}`
      });
      renderForecastTable(forecast);
      forecastStatus.textContent = note;
    };

    const runForecast = async () => {
      const seq = ++runSeq;
      const from = fromCurrency.value;
      const to = toCurrency.value;
      if (from === to) return;

      if (!pairForecastable()) {
        // No trained model for this pair: say so, clear the derived
        // figures, and draw the recent history on its own so the section
        // still shows the pair rather than going blank.
        const missing = [from, to].filter(code => !FORECASTABLE.includes(code));
        forecastStatus.textContent = `No trained model for ${missing.join(' and ')} yet, so ${pairText()} cannot be forecast. Trained pairs: ${FORECASTABLE.join(', ')}.`;
        forecastSummary.hidden = true;
        if (forecastTableWrap) forecastTableWrap.hidden = true;
        try {
          const points = await getHistory(from, to, 60);
          if (seq !== runSeq) return;
          forecastChart.setData({ history: points, forecast: [], unit: `${to} per 1 ${from}` });
        } catch (error) {
          if (seq === runSeq) forecastChart.setData(null);
        }
        return;
      }

      forecastStatus.textContent = `Running the model for ${pairText()}…`;
      try {
        const data = await fetchJson('/predict', {
          method: 'POST',
          body: JSON.stringify({ from_currency: from, to_currency: to, days: horizon })
        });
        if (seq !== runSeq) return;
        const rows = data.forecast || [];
        // Rows typed 'indicative' carry the last published rate forward
        // across weekends and holidays, so they belong to the history line
        // but must not be quoted as a published ECB rate.
        const history = rows.filter(row => row.type !== 'forecast');
        const forecast = rows.filter(row => row.type === 'forecast');
        const published = rows.filter(row => row.type === 'history');
        if (!history.length || !forecast.length) throw new Error('the model returned no usable points');
        const publishedTo = published.length ? dayLabel(published[published.length - 1].date) : dayLabel(history[0].date);
        showForecast(history, forecast,
          `Model estimate for ${pairText()} over ${horizon} days, built on ECB reference rates published to ${publishedTo}. The dashed divider marks today; the band covers roughly 80 per cent of outcomes and widens with the horizon. Indicative only and often wrong.`);
      } catch (error) {
        if (seq !== runSeq) return;
        const preview = buildPreviewForecast(horizon, rateFor(from, to) || 1.1881);
        showForecast(preview.history, preview.forecast,
          `Preview only — the forecast service is not connected (${error.message}), so every figure in this section is a sample shown to check the layout.`);
      }
    };

    const loadScoreboard = async () => {
      if (!scoreboard) return;
      try {
        const data = await fetchJson('/audit/scoreboard');
        const rows = data.scoreboard || [];
        scoreboard.innerHTML = rows.length ? rows.map(row => `
          <div class="scoreboard-row">
            <strong>${escapeHtml(row.currency)}</strong>
            <span class="score-pred"><small>Forecast</small>${escapeHtml(row.pred)}</span>
            <span class="score-actual"><small>Actual</small>${escapeHtml(row.actual)}</span>
            <span class="score-status ${escapeHtml(row.status)}">${escapeHtml(row.label)}</span>
          </div>`).join('') : '<div class="rules-empty">No resolved forecasts yet. Rows appear after the first daily audit.</div>';
      } catch (error) {
        scoreboard.innerHTML = '<div class="rules-empty">The track record needs the backend. This panel fills in once the API is connected.</div>';
      }
    };

    const updateCorridors = () => {
      document.querySelectorAll('[data-corridor]').forEach(async button => {
        const [from, to] = button.dataset.corridor.split(',');
        const rateNode = button.querySelector('[data-corridor-rate]');
        const moveNode = button.querySelector('[data-corridor-move]');
        try {
          const points = await getHistory(from, to, 7);
          if (rateNode) rateNode.textContent = formatRate(points[points.length - 1].rate);
          applyMove(moveNode, movePercent(points));
        } catch (error) {
          const fallback = SAMPLE_RATES[from] && SAMPLE_RATES[to] ? crossRate(SAMPLE_RATES, from, to) : null;
          if (rateNode) rateNode.textContent = fallback === null ? '—' : formatRate(fallback);
          if (moveNode) moveNode.textContent = '·';
        }
      });
    };

    const loadLive = async (force = false) => {
      await loadCapabilities();
      if (!pinned) {
        pinned = true;
        setPair(initialPair[0], initialPair[1]);
      }
      try {
        liveRates = await getLatestRates(force);
        document.querySelectorAll('[data-last-updated]').forEach(node => { node.textContent = dayLabel(liveRates.rate_date); });
      } catch (error) {
        liveRates = null;
        toast('Live rates unavailable', 'Sample figures are shown until the connection returns.');
      }
      calculate();
      updateCorridors();
      // The forecast loads itself for the selected pair; nobody has to
      // scroll down and press anything to see it.
      runForecast();
    };

    // --- wiring -------------------------------------------------------------
    const params = new URLSearchParams(window.location.search);
    let initialPair = ['GBP', 'EUR'];
    const pair = params.get('pair');
    if (pair && pair.length === 6) {
      const from = pair.slice(0, 3).toUpperCase();
      const to = pair.slice(3).toUpperCase();
      if (CURRENCIES.includes(from) && CURRENCIES.includes(to) && from !== to) {
        initialPair = [from, to];
      }
    }
    // Every visit and refresh opens on this pair. Chrome can write
    // remembered values back into selects after scripts have run, so the
    // pin is applied now and re-applied once on the first live load,
    // which lands after that restoration window.
    setPair(initialPair[0], initialPair[1]);
    let pinned = false;
    window.addEventListener('pageshow', event => {
      if (event.persisted) {
        setPair(initialPair[0], initialPair[1]);
        pairChanged();
      }
    });
    const daysParam = Number(params.get('days'));
    if ([7, 30, 60, 90].includes(daysParam)) {
      horizon = daysParam;
      document.querySelectorAll('[data-horizon]').forEach(button => {
        button.classList.toggle('is-selected', Number(button.dataset.horizon) === horizon);
      });
    }

    // A pair is forecastable when both legs have a trained model. Until
    // the backend answers, assume yes so the offline preview still draws.
    const pairForecastable = () => {
      if (!FORECASTABLE) return true;
      return FORECASTABLE.includes(fromCurrency.value) && FORECASTABLE.includes(toCurrency.value);
    };

    const pairChanged = () => {
      calculate();
      runForecast();
    };

    fromAmount.addEventListener('input', () => calculate(false));
    fromCurrency.addEventListener('change', pairChanged);
    toCurrency.addEventListener('change', pairChanged);
    forecastFrom?.addEventListener('change', () => {
      setPair(forecastFrom.value, forecastTo ? forecastTo.value : toCurrency.value);
      pairChanged();
    });
    forecastTo?.addEventListener('change', () => {
      setPair(fromCurrency.value, forecastTo.value);
      pairChanged();
    });
    document.querySelectorAll('[data-quick-amount]').forEach(button => button.addEventListener('click', () => {
      fromAmount.value = button.dataset.quickAmount;
      calculate(false);
    }));
    document.querySelectorAll('[data-action="swap-currencies"]').forEach(button => button.addEventListener('click', () => {
      setPair(toCurrency.value, fromCurrency.value);
      pairChanged();
    }));
    document.querySelectorAll('[data-settlement]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('[data-settlement]').forEach(item => item.classList.remove('is-selected'));
      button.classList.add('is-selected');
      feeRate = Number(button.dataset.fee);
      calculate(false);
    }));
    document.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('[data-range]').forEach(item => item.classList.remove('is-selected'));
      button.classList.add('is-selected');
      range = button.dataset.range;
      drawLive();
    }));
    document.querySelectorAll('[data-horizon]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('[data-horizon]').forEach(item => item.classList.remove('is-selected'));
      button.classList.add('is-selected');
      horizon = Number(button.dataset.horizon);
      runForecast();
    }));
    document.querySelector('[data-action="lock-quote"]')?.addEventListener('click', () => {
      calculate(false);
      toast('Demo quote locked', `${routeCode.textContent} is held for 30 seconds in this sample flow. Nothing is traded.`);
    });
    document.querySelector('[data-action="save-rate-alert"]')?.addEventListener('click', () => {
      const target = document.getElementById('rateTarget').value;
      const direction = document.getElementById('rateDirection').value;
      const alerts = readStore(STORAGE.alerts, DEFAULT_ALERTS);
      alerts.unshift({ id: cryptoId(), asset: routeCode.textContent, condition: direction === 'above' ? 'rises above' : 'falls below', threshold: target, unit: 'rate', channel: 'In-app', active: true });
      writeStore(STORAGE.alerts, alerts);
      toast('Rate alert saved', `${routeCode.textContent} will be checked against ${target} in the local demo.`);
    });
    document.querySelectorAll('[data-corridor]').forEach(button => button.addEventListener('click', () => {
      const [from, to] = button.dataset.corridor.split(',');
      setPair(from, to);
      pairChanged();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }));
    document.addEventListener('demo:refresh', () => {
      clearLiveCaches();
      loadLive(true);
      loadScoreboard();
    });

    calculate(false);
    loadLive();
    loadScoreboard();
  }


  let activeStock = null;
  let stockChart = null;

  function initMarkets() {
    const wall = document.getElementById('marketWall');
    if (!wall) return;
    const search = document.getElementById('marketSearch');
    const summary = document.getElementById('watchSummary');
    let mode = 'momentum';

    const renderSummary = () => {
      const list = getWatchlist();
      const selected = list.map(symbol => STOCKS.find(stock => stock.symbol === symbol)).filter(Boolean);
      document.querySelectorAll('[data-watch-count]').forEach(node => { node.textContent = `${selected.length} ${selected.length === 1 ? 'name' : 'names'}`; });
      summary.innerHTML = selected.length ? selected.slice(0, 5).map(stock => `<div class="watch-summary-item"><strong>${stock.symbol}</strong><span class="${stock.move >= 0 ? 'positive' : 'negative'}">${stock.move >= 0 ? '+' : '−'}${formatNumber(Math.abs(stock.move))}%</span></div>`).join('') : '<div class="watch-summary-empty">Pin a stock on the signal wall to build this list.</div>';
    };

    const render = () => {
      const query = search.value.trim().toLowerCase();
      const watchlist = getWatchlist();
      const ranked = [...STOCKS]
        .filter(stock => `${stock.symbol} ${stock.name} ${stock.sector}`.toLowerCase().includes(query))
        .sort((a, b) => b[mode] - a[mode]);

      wall.innerHTML = ranked.length ? ranked.map((stock, index) => {
        const series = randomSeries(8, 45, 7, stock.move >= 0 ? 1.1 : -.8);
        const points = series.map((value, pointIndex) => `${(pointIndex / 7) * 180},${90 - value}`).join(' ');
        return `<article class="stock-tile" data-stock-card="${stock.symbol}">
          <div class="stock-tile-head"><span class="stock-symbol"><strong>${stock.symbol}</strong><small>${stock.name} · ${stock.sector}</small></span><button class="stock-watch ${watchlist.includes(stock.symbol) ? 'is-watched' : ''}" type="button" data-watch-stock="${stock.symbol}" aria-label="${watchlist.includes(stock.symbol) ? 'Remove' : 'Add'} ${stock.symbol} ${watchlist.includes(stock.symbol) ? 'from' : 'to'} watchlist">${watchlist.includes(stock.symbol) ? '−' : '+'}</button></div>
          <svg class="stock-spark" viewBox="0 0 180 100" preserveAspectRatio="none" aria-hidden="true"><path d="M ${points.replaceAll(' ', ' L ')}"/></svg>
          <div class="stock-tile-price"><strong>${stock.symbol === 'LLOY' || stock.symbol === 'HSBA' || stock.symbol === 'AZN' || stock.symbol === 'SHEL' ? '£' : '$'}${formatNumber(stock.price)}</strong><span class="${stock.move >= 0 ? 'positive' : 'negative'}">${stock.move >= 0 ? '+' : '−'}${formatNumber(Math.abs(stock.move))}%</span></div>
          <div class="stock-meta"><small>${mode} score ${stock[mode]}</small><button class="stock-open" type="button" data-open-stock="${stock.symbol}">Open detail</button></div>
        </article>`;
      }).join('') : '<div class="market-empty"><p>No stock matches that search.</p></div>';
    };

    wall.addEventListener('click', event => {
      const watchButton = event.target.closest('[data-watch-stock]');
      if (watchButton) {
        toggleWatch(watchButton.dataset.watchStock);
        return;
      }
      const openButton = event.target.closest('[data-open-stock]');
      if (openButton) openStockDrawer(openButton.dataset.openStock);
    });
    search.addEventListener('input', render);
    document.querySelectorAll('[data-market-mode]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('[data-market-mode]').forEach(item => item.classList.remove('is-selected'));
      button.classList.add('is-selected');
      mode = button.dataset.marketMode;
      render();
    }));
    document.querySelectorAll('[data-action="close-stock"]').forEach(button => button.addEventListener('click', closeStockDrawer));
    document.getElementById('drawerWatchButton')?.addEventListener('click', event => {
      toggleWatch(event.currentTarget.dataset.symbol);
    });
    document.addEventListener('watchlist:change', () => { render(); renderSummary(); updateDrawerWatchButton(); });
    document.addEventListener('demo:refresh', render);
    window.addEventListener('resize', () => { if (activeStock) drawStockDetail(activeStock); });

    const queryFilter = new URLSearchParams(window.location.search).get('filter');
    if (queryFilter) search.value = queryFilter;
    render();
    renderSummary();
  }

  function openStockDrawer(symbol) {
    const stock = STOCKS.find(item => item.symbol === symbol);
    const drawer = document.getElementById('stockDrawer');
    if (!stock || !drawer) return;
    activeStock = stock;
    document.getElementById('stockDrawerSector').textContent = stock.sector;
    document.getElementById('stockDrawerTitle').textContent = stock.symbol;
    document.getElementById('stockDrawerName').textContent = stock.name;
    document.getElementById('stockDrawerPrice').textContent = `${['HSBA','AZN','SHEL','LLOY'].includes(stock.symbol) ? '£' : '$'}${formatNumber(stock.price)}`;
    const move = document.getElementById('stockDrawerMove');
    move.textContent = `${stock.move >= 0 ? '+' : '−'}${formatNumber(Math.abs(stock.move))}%`;
    move.className = stock.move >= 0 ? 'positive' : 'negative';
    document.getElementById('stockDrawerSignal').textContent = stock.signal;
    document.getElementById('stockDrawerRange').textContent = stock.range;
    document.getElementById('stockDrawerVolume').textContent = stock.volume;
    document.getElementById('stockDrawerNote').textContent = stock.note;
    updateDrawerWatchButton();
    drawer.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    setBodyLock(true);
    window.setTimeout(() => drawStockDetail(stock), 80);
  }

  function updateDrawerWatchButton() {
    const button = document.getElementById('drawerWatchButton');
    if (!button || !activeStock) return;
    const watched = getWatchlist().includes(activeStock.symbol);
    button.dataset.symbol = activeStock.symbol;
    button.textContent = watched ? 'Remove from watchlist' : 'Add to watchlist';
  }

  function drawStockDetail(stock) {
    const canvas = document.getElementById('stockDetailChart');
    if (!canvas) return;
    if (!stockChart) stockChart = new RateChart(canvas, { height: 260 });
    const values = randomSeries(60, stock.price * .96, stock.price * .007, stock.move >= 0 ? stock.price * .00035 : -stock.price * .00028);
    values[values.length - 1] = stock.price;
    const cursor = new Date();
    const dates = [];
    cursor.setDate(cursor.getDate() - 1);
    while (dates.length < values.length) {
      if (cursor.getDay() !== 0 && cursor.getDay() !== 6) dates.push(isoDate(cursor));
      cursor.setDate(cursor.getDate() - 1);
    }
    dates.reverse();
    const unit = ['HSBA', 'AZN', 'SHEL', 'LLOY'].includes(stock.symbol) ? 'GBP' : 'USD';
    stockChart.setData({
      history: values.map((value, index) => ({ date: dates[index], rate: Number(value.toFixed(4)) })),
      forecast: [],
      unit: `${unit} per share (sample)`
    });
  }


  function closeStockDrawer() {
    const drawer = document.getElementById('stockDrawer');
    if (!drawer?.classList.contains('is-open')) return;
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    setBodyLock(false);
  }

  let portfolioSortDescending = true;

  function initPortfolio() {
    const body = document.getElementById('holdingsBody');
    if (!body) return;
    const form = document.getElementById('holdingForm');
    const modal = document.getElementById('holdingModal');

    const openModal = () => {
      modal.hidden = false;
      setBodyLock(true);
      window.setTimeout(() => form.elements.symbol.focus(), 20);
    };

    document.querySelectorAll('[data-action="add-holding"]').forEach(button => button.addEventListener('click', openModal));
    document.querySelectorAll('[data-action="close-holding-modal"]').forEach(button => button.addEventListener('click', closeHoldingModal));
    form.addEventListener('submit', event => {
      event.preventDefault();
      const data = new FormData(form);
      const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO);
      const symbol = String(data.get('symbol')).trim().toUpperCase();
      const existing = holdings.find(item => item.symbol === symbol);
      if (existing) {
        existing.units += Number(data.get('units'));
        existing.price = Number(data.get('price'));
      } else {
        holdings.push({ symbol, name: String(data.get('name')).trim(), units: Number(data.get('units')), price: Number(data.get('price')), day: Number((Math.random() * 3 - 1).toFixed(2)), category: String(data.get('category')) });
      }
      writeStore(STORAGE.portfolio, holdings);
      closeHoldingModal();
      form.reset();
      form.elements.units.value = '10';
      form.elements.price.value = '100';
      renderPortfolio();
      toast(`${symbol} added`, 'The sample portfolio has been recalculated.');
    });
    body.addEventListener('click', event => {
      const button = event.target.closest('[data-remove-holding]');
      if (!button) return;
      const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO).filter(item => item.symbol !== button.dataset.removeHolding);
      writeStore(STORAGE.portfolio, holdings);
      renderPortfolio();
      toast(`${button.dataset.removeHolding} removed`, 'The position has left the local portfolio.');
    });
    document.querySelector('[data-action="sort-holdings"]')?.addEventListener('click', event => {
      portfolioSortDescending = !portfolioSortDescending;
      event.currentTarget.textContent = portfolioSortDescending ? 'Sort by value' : 'Sort by symbol';
      renderPortfolio();
    });
    document.querySelectorAll('[data-action="rebalance"]').forEach(button => button.addEventListener('click', createRebalanceProposal));
    document.querySelector('[data-action="export-portfolio"]')?.addEventListener('click', exportPortfolio);
    document.addEventListener('demo:refresh', () => {
      const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO).map(item => ({ ...item, day: Number((item.day + (Math.random() - .5) * .45).toFixed(2)) }));
      writeStore(STORAGE.portfolio, holdings);
      renderPortfolio();
    });
    window.addEventListener('resize', renderAllocation);
    renderPortfolio();
  }

  function closeHoldingModal() {
    const modal = document.getElementById('holdingModal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    setBodyLock(false);
  }

  function renderPortfolio() {
    const body = document.getElementById('holdingsBody');
    if (!body) return;
    const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO);
    const total = holdings.reduce((sum, item) => sum + item.units * item.price, 0);
    const sorted = [...holdings].sort((a, b) => portfolioSortDescending ? (b.units * b.price) - (a.units * a.price) : String(a.symbol).localeCompare(String(b.symbol)));
    document.querySelector('[data-portfolio-total]').textContent = formatNumber(total, 0);
    document.querySelector('[data-allocation-count]').textContent = String(holdings.length);
    document.getElementById('holdingsEmpty').hidden = holdings.length > 0;
    body.innerHTML = sorted.map(item => {
      const value = item.units * item.price;
      const weight = total ? value / total * 100 : 0;
      return `<tr>
        <td><div class="holding-name"><span class="holding-icon" style="--holding-colour:${categoryColour(item.category)}">${escapeHtml(String(item.symbol).slice(0, 2))}</span><span><strong>${escapeHtml(item.symbol)}</strong><small>${escapeHtml(item.name)}</small></span></div></td>
        <td>${formatNumber(item.units, item.units % 1 ? 2 : 0)}</td>
        <td>${formatMoney(item.price)}</td>
        <td><strong>${formatMoney(value)}</strong></td>
        <td class="${item.day >= 0 ? 'positive' : 'negative'}">${item.day >= 0 ? '+' : '−'}${formatNumber(Math.abs(item.day))}%</td>
        <td><div class="weight-bar" title="${formatNumber(weight)} per cent"><i style="--w:${Math.min(100, weight)}%"></i></div></td>
        <td><button class="row-action" type="button" data-remove-holding="${escapeHtml(item.symbol)}" aria-label="Remove ${escapeHtml(item.symbol)}">×</button></td>
      </tr>`;
    }).join('');
    renderAllocation();
  }

  function renderAllocation() {
    const canvas = document.getElementById('allocationChart');
    const legend = document.getElementById('allocationLegend');
    if (!canvas || !legend) return;
    const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO);
    const categoryValues = holdings.reduce((accumulator, item) => {
      accumulator.set(item.category, (accumulator.get(item.category) || 0) + item.units * item.price);
      return accumulator;
    }, new Map());
    const segments = [...categoryValues].map(([category, value]) => ({ label: category, value, colour: categoryColour(category) }));
    const total = segments.reduce((sum, segment) => sum + segment.value, 0) || 1;
    let geometry = drawDoughnut(canvas, segments);
    legend.innerHTML = segments.map(segment => `<span data-slice="${escapeHtml(segment.label)}"><span><i style="--legend-colour:${segment.colour}"></i>${escapeHtml(segment.label)}</span><b>${formatNumber(segment.value / total * 100, 0)}%</b></span>`).join('');

    const centre = document.querySelector('.allocation-centre');
    const centreValue = centre?.querySelector('strong');
    const centreLabel = centre?.querySelector('small');
    const defaultValue = String(holdings.length);
    const defaultLabel = 'positions';

    const highlight = index => {
      geometry = drawDoughnut(canvas, segments, index);
      if (!centreValue || !centreLabel) return;
      if (index === null) {
        centreValue.textContent = defaultValue;
        centreLabel.textContent = defaultLabel;
      } else {
        centreValue.textContent = `${formatNumber(segments[index].value / total * 100, 0)}%`;
        centreLabel.textContent = segments[index].label;
      }
    };

    if (!canvas.dataset.hoverReady) {
      canvas.dataset.hoverReady = 'yes';
      canvas.addEventListener('mousemove', event => {
        if (!geometry) return;
        const rect = canvas.getBoundingClientRect();
        const scale = geometry.width ? geometry.width / rect.width : 1;
        const px = (event.clientX - rect.left) * (canvas.clientWidth ? geometry.centreX * 2 / canvas.clientWidth : 1);
        const py = (event.clientY - rect.top) * (canvas.clientHeight ? geometry.centreY * 2 / canvas.clientHeight : 1);
        const dx = px - geometry.centreX;
        const dy = py - geometry.centreY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < geometry.inner || distance > geometry.radius + 6) {
          highlight(null);
          return;
        }
        let angle = Math.atan2(dy, dx);
        if (angle < -Math.PI / 2) angle += Math.PI * 2;
        const found = geometry.arcs.find(arc => angle >= arc.start && angle <= arc.end);
        highlight(found ? found.index : null);
      });
      canvas.addEventListener('mouseleave', () => highlight(null));
      if (typeof ResizeObserver === 'function') {
        new ResizeObserver(() => { geometry = drawDoughnut(canvas, segments); }).observe(canvas.parentElement || canvas);
      }
    }
  }


  function createRebalanceProposal() {
    const output = document.getElementById('rebalanceProposal');
    if (!output) return;
    const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO);
    const total = holdings.reduce((sum, item) => sum + item.units * item.price, 0);
    const target = holdings.length ? total / holdings.length : 0;
    const proposals = holdings
      .map(item => ({ ...item, difference: target - item.units * item.price }))
      .sort((a, b) => Math.abs(b.difference) - Math.abs(a.difference))
      .slice(0, 4);
    output.hidden = false;
    output.innerHTML = `<ul>${proposals.map(item => `<li>${item.difference >= 0 ? 'Add' : 'Trim'} <strong>${escapeHtml(item.symbol)}</strong> by about ${formatMoney(Math.abs(item.difference))}.</li>`).join('')}</ul>`;
    output.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    toast('Rebalance draft created', 'Four sample trades now appear in the studio.');
  }

  function exportPortfolio() {
    const holdings = readStore(STORAGE.portfolio, DEFAULT_PORTFOLIO);
    const rows = [['Ticker', 'Company', 'Units', 'Price GBP', 'Value GBP', 'Day %', 'Category'], ...holdings.map(item => [item.symbol, item.name, item.units, item.price, item.units * item.price, item.day, item.category])];
    // Spreadsheets evaluate a text cell that starts with =, +, -, @, tab or
    // carriage return as a formula (HYPERLINK can send cell contents to
    // another site). Such text gets a leading apostrophe, which spreadsheets
    // treat as "show as text"; numbers are written unchanged.
    const csvCell = value => {
      let text = String(value);
      if (typeof value !== 'number' && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    };
    const csv = rows.map(row => row.map(csvCell).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'deltaconvert-portfolio.csv';
    anchor.click();
    URL.revokeObjectURL(url);
    toast('CSV exported', 'Your browser has created the portfolio file.');
  }

  function initAlerts() {
    const savedRules = document.getElementById('savedRules');
    if (!savedRules) return;
    const asset = document.getElementById('alertAsset');
    const condition = document.getElementById('alertCondition');
    const threshold = document.getElementById('alertThreshold');
    const unit = document.getElementById('alertUnit');
    let channel = 'In-app';

    const params = new URLSearchParams(window.location.search);
    const setFromQuery = (control, key) => {
      const value = params.get(key);
      if (value === null) return;
      if (control.tagName === 'SELECT') {
        const match = [...control.options].some(option => option.value === value);
        if (match) control.value = value;
        syncCustomSelect(control);
      } else {
        control.value = value;
      }
    };
    setFromQuery(asset, 'asset');
    setFromQuery(condition, 'condition');
    setFromQuery(threshold, 'threshold');
    setFromQuery(unit, 'unit');

    const updatePreview = () => {
      const unitText = unit.value === '%' ? ' per cent' : unit.value && unit.value !== 'rate' ? ` ${unit.value}` : '';
      document.getElementById('rulePreview').textContent = `Tell me when ${asset.value} ${condition.value} ${threshold.value}${unitText}.`;
    };
    [asset, condition, threshold, unit].forEach(control => control.addEventListener('input', updatePreview));
    document.querySelectorAll('[data-channel]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('[data-channel]').forEach(item => item.classList.remove('is-selected'));
      button.classList.add('is-selected');
      channel = button.dataset.channel;
    }));
    document.querySelector('[data-action="save-alert"]')?.addEventListener('click', () => {
      const alerts = readStore(STORAGE.alerts, DEFAULT_ALERTS);
      alerts.unshift({ id: cryptoId(), asset: asset.value, condition: condition.value, threshold: threshold.value, unit: unit.value || 'rate', channel, active: true });
      writeStore(STORAGE.alerts, alerts);
      renderAlerts();
      toast('Rule saved', document.getElementById('rulePreview').textContent);
    });
    savedRules.addEventListener('click', event => {
      const toggle = event.target.closest('[data-toggle-alert]');
      const remove = event.target.closest('[data-delete-alert]');
      if (toggle) {
        const alerts = readStore(STORAGE.alerts, DEFAULT_ALERTS);
        const alert = alerts.find(item => String(item.id) === toggle.dataset.toggleAlert);
        if (alert) alert.active = !alert.active;
        writeStore(STORAGE.alerts, alerts);
        renderAlerts();
      }
      if (remove) {
        const alerts = readStore(STORAGE.alerts, DEFAULT_ALERTS).filter(item => String(item.id) !== remove.dataset.deleteAlert);
        writeStore(STORAGE.alerts, alerts);
        renderAlerts();
        toast('Rule removed', 'The local alert list has been updated.');
      }
    });
    document.querySelector('[data-action="clear-alerts"]')?.addEventListener('click', () => {
      writeStore(STORAGE.alerts, []);
      renderAlerts();
      toast('All rules cleared', 'The Alert Studio is ready for a new set.');
    });
    document.querySelector('[data-action="save-digest"]')?.addEventListener('click', () => {
      const digest = { time: document.getElementById('digestTime').value, frequency: document.getElementById('digestFrequency').value };
      writeStore(STORAGE.digest, digest);
      toast('Digest schedule saved', `${digest.frequency} at ${digest.time}.`);
    });
    document.querySelector('[data-action="test-digest"]')?.addEventListener('click', () => {
      toast('Demo digest ready', 'GBP is firmer, technology leads and two rules sit close to their thresholds.');
    });

    const digest = readStore(STORAGE.digest, { time: '07:30', frequency: 'Every weekday' });
    document.getElementById('digestTime').value = digest.time;
    document.getElementById('digestFrequency').value = digest.frequency;
    syncCustomSelect(document.getElementById('digestFrequency'));
    updatePreview();
    renderAlerts();
  }

  function renderAlerts() {
    const container = document.getElementById('savedRules');
    if (!container) return;
    const alerts = readStore(STORAGE.alerts, DEFAULT_ALERTS);
    const active = alerts.filter(alert => alert.active).length;
    document.querySelectorAll('[data-alert-count]').forEach(node => { node.textContent = `${alerts.length} ${alerts.length === 1 ? 'rule' : 'rules'}`; });
    const coverage = document.querySelector('.coverage-map strong');
    const coverageSmall = document.querySelector('.coverage-map small');
    if (coverage) coverage.textContent = String(active);
    if (coverageSmall) coverageSmall.textContent = active === 1 ? 'active' : 'active';
    container.innerHTML = alerts.length ? alerts.map(alert => {
      const unitText = alert.unit === '%' ? '%' : alert.unit && !['rate', 'level'].includes(alert.unit) ? ` ${alert.unit}` : '';
      return `<div class="saved-rule">
        <button class="rule-toggle ${alert.active ? 'is-active' : ''}" type="button" data-toggle-alert="${escapeHtml(alert.id)}" aria-label="${alert.active ? 'Pause' : 'Start'} alert"></button>
        <span class="rule-copy"><strong>${escapeHtml(alert.asset)} ${escapeHtml(alert.condition)} ${escapeHtml(alert.threshold)}${escapeHtml(unitText)}</strong><small>${alert.active ? 'Active' : 'Paused'}</small></span>
        <span class="rule-channel">${escapeHtml(alert.channel)}</span>
        <button class="rule-delete" type="button" data-delete-alert="${escapeHtml(alert.id)}" aria-label="Delete alert">×</button>
      </div>`;
    }).join('') : '<div class="rules-empty">No rules yet. Use the studio above to create one.</div>';
  }


  function initLandingPage() {
    document.querySelectorAll('.fade-section').forEach(section => section.classList.add('is-visible'));
    if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const sections = document.querySelectorAll('.fade-section');
      sections.forEach(section => section.classList.remove('is-visible'));
      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -40px' });
      sections.forEach(section => observer.observe(section));
    }

    const asset = document.getElementById('homeAlertAsset');
    const condition = document.getElementById('homeAlertCondition');
    const threshold = document.getElementById('homeAlertThreshold');
    const unit = document.getElementById('homeAlertUnit');
    const preview = document.getElementById('homeAlertPreview');
    const link = document.getElementById('homeAlertStart');
    if (!asset || !condition || !threshold || !unit || !preview || !link) return;

    const update = () => {
      const unitText = unit.value === '%' ? ' per cent' : unit.value ? ` ${unit.value}` : '';
      preview.textContent = `Tell me when ${asset.value} ${condition.value.toLowerCase()} ${threshold.value}${unitText}.`;
      const params = new URLSearchParams({ asset: asset.value, condition: condition.value.toLowerCase(), threshold: threshold.value, unit: unit.value });
      link.href = `alerts.html?${params.toString()}`;
    };
    [asset, condition, threshold, unit].forEach(control => control.addEventListener('input', update));
    update();
  }

  function isoDate(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  /* Sample history and forecast used only when the backend is not
     connected, so the page layout can be checked without running the
     model. Every caller labels the result as a preview on screen. */
  function buildPreviewForecast(days, base = 1.1881) {
    const values = randomSeries(45, base * .995, base * .004, base * .00008);
    const back = [];
    const cursor = new Date();
    cursor.setDate(cursor.getDate() - 1);
    while (back.length < values.length) {
      if (cursor.getDay() !== 0 && cursor.getDay() !== 6) back.push(new Date(cursor));
      cursor.setDate(cursor.getDate() - 1);
    }
    back.reverse();
    const history = back.map((date, index) => ({ date: isoDate(date), rate: Number(values[index].toFixed(4)), type: 'history' }));

    const last = history[history.length - 1].rate;
    const sigma = last * .0045;
    const forecast = [];
    const forward = new Date();
    let step = 1;
    while (forecast.length < days) {
      forward.setDate(forward.getDate() + 1);
      if (forward.getDay() === 0 || forward.getDay() === 6) continue;
      const mean = last * (1 + .00015 * step);
      const band = 1.28 * sigma * Math.sqrt(step);
      forecast.push({
        date: isoDate(forward),
        rate: Number(mean.toFixed(4)),
        lower: Number((mean - band).toFixed(4)),
        upper: Number((mean + band).toFixed(4)),
        type: 'forecast'
      });
      step += 1;
    }
    return { history, forecast };
  }

  function initHomeLive() {
    if (document.body.dataset.page !== 'dashboard') return;
    const heroRate = document.getElementById('heroQuoteRate');
    if (!heroRate) return;

    const load = async () => {
      try {
        const latest = await getLatestRates();
        const gbpEur = crossRate(latest.rates, 'GBP', 'EUR');
        const gbpUsd = crossRate(latest.rates, 'GBP', 'USD');
        heroRate.textContent = formatRate(gbpEur);
        const nowNode = document.getElementById('heroQuoteNow');
        if (nowNode) nowNode.textContent = formatRate(gbpEur);
        const routeRate = document.getElementById('homeRouteRate');
        if (routeRate) routeRate.textContent = formatRate(gbpEur);
        const receive = document.getElementById('homeRouteReceive');
        if (receive) receive.textContent = `€${formatNumber((10000 - 16) * gbpEur)}`;
        const signal = document.getElementById('homeSignalGbpUsd');
        if (signal) signal.textContent = formatRate(gbpUsd);
        document.querySelectorAll('[data-last-updated]').forEach(node => { node.textContent = dayLabel(latest.rate_date); });
        const heroPoints = await getHistory('GBP', 'EUR', 7);
        applyMove(document.getElementById('heroQuoteMove'), movePercent(heroPoints));
        const lowNode = document.getElementById('heroQuoteLow');
        if (lowNode) lowNode.textContent = formatRate(Math.min(...heroPoints.map(point => point.rate)));
        const usdPoints = await getHistory('GBP', 'USD', 7);
        applyMove(document.getElementById('homeSignalGbpUsdMove'), movePercent(usdPoints));
      } catch (error) {
        /* The landing keeps its illustrative figures when the API is unreachable. */
      }
    };

    document.addEventListener('demo:refresh', () => {
      clearLiveCaches();
      load();
    });
    load();
  }

  function init() {
    populateCurrencySelects();
    initCustomSelects();
    initGlobal();
    initDashboard();
    initHomeLive();
    initExchange();
    initMarkets();
    initPortfolio();
    initAlerts();
    initLandingPage();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();