"""Browser helper for job applications. One Chromium stays open between
commands (CDP on port 9222), so the form that was filled and screenshotted
is the same one that gets submitted after the owner approves.

  python .claude/skills/apply-job/form.py start                 launch the browser
  python .claude/skills/apply-job/form.py open URL              load a posting / application page
  python .claude/skills/apply-job/form.py inspect               list fields as JSON (question, type, options, selector)
  python .claude/skills/apply-job/form.py fill PLAN.json        fill fields: [{"selector":..., "action":"fill|check|select|upload|click|type", "value":...}]
                                               Yes/No buttons: {"action":"choose", "question":"text of the question", "value":"No"}
  python .claude/skills/apply-job/form.py shot OUT.png          full-page screenshot
  python .claude/skills/apply-job/form.py text                  visible page text (errors, confirmation)
  python .claude/skills/apply-job/form.py click "Button text"   click a button or link by its text
  python .claude/skills/apply-job/form.py stop                  close the browser

Run in the Claude Code cloud container: the proxy CA must be in the NSS
store (certutil -A -d sql:$HOME/.pki/nssdb -n ccr-agent-proxy -t "C,," -i
/root/.ccr/agent-proxy-ca.crt) and Chromium is /opt/pw-browsers/chromium.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PORT = 9222
CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium")
PROFILE = Path(os.environ.get("APPLY_PROFILE", "/tmp/apply-chrome"))

INSPECT_JS = r"""
() => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const question = e => {
    // The nearest container that carries question text: label, legend, or a heading-like sibling.
    if (e.labels && e.labels[0] && e.type !== 'radio' && e.type !== 'checkbox') return e.labels[0].innerText.trim();
    let n = e;
    for (let i = 0; i < 6 && n; i++, n = n.parentElement) {
      const l = n.querySelector && n.querySelector('legend, label:not(:has(input)), [class*="question"], [class*="label"]');
      if (l && l.innerText.trim() && !l.contains(e)) return l.innerText.trim();
    }
    return (e.getAttribute('aria-label') || e.placeholder || e.name || '').trim();
  };
  const sel = e => {
    if (e.id) return '#' + CSS.escape(e.id);
    if (e.name && e.type !== 'radio' && e.type !== 'checkbox') return `${e.tagName.toLowerCase()}[name="${e.name}"]`;
    if (e.name) return `input[name="${e.name}"][value="${CSS.escape(e.value)}"]`;
    return null;
  };
  const out = [];
  document.querySelectorAll('input, textarea, select').forEach((e, i) => {
    if (e.type === 'hidden' || e.type === 'submit') return;
    if (!vis(e) && e.type !== 'file' && e.type !== 'radio' && e.type !== 'checkbox') return;
    if (!sel(e)) e.setAttribute('data-apply-idx', String(i));
    out.push({
      selector: sel(e) || `[data-apply-idx="${i}"]`,
      tag: e.tagName.toLowerCase(), type: e.type || '',
      question: question(e).slice(0, 300),
      option: (e.type === 'radio' || e.type === 'checkbox') && e.labels && e.labels[0] ? e.labels[0].innerText.trim().slice(0, 200) : undefined,
      options: e.tagName === 'SELECT' ? [...e.options].map(o => o.text.trim()).filter(Boolean) : undefined,
      required: e.required || e.getAttribute('aria-required') === 'true',
      value: e.type === 'file' ? undefined : (e.type === 'radio' || e.type === 'checkbox' ? e.checked : e.value),
    });
  });
  return out;
}
"""


def _page():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, browser, page


def start():
    PROFILE.mkdir(parents=True, exist_ok=True)
    headless = os.environ.get("HEADLESS", "1") != "0"  # HEADLESS=0: visible window, on his own computer
    args = [CHROME] + (["--headless=new"] if headless else []) + [f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}", "--window-size=1280,1000", "--no-first-run"]
    if os.geteuid() == 0:  # the cloud container runs as root
        args.append("--no-sandbox")
    if os.environ.get("HTTPS_PROXY"):
        args.append(f"--proxy-server={os.environ['HTTPS_PROXY']}")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            print("browser ready")
            return
        except Exception:
            time.sleep(0.5)
    sys.exit("browser did not start")


def main(argv):
    cmd = argv[0]
    if cmd == "start":
        return start()
    if cmd == "stop":
        # "[r]" keeps pkill from matching its own command line
        subprocess.run(["pkill", "-f", f"[r]emote-debugging-port={PORT}"])
        return print("browser stopped")
    pw, browser, page = _page()
    try:
        if cmd == "open":
            page.goto(argv[1], wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector("input, textarea, select", timeout=20000)
            except Exception:
                pass
            print(page.title())
        elif cmd == "inspect":
            print(json.dumps(page.evaluate(INSPECT_JS), indent=1))
        elif cmd == "fill":
            plan = json.loads(Path(argv[1]).read_text())
            for step in plan:
                s, a, v = step["selector"], step.get("action", "fill"), step.get("value")
                loc = page.locator(s).first
                try:
                    if a == "fill":
                        loc.fill(str(v))
                    elif a == "type":  # autocomplete widgets: type, then pick the first match
                        loc.click()
                        loc.press_sequentially(str(v), delay=40)
                        page.wait_for_timeout(800)
                        page.keyboard.press("ArrowDown")
                        page.keyboard.press("Enter")
                    elif a == "check":
                        loc.check(force=True)
                    elif a == "select":
                        loc.select_option(label=str(v))
                    elif a == "upload":
                        loc.set_input_files(str(v))
                        page.wait_for_timeout(2500)
                    elif a == "click":
                        loc.click(force=True)
                    elif a == "choose":  # Yes/No buttons: click the answer inside its question
                        q = page.get_by_text(step["question"], exact=False).first
                        box = q.locator("xpath=ancestor::*[.//button or .//label][1]")
                        for _ in range(4):
                            hit = box.get_by_role("button", name=str(v), exact=True).or_(
                                box.get_by_text(str(v), exact=True))
                            if hit.count():
                                hit.first.click(force=True)
                                break
                            box = box.locator("xpath=..")
                        else:
                            raise RuntimeError(f"no '{v}' option near the question")
                    print(f"ok   {a:6} {s}")
                except Exception as e:  # report and keep going: the screenshot shows what is left
                    print(f"FAIL {a:6} {s}: {str(e).splitlines()[0][:120]}")
        elif cmd == "shot":
            page.screenshot(path=argv[1], full_page=True)
            print(argv[1])
        elif cmd == "text":
            print(page.inner_text("body")[:6000])
        elif cmd == "click":
            page.get_by_role("button", name=argv[1]).or_(page.get_by_text(argv[1], exact=True)).first.click()
            page.wait_for_timeout(4000)
            print(page.url)
        else:
            sys.exit(f"unknown command {cmd}")
    finally:
        pw.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
