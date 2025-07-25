from typing import final
from flask import Flask, request, render_template, jsonify
from datetime import datetime
import re
import urllib.parse
import requests
from playwright.sync_api import sync_playwright

# Test urls for regex:
# https://www.google.com/maps/place/Eiffel+Tower/@48.8584,2.2945,17z
# https://google.com/maps/place/Statue+of+Liberty/@40.6892,-74.0445,17z
# https://maps.google.com/maps?q=Big+Ben,+London # has an issue, doesnt work
# https://maps.app.goo.gl/4jnZLELvmpvBmFvx8
# https://maps.app.goo.gl/jXqDkM2NWN55kZcd9?g_st=com.google.maps.preview.copy
# https://www.google.co.uk/maps/place/Buckingham+Palace/@51.5014,-0.1419,17z
# https://www.google.de/maps/place/Brandenburger+Tor/@52.5163,13.3777,17z

debug_enabled = False
is_headless = not debug_enabled
print(f"is_headless: {is_headless}")
log_file_path = ""
app = Flask(__name__)

GMAPS_URL_RE = re.compile(
	r"""(?x)  # Verbose mode
	^https?://
	(
		(www\.)?
		(google\.[a-z.]+/maps)			  |		# www.google.com/maps, google.co.uk/maps, etc.
		(maps\.google\.[a-z.]+)			  |		# maps.google.com
		(goo\.gl/maps)					  |		# goo.gl/maps
		(maps\.app\.goo\.gl)					# maps.app.goo.gl
		# (maps\.app\.goo\.gl.*\.preview\.copy)	# maps.app.goo.gl(...).preview.copy
	)
	""",
	re.IGNORECASE
)

# ---- Dispatcher
def extract_coordinates(url: str):
	if ".preview.copy" in url:
		return handle_preview_copy_url(url)
	if "maps?q=" in url:
		return handle_browser_resolved_url(url)
	else:
		return handle_standard_url(url)

# ---- Handler: preview.copy links
def handle_preview_copy_url(url: str):
	url = url.split('?')[0]
	input_url = resolve_initial_redirect(url)
	if "consent.google.com" in input_url:
		parsed = urllib.parse.urlparse(input_url)
		query = urllib.parse.parse_qs(parsed.query)
		continue_url = query.get("continue", [""])[0]
		if continue_url:
			input_url = urllib.parse.unquote(continue_url)
		else:
			log_msg("ERROR", "No 'continue' parameter found.")
			return None, input_url
	final_url = extract_with_playwright(input_url)
	coord = extract_coords_from_url(final_url)
	return coord, final_url

# ---- Handler: links with only a query containing place names (https://maps.google.com/maps?q=Big+Ben,+London)
def handle_browser_resolved_url(url: str):
	input_url = resolve_initial_redirect(url)
	if "consent.google.com" in input_url:
		parsed = urllib.parse.urlparse(input_url)
		query = urllib.parse.parse_qs(parsed.query)
		continue_url = query.get("continue", [""])[0]
		if continue_url:
			input_url = urllib.parse.unquote(continue_url)
		else:
			log_msg("ERROR", "No 'continue' parameter found.")
			return None, input_url
	final_url = extract_with_playwright(input_url)
	coord = extract_coords_from_url(final_url)
	return coord, final_url

# ---- Handler: standard links
def handle_standard_url(url: str):
	try:
		# Follow redirect to get final destination
		response = requests.head(url, allow_redirects=True, timeout=10)
		final_url = response.url
		log_msg("DEBUG", "Final URL:", final_url)
	except requests.RequestException as e:
		raise RuntimeError(f"Failed to resolve standard URL: {e}")
	coords = extract_coords_from_url(final_url)
	return coords, final_url

# ---- Utility: redirect resolver
def resolve_initial_redirect(url: str):
	try:
		response = requests.get(url, allow_redirects=True, timeout=10)
		return response.url
	except Exception as e:
		log_msg("ERROR", "Redirect failed: ", e)
		return url

# ---- Utility: use playwright to get the final rendered URL
def extract_with_playwright(url:str):
	with sync_playwright() as p:
		browser = p.chromium.launch(headless=is_headless)
		page = browser.new_page()
		page.goto(url)
		# Click reject button if necessary
		try:
			page.locator('button:has-text("Reject all")').first.click(timeout=5000)
		except:
			pass # No reject button
		page.wait_for_function(
				"""() => window.location.href.includes('/@')""",
				timeout=15000
		)
		final_url = page.url
		log_msg("DEBUG", "Final URL: ", final_url)
		browser.close()
		return final_url

# ---- Utility: extract coordinates with regex patterns
def extract_coords_from_url(url: str):
	patterns = [
		r'/@([-.\d]+),([-.\d]+)',				 # Matches /@lat,lon
		r'/place/([-.\d]+),([-.\d]+)',			 # Matches /place/lat,lon
		r'/search/([-.\d]+),\+?([-.\d]+)',
		r'[?&]q=([-.\d]+),([-.\d]+)',			 # Matches ?q=lat,lon
		r'[?&]ll=([-.\d]+),([-.\d]+)',			 # Matches ?ll=lat,lon
		r'[?&]center=([-.\d]+),([-.\d]+)',		 # Matches ?center=lat,lon
		r'!3d([-.\d]+)!4d([-.\d]+)'				 # Matches !3dlat!4dlon
	]
	for pattern in patterns:
		match = re.search(pattern, url)
		if match:
			return match.groups()
	return None

# ---- Utility: logging function to output and write to file
def log_msg(level: str, msg: str, optional_arg = None):
	ts = datetime.now()
	iso_ts = ts.isoformat()
	if level == "DEBUG" and debug_enabled == False:
		return
	if optional_arg:
		log_line = f"[{iso_ts}]:[{level}]: {msg} {optional_arg}"
	else:
		log_line = f"[{iso_ts}]:[{level}]: {msg}"
	print(log_line)
	with open(log_file_path+"gmaps2osm_logs.txt", "a") as log_file:
		log_file.write(log_line+"\n")

@app.route("/", methods=["GET", "POST"])
def index():
	result = {}
	if request.method == "POST":
		url = request.form.get("gmaps_url", "").strip()
		log_msg("DEBUG", "URL:", url)
		if not url:
			result["error"] = "Please enter a Google Maps URL."
			log_msg("DEBUG", "Not a URL")
		else:
			try:
				if not GMAPS_URL_RE.search(url):
					result["error"] = "Please enter a valid Google Maps URL."
				else:
					coords, final_url = extract_coordinates(url)
					log_msg("DEBUG", "coords:", coords)
					if coords:
						lat, lon = coords
						result["latitude"] = lat
						result["longitude"] = lon
						result["osm_link"] = f"https://osmand.net/map?pin={lat},{lon}#16/{lat}/{lon}"
					else:
						raise ValueError("No coordinates found in the URL.")
			except ValueError as e:
				result["error"] = f"Error resolving or parsing URL: {e}"
	return render_template("index.html", **result)

if __name__ == "__main__":
	app.run(debug=True)
