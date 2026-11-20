/*
  Site copy of Blowfish's assets/js/search.js (theme v3.8.0) with three changes:

  1. Chinese (and any other IME) input works: the query runs on the `input`
     and `compositionend` events instead of `keyup`, and keys pressed while a
     character is still being composed are left to the input method.
  2. Protected sections are searchable after unlocking. The deploy writes an
     encrypted index of them (search-private.json, see scripts/protect_pages.py).
     If the password is remembered for this visit (set by the "Knock knock"
     prompt), that index is decrypted in the browser and merged in.
  3. A one-line hint under the results says so when it is not unlocked.

  Re-copy and re-apply if the theme is upgraded.
*/
var fuse;
var showButton = document.getElementById("search-button");
var showButtonMobile = document.getElementById("search-button-mobile");
var hideButton = document.getElementById("close-search-button");
var wrapper = document.getElementById("search-wrapper");
var modal = document.getElementById("search-modal");
var input = document.getElementById("search-query");
var output = document.getElementById("search-results");
var first = output.firstChild;
var last = output.lastChild;
var searchVisible = false;
var indexed = false;
var hasResults = false;
var previouslyFocused = null;

// Listen for events
showButton ? showButton.addEventListener("click", displaySearch) : null;
showButtonMobile ? showButtonMobile.addEventListener("click", displaySearch) : null;
hideButton.addEventListener("click", hideSearch);
wrapper.addEventListener("click", hideSearch);
modal.addEventListener("click", function (event) {
  event.stopPropagation();
  event.stopImmediatePropagation();
  return false;
});
const shortcutHint = document.getElementById("search-shortcut-hint");
if (shortcutHint && !/Mac|iPhone|iPad/.test(navigator.platform)) {
  shortcutHint.textContent = "Ctrl K";
}

document.addEventListener("keydown", function (event) {
  // Keys that belong to an input method (choosing a character with Enter or
  // the arrows) are not ours to handle.
  if (event.isComposing || event.keyCode === 229) return;

  // Forward slash to open search wrapper
  if (event.key == "/") {
    const active = document.activeElement;
    const tag = active.tagName;
    const isInputField = tag === "INPUT" || tag === "TEXTAREA" || active.isContentEditable;

    if (!searchVisible && !isInputField) {
      event.preventDefault();
      displaySearch();
    }
  }

  // Cmd+K (macOS) / Ctrl+K to toggle search wrapper
  if (event.key && event.key.toLowerCase() == "k" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    if (searchVisible) {
      hideSearch();
    } else {
      displaySearch();
    }
  }

  // Esc to close search wrapper
  if (event.key == "Escape") {
    hideSearch();
  }

  // Trap Tab / Shift+Tab focus inside the modal while it is open
  if (event.key == "Tab" && searchVisible) {
    var focusable = modal.querySelectorAll('a[href], button, input, [tabindex="0"]');
    if (focusable.length > 0) {
      var firstFocusable = focusable[0];
      var lastFocusable = focusable[focusable.length - 1];
      if (!modal.contains(document.activeElement)) {
        event.preventDefault();
        firstFocusable.focus();
      } else if (event.shiftKey && document.activeElement == firstFocusable) {
        event.preventDefault();
        lastFocusable.focus();
      } else if (!event.shiftKey && document.activeElement == lastFocusable) {
        event.preventDefault();
        firstFocusable.focus();
      }
    }
  }

  // Down arrow to move down results list
  if (event.key == "ArrowDown") {
    if (searchVisible && hasResults) {
      event.preventDefault();
      if (document.activeElement == input) {
        first.focus();
      } else if (document.activeElement == last) {
        last.focus();
      } else {
        document.activeElement.parentElement.nextSibling.firstElementChild.focus();
      }
    }
  }

  // Up arrow to move up results list
  if (event.key == "ArrowUp") {
    if (searchVisible && hasResults) {
      event.preventDefault();
      if (document.activeElement == input) {
        input.focus();
      } else if (document.activeElement == first) {
        input.focus();
      } else {
        document.activeElement.parentElement.previousSibling.firstElementChild.focus();
      }
    }
  }

  // Enter to get to results
  if (event.key == "Enter") {
    if (searchVisible && hasResults) {
      event.preventDefault();
      if (document.activeElement == input) {
        first.focus();
      } else {
        document.activeElement.click();
      }
    }
  }
});

// Update search as the text changes. With an input method (Chinese, Japanese,
// ...) the text only counts once a character has been committed.
var composing = false;
input.addEventListener("compositionstart", function () { composing = true; });
input.addEventListener("compositionend", function () { composing = false; executeQuery(input.value); });
input.addEventListener("input", function () { if (!composing) executeQuery(input.value); });

function displaySearch() {
  if (!indexed) {
    buildIndex();
  }
  if (!searchVisible) {
    previouslyFocused = document.activeElement;
    document.body.style.overflow = "hidden";
    wrapper.style.visibility = "visible";
    input.focus();
    searchVisible = true;
  }
}

function hideSearch() {
  if (searchVisible) {
    document.body.style.overflow = "visible";
    wrapper.style.visibility = "hidden";
    input.value = "";
    output.innerHTML = "";
    if (previouslyFocused && typeof previouslyFocused.focus === "function" && document.contains(previouslyFocused)) {
      previouslyFocused.focus();
    } else if (document.activeElement) {
      document.activeElement.blur();
    }
    previouslyFocused = null;
    searchVisible = false;
  }
}

