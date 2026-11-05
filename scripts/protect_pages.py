#!/usr/bin/env python3
"""
Lock password-protected pages after the Hugo build.

Any page with `protected: true` in its front matter renders a marker
(<meta name="jw-protected">, from partials/extend-head-uncached.html). This
script finds those pages in the built site, encrypts everything inside
<main>…</main> with AES-256-GCM (key derived from PAGE_PASSWORD with
PBKDF2-SHA256), and replaces it with a prompt. The browser decrypts in
place once the right password is typed. Without the password the content
on the deployed site is unreadable; the header, nav and footer stay as they
are, so a locked page still looks like the rest of the site.

It also blanks the description meta tags of those pages, so the summary
does not leak through link previews, and it folds the page's own images
(files next to the page, e.g. notebook photos) into the encrypted payload
as data: URIs and deletes the loose files, so they cannot be fetched by URL.

Visitor-side rules (in the embedded script):
  * 3 wrong tries lock protected pages for 24 hours in that browser and send
    the visitor to the decoy page. This lives in localStorage, so it deters
    rather than prevents; the encryption is the real protection.
  * A correct password is kept for the browser session, so other protected
    pages open without retyping.

Usage:
    PAGE_PASSWORD=... python3 scripts/protect_pages.py public [--decoy /shabi/]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:  # pragma: no cover
    print("error: pip install cryptography", file=sys.stderr)
    sys.exit(2)

MARKER_RE = re.compile(r'<meta\s+name=["\']?jw-protected["\']?\s+content=["\']?1["\']?\s*/?>', re.I)
ITERATIONS = 250_000
MAIN_RE = re.compile(r"(<main\b[^>]*>)(.*?)(</main>)", re.S)
DESC_RE = re.compile(
    r'<meta\s+(?:name|property)=["\']?(?:description|og:description|twitter:description)["\']?\s+content=["\']?[^>]*?>',
    re.I,
)
DESC_RE2 = re.compile(
    r'<meta\s+content=["\']?[^>]*?["\']?\s+(?:name|property)=["\']?(?:description|og:description|twitter:description)["\']?[^>]*>',
    re.I,
)
LDJSON_RE = re.compile(r'<script type=["\']?application/ld\+json["\']?>.*?</script>', re.S | re.I)


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def encrypt(password: str, plaintext: str) -> dict:
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    key = derive_key(password, salt)
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"v": 1, "it": ITERATIONS, "s": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def decrypt(password: str, vault: dict) -> str:
    """Used by the tests to prove the round trip."""
    salt, iv, ct = (base64.b64decode(vault[k]) for k in ("s", "iv", "ct"))
    return AESGCM(derive_key(password, salt)).decrypt(iv, ct, None).decode("utf-8")


PANEL = """
<div id="jw-lock" class="jw-lock" hidden>
  <div class="jw-lock-card">
    <p class="jw-lock-knock">Knock knock.</p>
    <p class="jw-lock-who">Who&rsquo;s there?</p>
    <form class="jw-lock-form" autocomplete="off">
      <input id="jw-pw" class="jw-lock-input" type="password" placeholder="thou shalt speak" aria-label="Password" autocomplete="current-password">
      <button class="jw-lock-btn" type="submit">bitte</button>
    </form>
    <p id="jw-msg" class="jw-lock-msg" aria-live="polite"></p>
  </div>
</div>
<div id="jw-content" hidden></div>
<script type="application/json" id="jw-vault">__VAULT__</script>
<style>
.jw-lock { display: flex; justify-content: center; padding: 4rem 1rem 6rem; }
.jw-lock-card { width: min(26rem, 100%); text-align: center; }
.jw-lock-knock { font-size: 2.2rem; font-weight: 700; line-height: 1.1; margin: 0; color: rgb(var(--color-neutral-800)); }
.dark .jw-lock-knock { color: rgb(var(--color-neutral-100)); }
.jw-lock-who { margin: 0.4rem 0 1.6rem; font-size: 1.1rem; color: rgb(var(--color-neutral-500)); }
.dark .jw-lock-who { color: rgb(var(--color-neutral-400)); }
.jw-lock-form { display: flex; gap: 0.5rem; }
.jw-lock-input { flex: 1; min-width: 0; padding: 0.7rem 0.95rem; border-radius: 0.75rem;
  border: 1px solid rgba(var(--color-primary-500), 0.4); background: rgba(var(--color-primary-500), 0.06);
  color: inherit; font-size: 1rem; outline: none; transition: border-color 0.2s ease, box-shadow 0.2s ease; }
