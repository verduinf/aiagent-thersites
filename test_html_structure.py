import re
import requests

resp = requests.get('https://nu.nl')
html = resp.text

has_nav = bool(re.search(r'<nav', html, re.I))
has_header = bool(re.search(r'<header', html, re.I))
has_footer = bool(re.search(r'<footer', html, re.I))
has_article = bool(re.search(r'<article', html, re.I))
has_h2 = bool(re.search(r'<h2', html, re.I))

print(f"=== HTML SEMANTIC TAG CHECK FOR NU.NL ===")
print(f"Contains <nav>: {has_nav}")
print(f"Contains <header>: {has_header}")
print(f"Contains <footer>: {has_footer}")
print(f"Contains <article>: {has_article}")
print(f"Contains <h2>: {has_h2}")

# Let's check where the nav links come from in raw HTML
print("\n--- SAMPLE RAW HTML AROUND NAV LINKS ---")
nav_match = re.search(r'<(div|header|nav)[^>]*(header|nav|menu)[^>]*>.*?</\1>', html, re.DOTALL | re.I)
if nav_match:
    print(nav_match.group(0)[:500])
else:
    print("No class/id nav block found with simple regex, checking <a> tag containers...")