function fetchJSON(path, callback) {
  var httpRequest = new XMLHttpRequest();
  httpRequest.onreadystatechange = function () {
    if (httpRequest.readyState === 4) {
      if (httpRequest.status === 200) {
        var data = JSON.parse(httpRequest.responseText);
        if (callback) callback(data);
      }
    }
  };
  httpRequest.open("GET", path);
  httpRequest.send();
}

var PRIVATE_KEY = "jw_pw";          // where the Knock-knock prompt keeps the password for this visit
var privateState = "none";          // none | locked | open

function b64bytes(str) {
  var bin = atob(str), a = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return a;
}

// The encrypted index of the protected sections; resolves to [] when there is
// none, when nothing is unlocked, or when the remembered password is wrong.
function loadPrivateIndex(baseURL) {
  return fetch(baseURL + "search-private.json").then(function (r) {
    if (!r.ok) return [];
    return r.json().then(function (vault) {
      var pw = null;
      try { pw = sessionStorage.getItem(PRIVATE_KEY); } catch (e) {}
      if (!pw || !window.crypto || !crypto.subtle) { privateState = "locked"; return []; }
      var enc = new TextEncoder();
      return crypto.subtle.importKey("raw", enc.encode(pw), "PBKDF2", false, ["deriveKey"]).then(function (base) {
        return crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64bytes(vault.s), iterations: vault.it, hash: "SHA-256" }, base,
          { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
      }).then(function (key) {
        return crypto.subtle.decrypt({ name: "AES-GCM", iv: b64bytes(vault.iv) }, key, b64bytes(vault.ct));
      }).then(function (buf) {
        privateState = "open";
        return JSON.parse(new TextDecoder().decode(buf));
      }).catch(function () { privateState = "locked"; return []; });
    });
  }).catch(function () { return []; });
}

function showPrivateHint() {
  var hint = document.getElementById("search-private-hint");
  if (privateState !== "locked") { if (hint) hint.remove(); return; }
  if (hint) return;
  hint = document.createElement("p");
  hint.id = "search-private-hint";
  hint.className = "px-3 pb-3 text-xs text-neutral-500 dark:text-neutral-400";
  hint.textContent = "Locked sections join the search once you have opened one of them in this visit.";
  output.parentElement.appendChild(hint);
}

function buildIndex() {
  if (buildIndex.started) return;
  buildIndex.started = true;
  var baseURL = wrapper.getAttribute("data-url");
  baseURL = baseURL.replace(/\/?$/, "/");
  fetchJSON(baseURL + "index.json", function (data) {
    var options = {
      shouldSort: true,
      ignoreLocation: true,
      threshold: 0.0,
      includeMatches: true,
      keys: [
        { name: "title", weight: 0.8 },
        { name: "section", weight: 0.2 },
        { name: "summary", weight: 0.6 },
        { name: "content", weight: 0.4 },
      ],
    };
    loadPrivateIndex(baseURL).then(function (extra) {
      fuse = new Fuse(data.concat(extra), options);
      indexed = true;
      showPrivateHint();
      if (input.value) executeQuery(input.value);
    });
  });
}

function executeQuery(term) {
  if (!indexed) {
    buildIndex();
  }
  if (!fuse) {
    return;
  }
  let results = fuse.search(term);
  let resultsHTML = "";

  if (results.length > 0) {
    results.forEach(function (value, key) {
      var html = value.item.summary;
      var div = document.createElement("div");
      div.innerHTML = html;
      value.item.summary = div.textContent || div.innerText || "";
      var title = value.item.externalUrl
        ? value.item.title +
          '<span class="text-xs ml-2 align-center cursor-default text-neutral-400 dark:text-neutral-500">' +
          value.item.externalUrl +
          "</span>"
        : value.item.title;
      var linkconfig = value.item.externalUrl
        ? 'target="_blank" rel="noopener" href="' + value.item.externalUrl + '"'
        : 'href="' + value.item.permalink + '"';
      resultsHTML =
        resultsHTML +
        `<li class="mb-2">
          <a class="flex items-center px-3 py-2 rounded-md appearance-none bg-neutral-100 dark:bg-neutral-700 focus:bg-primary-100 hover:bg-primary-100 dark:hover:bg-primary-900 dark:focus:bg-primary-900 focus:outline-dotted focus:outline-transparent focus:outline-2" 
          ${linkconfig} tabindex="0">
            <div class="grow">
              <div class="-mb-1 text-lg font-bold">
                ${title}
              </div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">${value.item.section}<span class="px-2 text-primary-500">&middot;</span>${value.item.date ? value.item.date : ""}</span></div>
              <div class="text-sm italic">${value.item.summary}</div>
            </div>
            <div class="ml-2 ltr:block rtl:hidden text-neutral-500">&rarr;</div>
            <div class="mr-2 ltr:hidden rtl:block text-neutral-500">&larr;</div>
          </a>
        </li>`;
    });
    hasResults = true;
  } else {
    resultsHTML = "";
    hasResults = false;
  }

  output.innerHTML = resultsHTML;
  if (results.length > 0 && output.firstChild) {
    first = output.firstChild.firstElementChild;
    last = output.lastChild.firstElementChild;
  }
}
