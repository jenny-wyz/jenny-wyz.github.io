/* Reading section: filters, views and the detail panel.
   Data comes from the JSON embedded by layouts/reading/list.html.
   No dependencies. State lives in the URL query string so views are linkable. */
(function () {
  'use strict';

  var root = document.getElementById('reading-app');
  var dataEl = document.getElementById('rd-data');
  if (!root || !dataEl) return;

  var books;
  try { books = JSON.parse(dataEl.textContent); } catch (e) { return; }
  if (!Array.isArray(books)) return;

  var PAGE = parseInt(root.getAttribute('data-page-size'), 10) || 48;
  var STATUSES = ['Reading', 'Paused', 'To Read', 'Completed'];
  var LANGS = { en: 'English', zh: 'Chinese' };
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

  /* ---------- helpers ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fold(s) {
    s = String(s || '').toLowerCase();
    try { s = s.normalize('NFD').replace(/[̀-ͯ]/g, ''); } catch (e) { /* old browsers */ }
    return s.replace(/[‘’]/g, "'");
  }
  function slug(s) { return fold(s).replace(/[^a-z0-9一-鿿]+/g, '-').replace(/^-|-$/g, ''); }
  function stars(n, big) {
    if (!n) return '';
    var s = '';
    for (var i = 0; i < 5; i++) s += i < n ? '★' : '☆';
    return '<span class="rd-stars' + (big ? ' rd-stars-lg' : '') + '" aria-label="' + n + ' of 5 stars">' + s + '</span>';
  }
  function monthYear(iso) {
    if (!iso) return '';
    var y = iso.slice(0, 4), m = parseInt(iso.slice(5, 7), 10);
    return (m ? MONTHS[m - 1] + ' ' : '') + y;
  }
  function statusClass(s) { return 'rd-s-' + slug(s); }
  function statusTag(s) {
    return '<span class="rd-status ' + statusClass(s) + '"><span class="rd-dot"></span>' + esc(s) + '</span>';
  }
  function cover(b, size) {
    var inner;
    if (b.cover) {
      inner = '<img src="' + esc(b.cover) + '" alt="" loading="lazy" decoding="async">';
    } else {
      inner = '<span class="rd-spine' + (b.lang === 'zh' ? ' rd-spine-zh' : '') + (b.collection ? ' rd-spine-collection' : '') + '">' +
        '<span class="rd-spine-title">' + esc(b.title) + '</span>' +
        (b.author ? '<span class="rd-spine-author">' + esc(b.author) + '</span>' : '') + '</span>';
    }
    return '<span class="rd-cover rd-cover-' + size + '" style="--hue:' + (b.hue | 0) + ';--tone:' + (b.tone | 0) + '">' + inner + '</span>';
  }
  function firstAuthor(a) { return (a || '').split(',')[0].trim(); }
  function count(list, fn) { var m = {}; list.forEach(function (b) { var ks = fn(b); if (!Array.isArray(ks)) ks = [ks]; ks.forEach(function (k) { if (k) m[k] = (m[k] || 0) + 1; }); }); return m; }
  function sortedEntries(m) { return Object.keys(m).map(function (k) { return [k, m[k]]; }).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0]); }); }

  /* very small Markdown subset for notes: paragraphs, headings, bullets, quotes */
  function md(text) {
    var out = [], list = null;
    function flush() { if (list) { out.push('<ul>' + list.join('') + '</ul>'); list = null; } }
    String(text || '').split(/\n{2,}|\n(?=[-#>])/).forEach(function (block) {
      var line = block.trim();
      if (!line) return;
      var m;
      if ((m = line.match(/^(#{1,3})\s+(.*)$/))) { flush(); out.push('<h3>' + esc(m[2]) + '</h3>'); }
      else if (/^(-|\d+\.)\s+/.test(line)) {
        line.split('\n').forEach(function (l) { l = l.replace(/^\s*(-|\d+\.)\s+/, '').trim(); if (l) { list = list || []; list.push('<li>' + esc(l) + '</li>'); } });
      }
      else if (line.charAt(0) === '>') { flush(); out.push('<blockquote>' + esc(line.replace(/^>\s?/gm, '')) + '</blockquote>'); }
      else { flush(); out.push('<p>' + esc(line).replace(/\n/g, '<br>') + '</p>'); }
    });
    flush();
    return out.join('');
  }

  /* ---------- state in the URL ---------- */
  var state = { view: 'shelf', q: '', status: '', cat: [], rating: '', lang: '', sort: 'added', dir: '', book: '' };
  function readState() {
    var p = new URLSearchParams(location.search);
    state.view = p.get('view') || 'shelf';
    state.q = p.get('q') || '';
    state.status = p.get('status') || '';
    state.cat = (p.get('cat') || '').split(',').filter(Boolean);
    state.rating = p.get('rating') || '';
    state.lang = p.get('lang') || '';
    state.sort = p.get('sort') || 'added';
    state.dir = p.get('dir') || '';
    state.book = p.get('book') || '';
  }
  function writeState() {
    var p = new URLSearchParams();
    if (state.view !== 'shelf') p.set('view', state.view);
    if (state.q) p.set('q', state.q);
    if (state.status) p.set('status', state.status);
    if (state.cat.length) p.set('cat', state.cat.join(','));
    if (state.rating) p.set('rating', state.rating);
    if (state.lang) p.set('lang', state.lang);
    if (state.sort !== 'added') p.set('sort', state.sort);
    if (state.dir) p.set('dir', state.dir);
    if (state.book) p.set('book', state.book);
    var qs = p.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
  }

  /* ---------- filtering and sorting ---------- */
  var index = books.map(function (b) {
    return fold([b.title, b.author].concat(b.categories || []).join(' '));
  });
  function filtered() {
    var q = fold(state.q).trim();
    var min = state.rating ? parseInt(state.rating, 10) : 0;
    return books.filter(function (b, i) {
      if (state.status && b.status !== state.status) return false;
      if (state.lang && b.lang !== state.lang) return false;
      if (state.cat.length && !state.cat.some(function (c) { return (b.categories || []).indexOf(c) >= 0; })) return false;
      if (min && !(b.rating >= min)) return false;
      if (q && index[i].indexOf(q) < 0) return false;
      return true;
    });
  }
  var SORTS = {
    added: { dir: 'desc', key: function (b) { return b.added || ''; } },
    completed: { dir: 'desc', key: function (b) { return b.completed || ''; }, emptyLast: true },
    title: { dir: 'asc', key: function (b) { return fold(b.title); } },
    author: { dir: 'asc', key: function (b) { return fold(b.author) || '￿'; } },
    rating: { dir: 'desc', key: function (b) { return b.rating || 0; }, emptyLast: true }
  };
  function sorted(list) {
    var def = SORTS[state.sort] || SORTS.added;
    var dir = state.dir || def.dir;
    var sign = dir === 'desc' ? -1 : 1;
    return list.slice().sort(function (a, b) {
      var ka = def.key(a), kb = def.key(b);
      if (def.emptyLast) {
        var ea = !ka, eb = !kb;
        if (ea !== eb) return ea ? 1 : -1;
      }
      if (ka < kb) return -1 * sign;
      if (ka > kb) return 1 * sign;
      return fold(a.title) < fold(b.title) ? -1 : 1;
    });
  }

  /* ---------- DOM refs ---------- */
  var toolbar = root.querySelector('.rd-toolbar');
  var filtersEl = document.getElementById('rd-filters');
  var summaryEl = document.getElementById('rd-summary');
  var viewEl = document.getElementById('rd-view');
  var qEl = document.getElementById('rd-q');
  var sortEl = document.getElementById('rd-sort');
  var panel = document.getElementById('rd-panel');
  var panelBody = document.getElementById('rd-panel-body');
  var backdrop = document.getElementById('rd-backdrop');
  var closeBtn = document.getElementById('rd-close');
  var shown = PAGE;
  var currentList = [];

  /* ---------- filters ---------- */
  function chip(label, pressed, attrs, n) {
    return '<button type="button" class="rd-chip" aria-pressed="' + (pressed ? 'true' : 'false') + '" ' + attrs + '>' + esc(label) +
      (n != null ? ' <small>' + n + '</small>' : '') + '</button>';
  }
  function renderFilters() {
    var byStatus = count(books, function (b) { return b.status; });
    var byCat = count(books, function (b) { return b.categories || []; });
    var byLang = count(books, function (b) { return b.lang; });
    var html = '';
    html += '<div class="rd-filter-row"><span class="rd-filter-label">Status</span>' + chip('All', !state.status, 'data-f="status" data-v=""') +
      STATUSES.filter(function (s) { return byStatus[s]; }).map(function (s) { return chip(s, state.status === s, 'data-f="status" data-v="' + esc(s) + '"', byStatus[s]); }).join('') + '</div>';
    html += '<div class="rd-filter-row"><span class="rd-filter-label">Category</span>' +
      sortedEntries(byCat).map(function (e) { return chip(e[0], state.cat.indexOf(e[0]) >= 0, 'data-f="cat" data-v="' + esc(e[0]) + '"', e[1]); }).join('') + '</div>';
    html += '<div class="rd-filter-row"><span class="rd-filter-label">More</span>' +
      chip('5 stars', state.rating === '5', 'data-f="rating" data-v="5"') + chip('4 stars and up', state.rating === '4', 'data-f="rating" data-v="4"') +
      Object.keys(LANGS).filter(function (l) { return byLang[l]; }).map(function (l) { return chip(LANGS[l], state.lang === l, 'data-f="lang" data-v="' + l + '"', byLang[l]); }).join('') +
      (hasFilters() ? '<button type="button" class="rd-chip rd-chip-clear" data-f="clear">Clear all</button>' : '') + '</div>';
    filtersEl.innerHTML = html;
  }
  function hasFilters() { return !!(state.q || state.status || state.cat.length || state.rating || state.lang); }
  filtersEl.addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-f]');
    if (!btn) return;
    var f = btn.getAttribute('data-f'), v = btn.getAttribute('data-v');
    if (f === 'clear') { state.q = ''; state.status = ''; state.cat = []; state.rating = ''; state.lang = ''; qEl.value = ''; }
    else if (f === 'cat') { var i = state.cat.indexOf(v); if (i >= 0) state.cat.splice(i, 1); else state.cat.push(v); }
    else if (state[f] === v) state[f] = '';
    else state[f] = v;
    shown = PAGE;
    update();
  });

  /* ---------- views ---------- */
  function renderSummary(list) {
    var total = books.length;
    var txt = list.length === total ? '<b>' + total + '</b> books' : '<b>' + list.length + '</b> of ' + total + ' books';
    if (state.view === 'stats') txt += ' in these statistics';
    summaryEl.innerHTML = '<span>' + txt + '</span>' + (hasFilters() ? '<span>filtered</span>' : '');
  }

  function renderShelf(list) {
    if (!list.length) return '<div class="rd-empty">No books match. Try clearing a filter.</div>';
    var html = '<div class="rd-grid">';
    list.slice(0, shown).forEach(function (b) {
      html += '<button type="button" class="rd-card" data-book="' + esc(b.id) + '">' + cover(b, 'md') +
        '<span class="rd-title">' + esc(b.title) + '</span>' +
        (b.author ? '<span class="rd-author">' + esc(b.author) + '</span>' : '') +
        '<span class="rd-card-meta">' + (b.rating ? stars(b.rating) : (b.status !== 'Completed' ? statusTag(b.status) : '')) + '</span>' +
        '</button>';
    });
    html += '</div>';
    if (list.length > shown) html += '<button type="button" class="rd-more" data-more>Show ' + Math.min(PAGE, list.length - shown) + ' more</button>';
    return html;
  }

  function renderList(list) {
    if (!list.length) return '<div class="rd-empty">No books match. Try clearing a filter.</div>';
    function th(label, key, cls) {
      var sortAttr = state.sort === key ? ' aria-sort="' + ((state.dir || SORTS[key].dir) === 'asc' ? 'ascending' : 'descending') + '"' : '';
      return '<th data-sort="' + key + '"' + sortAttr + (cls ? ' class="' + cls + '"' : '') + '>' + label + '</th>';
    }
    var html = '<table class="rd-table"><thead><tr>' + th('Title', 'title') + th('Author', 'author', 'rd-hide-sm') +
      '<th class="rd-hide-sm">Category</th><th>Status</th>' + th('Rating', 'rating') + th('Finished', 'completed', 'rd-hide-sm') + '</tr></thead><tbody>';
    list.slice(0, shown).forEach(function (b) {
      html += '<tr class="rd-row" data-book="' + esc(b.id) + '" tabindex="0">' +
        '<td><span class="rd-cell-title">' + cover(b, 'sm') + '<span><span class="rd-t">' + esc(b.title) + '</span>' +
        (b.author ? '<span class="rd-a rd-hide-sm-inline"><br>' + esc(b.author) + '</span>' : '') + '</span></span></td>' +
        '<td class="rd-hide-sm"><span class="rd-a">' + esc(b.author) + '</span></td>' +
        '<td class="rd-hide-sm"><span class="rd-cats">' + (b.categories || []).map(function (c) { return '<span class="rd-cat">' + esc(c) + '</span>'; }).join('') + '</span></td>' +
        '<td>' + statusTag(b.status) + '</td>' +
        '<td>' + (b.rating ? stars(b.rating) : '<span class="rd-muted">—</span>') + '</td>' +
        '<td class="rd-num rd-hide-sm">' + (b.completed ? monthYear(b.completed) : '<span class="rd-muted">—</span>') + '</td></tr>';
    });
    html += '</tbody></table>';
    if (list.length > shown) html += '<button type="button" class="rd-more" data-more>Show ' + Math.min(PAGE, list.length - shown) + ' more</button>';
    return html;
  }

  function renderTimeline(list) {
    var done = list.filter(function (b) { return b.status === 'Completed'; });
    if (!done.length) return '<div class="rd-empty">No finished books in this selection.</div>';
    var dated = done.filter(function (b) { return b.completed; }).sort(function (a, b) { return a.completed < b.completed ? 1 : -1; });
    var undated = done.filter(function (b) { return !b.completed; }).sort(function (a, b) { return fold(a.title) < fold(b.title) ? -1 : 1; });
    var html = '<div class="rd-timeline">';
    var years = {};
    dated.forEach(function (b) { var y = b.completed.slice(0, 4), m = b.completed.slice(5, 7); years[y] = years[y] || {}; (years[y][m] = years[y][m] || []).push(b); });
    Object.keys(years).sort().reverse().forEach(function (y) {
      var n = 0; Object.keys(years[y]).forEach(function (m) { n += years[y][m].length; });
      html += '<section class="rd-year"><h2 class="rd-year-h">' + y + '<small>' + n + (n === 1 ? ' book' : ' books') + '</small></h2>';
      Object.keys(years[y]).sort().reverse().forEach(function (m) {
        html += '<div class="rd-month"><h3 class="rd-month-h">' + MONTHS[parseInt(m, 10) - 1] + '</h3>' + years[y][m].map(tlItem).join('') + '</div>';
      });
      html += '</section>';
    });
    if (undated.length) {
      html += '<section class="rd-year rd-tl-undated"><h2 class="rd-year-h">Earlier<small>' + undated.length + ' books, date not recorded</small></h2><div class="rd-tl-items">' + undated.map(tlItem).join('') + '</div></section>';
    }
    return html + '</div>';
  }
  function tlItem(b) {
    return '<button type="button" class="rd-tl-item" data-book="' + esc(b.id) + '">' + cover(b, 'sm') +
      '<span class="rd-tl-text"><span class="rd-title">' + esc(b.title) + '</span>' + (b.author ? '<span class="rd-author">' + esc(b.author) + '</span>' : '') + '</span>' +
      (b.rating ? stars(b.rating) : '') + '</button>';
  }

  function renderStats(list) {
    if (!list.length) return '<div class="rd-empty">Nothing to count. Try clearing a filter.</div>';
    var n = list.length;
    var byStatus = count(list, function (b) { return b.status; });
    var byCat = sortedEntries(count(list, function (b) { return b.categories || []; }));
    var byAuthor = sortedEntries(count(list, function (b) { return firstAuthor(b.author); })).filter(function (e) { return e[1] > 1; }).slice(0, 8);
    var byLang = count(list, function (b) { return b.lang; });
    var byYear = count(list.filter(function (b) { return b.status === 'Completed' && b.completed; }), function (b) { return b.completed.slice(0, 4); });
    var rated = list.filter(function (b) { return b.rating; });
    var byRating = count(rated, function (b) { return String(b.rating); });
    var max = function (entries) { return entries.reduce(function (m, e) { return Math.max(m, e[1]); }, 0) || 1; };
    function bars(entries, f, v, soft) {
      var mx = max(entries);
      return '<div class="rd-bars">' + entries.map(function (e) {
        return '<button type="button" class="rd-bar" data-f="' + f + '" data-v="' + esc(v ? v(e[0]) : e[0]) + '" title="Filter by ' + esc(e[0]) + '"><span class="rd-bar-l">' + esc(e[0]) + '</span>' +
          '<span class="rd-bar-track"><span class="rd-bar-fill' + (soft ? ' rd-soft' : '') + '" style="width:' + Math.round(e[1] / mx * 100) + '%"></span></span><span class="rd-bar-n">' + e[1] + '</span></button>';
      }).join('') + '</div>';
    }
    var html = '<div class="rd-stats-grid">';
    // status
    html += '<div class="rd-panel-card"><h3>Status</h3><div class="rd-stack">' + STATUSES.map(function (s) {
      return byStatus[s] ? '<span class="rd-k-' + slug(s) + '" style="width:' + (byStatus[s] / n * 100) + '%" title="' + esc(s) + ': ' + byStatus[s] + '"></span>' : '';
    }).join('') + '</div><div class="rd-legend">' + STATUSES.filter(function (s) { return byStatus[s]; }).map(function (s) {
      return '<span><i class="rd-k-' + slug(s) + '"></i>' + esc(s) + ' <b>' + byStatus[s] + '</b></span>';
    }).join('') + '</div>' +
      '<h3 style="margin-top:1.4rem">Language</h3>' + bars(sortedEntries(byLang).map(function (e) { return [LANGS[e[0]] || e[0], e[1]]; }), 'lang', function (label) { return label === 'Chinese' ? 'zh' : 'en'; }, true) + '</div>';
    // categories
    html += '<div class="rd-panel-card"><h3>Categories</h3>' + bars(byCat, 'cat') + '</div>';
    // ratings
    html += '<div class="rd-panel-card"><h3>Ratings <small style="font-weight:400;text-transform:none;letter-spacing:0">' + rated.length + ' rated</small></h3><div class="rd-bars">' +
      [5, 4, 3, 2, 1].map(function (r) {
        var c = byRating[String(r)] || 0, mx = max(sortedEntries(byRating));
        return '<div class="rd-bar" style="cursor:default">' + stars(r) + '<span class="rd-bar-track"><span class="rd-bar-fill" style="width:' + Math.round(c / mx * 100) + '%"></span></span><span class="rd-bar-n">' + c + '</span></div>';
      }).join('') + '</div>' +
      (rated.length ? '<p class="rd-muted" style="font-size:.8rem;margin:.9rem 0 0">Average ' + (rated.reduce(function (s, b) { return s + b.rating; }, 0) / rated.length).toFixed(1) + ' of 5</p>' : '') + '</div>';
    // authors
    if (byAuthor.length) html += '<div class="rd-panel-card"><h3>Most read authors</h3>' + bars(byAuthor, 'q') + '</div>';
    // years
    var yearEntries = Object.keys(byYear).sort().map(function (y) { return [y, byYear[y]]; });
    if (yearEntries.length) html += '<div class="rd-panel-card"><h3>Finished per year <small style="font-weight:400;text-transform:none;letter-spacing:0">dated books only</small></h3>' + bars(yearEntries, 'none', null, true) + '</div>';
    return html + '</div>';
  }

  function update() {
    currentList = sorted(filtered());
    renderFilters();
    renderSummary(currentList);
    root.querySelectorAll('.rd-views button').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-view') === state.view ? 'true' : 'false'); });
    var r = { shelf: renderShelf, list: renderList, timeline: renderTimeline, stats: renderStats }[state.view] || renderShelf;
    viewEl.innerHTML = r(currentList);
    writeState();
  }

  /* ---------- detail panel ---------- */
  var lastFocus = null;
  function openBook(id, viaNav) {
    var b = null, pos = -1;
    for (var i = 0; i < currentList.length; i++) if (currentList[i].id === id) { b = currentList[i]; pos = i; break; }
    if (!b) for (i = 0; i < books.length; i++) if (books[i].id === id) { b = books[i]; break; }
    if (!b) return;
    if (!viaNav) lastFocus = document.activeElement;
    var html = '<div class="rd-panel-top">' + cover(b, 'lg') + '<div><h2 class="rd-panel-title" id="rd-panel-title">' + esc(b.title) + '</h2>' +
      (b.author ? '<p class="rd-panel-author">' + esc(b.author) + '</p>' : '') + statusTag(b.status) + (b.rating ? '<div style="margin-top:.5rem">' + stars(b.rating, true) + '</div>' : '') + '</div></div>';
    html += '<dl class="rd-meta">';
    if (b.categories && b.categories.length) html += '<dt>Category</dt><dd><span class="rd-cats">' + b.categories.map(function (c) { return '<span class="rd-cat">' + esc(c) + '</span>'; }).join('') + '</span></dd>';
    if (b.started) html += '<dt>Started</dt><dd>' + monthYear(b.started) + '</dd>';
    if (b.completed) html += '<dt>Finished</dt><dd>' + monthYear(b.completed) + '</dd>';
    if (b.added) html += '<dt>Logged</dt><dd>' + monthYear(b.added) + '</dd>';
    html += '<dt>Language</dt><dd>' + (LANGS[b.lang] || b.lang) + (b.collection ? ' · collection' : '') + '</dd></dl>';
    if (b.review) html += '<h3 class="rd-section-h">Review</h3><p class="rd-review">' + esc(b.review) + '</p>';
    if (b.notes && b.notes.length) {
      html += '<h3 class="rd-section-h">Notes</h3>' + b.notes.map(function (nt) {
        return '<div class="rd-notes">' + (nt.created ? '<p class="rd-note-date">' + monthYear(nt.created) + '</p>' : '') + md(nt.text) + '</div>';
      }).join('');
    }
    if (b.body) html += '<h3 class="rd-section-h">From the page</h3><div class="rd-notes">' + md(b.body) + '</div>';
    if (b.page) html += '<a class="rd-link" href="' + esc(b.page) + '">Read the full write-up →</a>';
    if (pos >= 0 && currentList.length > 1) {
      var prev = currentList[(pos - 1 + currentList.length) % currentList.length], next = currentList[(pos + 1) % currentList.length];
      html += '<div class="rd-panel-nav"><button type="button" data-nav="' + esc(prev.id) + '">← ' + esc(prev.title) + '</button><button type="button" data-nav="' + esc(next.id) + '">' + esc(next.title) + ' →</button></div>';
    }
    panelBody.innerHTML = html;
    panel.hidden = false; backdrop.hidden = false;
    requestAnimationFrame(function () { panel.classList.add('rd-open'); backdrop.classList.add('rd-open'); });
    document.body.classList.add('rd-lock');
    panel.scrollTop = 0;
    closeBtn.focus();
    state.book = id; writeState();
  }
  function closePanel() {
    panel.classList.remove('rd-open'); backdrop.classList.remove('rd-open');
    document.body.classList.remove('rd-lock');
    setTimeout(function () { panel.hidden = true; backdrop.hidden = true; }, 250);
    state.book = ''; writeState();
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  closeBtn.addEventListener('click', closePanel);
  backdrop.addEventListener('click', closePanel);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) closePanel(); });
  panelBody.addEventListener('click', function (e) { var b = e.target.closest('[data-nav]'); if (b) openBook(b.getAttribute('data-nav'), true); });

  /* ---------- events ---------- */
  root.addEventListener('click', function (e) {
    var more = e.target.closest('[data-more]');
    if (more) { shown += PAGE; update(); return; }
    var bookBtn = e.target.closest('[data-book]');
    if (bookBtn) { openBook(bookBtn.getAttribute('data-book')); return; }
    var view = e.target.closest('[data-view]');
    if (view) { state.view = view.getAttribute('data-view'); shown = PAGE; update(); return; }
    var th = e.target.closest('th[data-sort]');
    if (th) {
      var k = th.getAttribute('data-sort');
      if (state.sort === k) state.dir = (state.dir || SORTS[k].dir) === 'asc' ? 'desc' : 'asc'; else { state.sort = k; state.dir = ''; }
      sortEl.value = state.sort; update(); return;
    }
    var bar = e.target.closest('.rd-bar[data-f]');
    if (bar) {
      var f = bar.getAttribute('data-f'), v = bar.getAttribute('data-v');
      if (f === 'cat') state.cat = [v]; else if (f === 'q') { state.q = v; qEl.value = v; } else if (f === 'lang') state.lang = v; else return;
      state.view = 'shelf'; shown = PAGE; update(); window.scrollTo({ top: root.offsetTop - 80, behavior: 'smooth' });
    }
  });
  root.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.classList && e.target.classList.contains('rd-row')) openBook(e.target.getAttribute('data-book'));
  });
  var qTimer;
  qEl.addEventListener('input', function () { clearTimeout(qTimer); qTimer = setTimeout(function () { state.q = qEl.value; shown = PAGE; update(); }, 120); });
  sortEl.addEventListener('change', function () { state.sort = sortEl.value; state.dir = ''; update(); });

  /* ---------- init ---------- */
  readState();
  qEl.value = state.q;
  if (SORTS[state.sort]) sortEl.value = state.sort;
  toolbar.hidden = false; filtersEl.hidden = false; summaryEl.hidden = false;
  update();
  if (state.book) openBook(state.book);
})();