.jw-lock-input:focus { border-color: rgb(var(--color-primary-500)); box-shadow: 0 0 0 4px rgba(var(--color-primary-500), 0.18); }
.jw-lock-input.is-wrong { animation: jw-shake 0.4s ease; border-color: rgb(220, 90, 90); }
.jw-lock-btn { padding: 0.7rem 1.1rem; border-radius: 0.75rem; border: 0; cursor: pointer; font-weight: 600;
  background: rgb(var(--color-primary-600)); color: #fff; transition: background-color 0.2s ease, transform 0.15s ease; }
.jw-lock-btn:hover { background: rgb(var(--color-primary-700)); transform: translateY(-1px); }
.dark .jw-lock-btn { background: rgb(var(--color-primary-500)); }
.dark .jw-lock-btn:hover { background: rgb(var(--color-primary-400)); }
.jw-lock-msg { min-height: 1.5em; margin: 1rem 0 0; font-size: 0.95rem; color: rgb(var(--color-neutral-500)); }
.jw-lock-msg.is-bad { color: rgb(220, 90, 90); }
#jw-content { animation: jw-reveal 0.5s ease; }
@keyframes jw-shake { 0%,100% { transform: translateX(0); } 20%,60% { transform: translateX(-6px); } 40%,80% { transform: translateX(6px); } }
@keyframes jw-reveal { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .jw-lock-input.is-wrong, #jw-content { animation: none; } }
</style>
<script>
(function () {
  var DECOY = "__DECOY__", TRIES = 3, LOCK_MS = 24 * 60 * 60 * 1000;
  var K_LOCK = "jw_lock_until", K_TRIES = "jw_tries", K_PW = "jw_pw";
  var store = function (k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} };
  var load = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var sess = function (k, v) { try { if (v === undefined) return sessionStorage.getItem(k); if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch (e) { return null; } };

  var until = parseInt(load(K_LOCK) || "0", 10);
  if (until && Date.now() < until) { location.replace(DECOY); return; }
  if (until) { store(K_LOCK, null); store(K_TRIES, null); }

  var vault = JSON.parse(document.getElementById("jw-vault").textContent);
  var lock = document.getElementById("jw-lock"), out = document.getElementById("jw-content");
  var form = lock.querySelector("form"), input = document.getElementById("jw-pw"), msg = document.getElementById("jw-msg");
  var b64 = function (s) { var bin = atob(s), a = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i); return a; };

  function unlock(pw) {
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(pw), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(vault.s), iterations: vault.it, hash: "SHA-256" }, base,
        { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    }).then(function (key) {
      return crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(vault.iv) }, key, b64(vault.ct));
    }).then(function (buf) {
      out.innerHTML = new TextDecoder().decode(buf);
      lock.hidden = true; out.hidden = false;
      // Run the scripts the page content may carry (e.g. the subject rail).
      Array.prototype.forEach.call(out.querySelectorAll("script"), function (old) {
        var s = document.createElement("script"); s.textContent = old.textContent; old.replaceWith(s);
      });
      store(K_TRIES, null);
      sess(K_PW, pw);
    });
  }

  var remembered = sess(K_PW);
  var shown = function () { lock.hidden = false; setTimeout(function () { input.focus(); }, 50); };
  if (remembered) { unlock(remembered).catch(function () { sess(K_PW, null); shown(); }); } else { shown(); }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var pw = input.value;
    if (!pw) return;
    unlock(pw).catch(function () {
      var tries = parseInt(load(K_TRIES) || "0", 10) + 1;
      store(K_TRIES, String(tries));
      input.value = ""; input.classList.remove("is-wrong"); void input.offsetWidth; input.classList.add("is-wrong");
      msg.classList.add("is-bad");
      if (tries >= TRIES) {
        msg.textContent = "Fine. Welcome.";
        store(K_LOCK, String(Date.now() + LOCK_MS));
        setTimeout(function () { location.replace(DECOY); }, 900);
      } else if (tries === TRIES - 1) {
        msg.textContent = "Shabi. Last try.";
      } else {
        msg.textContent = "Social credits -10,000,000!";
      }
    });
  });
})();
</script>
"""


IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=["\']?)([^"\'\s>]+)', re.I)
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}


def inline_images(content: str, page_dir: str, site_root: str) -> tuple[str, list[str]]:
    """Replace local <img src> with data: URIs; return the files to delete."""
    used: list[str] = []

    def repl(m):
        src = m.group(2)
        if src.startswith(("data:", "http:", "https:", "//")):
            return m.group(0)
        path = os.path.normpath(os.path.join(site_root, src.lstrip("/"))) if src.startswith("/") \
            else os.path.normpath(os.path.join(page_dir, src.split("?")[0]))
        ext = os.path.splitext(path)[1].lower()
        if ext not in MIME or not os.path.isfile(path):
            return m.group(0)
        with open(path, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("ascii")
        used.append(path)
        return m.group(1) + f"data:{MIME[ext]};base64,{data}"

    # Responsive variants would be loose files too: take the largest srcset
    # candidate as the src, then drop srcset/sizes so one folded-in image
    # carries the picture.
    def biggest(m):
        tag = m.group(0)
        ss = re.search(r'\ssrcset=["\']([^"\']*)["\']', tag, re.I)
        if ss:
            best, bw = None, -1
            for cand in ss.group(1).split(","):
                parts = cand.strip().split()
                if not parts:
                    continue
                w = int(parts[1][:-1]) if len(parts) > 1 and parts[1].endswith("w") and parts[1][:-1].isdigit() else 0
                if w > bw:
                    best, bw = parts[0], w
            if best:
                tag = re.sub(r'(\ssrc=["\']?)[^"\'\s>]+', lambda mm: mm.group(1) + best, tag, count=1, flags=re.I)
        return re.sub(r'\s(?:srcset|sizes)=["\'][^"\']*["\']', "", tag, flags=re.I)
    content = re.sub(r"<img\b[^>]*>", biggest, content, flags=re.I)
    content = IMG_SRC_RE.sub(repl, content)
    # Nothing in a protected page's folder may stay fetchable: remove every
    # image file there, including resized copies Hugo made.
    if os.path.isdir(page_dir):
        for f in os.listdir(page_dir):
            if os.path.splitext(f)[1].lower() in MIME:
                full = os.path.join(page_dir, f)
                if full not in used:
                    used.append(full)
    return content, used


def lock_html(html: str, password: str, decoy: str, page_dir: str = "", site_root: str = "") -> tuple[str, list[str]]:
    m = MAIN_RE.search(html)
    if not m:
        raise ValueError("no <main> element found")
    content, used = inline_images(m.group(2), page_dir, site_root) if page_dir else (m.group(2), [])
    vault = encrypt(password, content)
    panel = PANEL.replace("__VAULT__", json.dumps(vault)).replace("__DECOY__", decoy)
    html = html[: m.start(2)] + panel + html[m.end(2):]
    html = DESC_RE.sub("", html)
    html = DESC_RE2.sub("", html)
    html = LDJSON_RE.sub("", html)
    return html, used


def find_protected(root: str) -> list[str]:
    found = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".html"):
                path = os.path.join(dirpath, f)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(20000)
                if MARKER_RE.search(head):
                    found.append(path)
    return sorted(found)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", help="built site directory (public)")
    ap.add_argument("--decoy", default="/shabi/", help="where locked-out visitors are sent")
    args = ap.parse_args(argv)

    pages = find_protected(args.site)
    if not pages:
        print("No protected pages.", file=sys.stderr)
        return 0
    password = os.environ.get("PAGE_PASSWORD", "")
    if len(password) < 4:
        print(f"error: {len(pages)} protected page(s) but PAGE_PASSWORD is not set "
              "(repository secret: Settings > Secrets and variables > Actions)", file=sys.stderr)
        return 2
    removed: set[str] = set()
    for path in pages:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        html, used = lock_html(html, password, args.decoy, os.path.dirname(path), args.site)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        removed.update(used)
        print(f"  locked {os.path.relpath(path, args.site)}" + (f" (+{len(used)} image(s) folded in)" if used else ""), file=sys.stderr)
    for f in removed:
        os.remove(f)
    print(f"Locked {len(pages)} page(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
