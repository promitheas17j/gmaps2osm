from typing import final
from flask import Flask, request, render_template, jsonify
import re
import requests
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
from werkzeug.wrappers import response
import tempfile
import shutil

app = Flask(__name__)

GMAPS_URL_RE = re.compile(
	r"""(?x)  # Verbose mode
	^https?://
	(
		(www\.)?
		(google\.[a-z.]+/maps)			  |  # www.google.com/maps, google.co.uk/maps, etc.
		(maps\.google\.[a-z.]+)			  |  # maps.google.com
		(goo\.gl/maps)					  |  # goo.gl/maps
		(maps\.app\.goo\.gl)				 # maps.app.goo.gl
	)
	""",
	re.IGNORECASE
)
# Test urls for regex:
# https://www.google.com/maps/place/Eiffel+Tower/@48.8584,2.2945,17z
# https://google.com/maps/place/Statue+of+Liberty/@40.6892,-74.0445,17z
# https://maps.google.com/maps?q=Big+Ben,+London
# https://goo.gl/maps/XkC3bN3EoVhM8P4j7
# https://maps.app.goo.gl/4jnZLELvmpvBmFvx8
# https://maps.app.goo.gl/jXqDkM2NWN55kZcd9?g_st=com.google.maps.preview.copy
# https://www.google.co.uk/maps/place/Buckingham+Palace/@51.5014,-0.1419,17z
# https://www.google.de/maps/place/Brandenburger+Tor/@52.5163,13.3777,17z


def extract_coordinates_for_place_name(url: str):
	"""
	For gmaps links which do not result in a link containing coordinates, use selenium to visit the link in a headless browser, wait a few seconds for the url to update with coordinates, and grab that link.
	"""
	options = Options()
	# options.headless = True
	options.page_load_strategy = "eager"
	options.add_argument("--headless=new")
	options.add_argument("--no-sandbox")
	options.add_argument("--disable-dev-shm-usage")
	options.add_argument("--disable-gpu")
	options.add_argument("--disable-extensions")
	# options.add_argument("--disable-background-networking")
	# options.add_argument("--disable-sync")
	options.add_argument("--disable-translate")
	options.add_argument("--metrics-recording-only")
	options.add_argument("--mute-audio")
	options.add_argument("--no-first-run")
	# options.add_argument("--safebrowsing-disable-auto-update")
	options.add_argument("--disable-features=VizDisplayCompositor")
	prefs = {
		"profile.managed_default_content_settings.images": 2,  # Disable images
		"profile.default_content_setting_values.notifications": 2,
		"profile.default_content_setting_values.geolocation": 2
	}
	options.add_experimental_option("prefs", prefs)
	temp_dir = tempfile.mkdtemp()
	options.add_argument(f"--user-data-dir={temp_dir}")
	driver = webdriver.Chrome(options=options)
	wait = WebDriverWait(driver, 10)
	try:
		print(f"[DEBUG] Visiting: {url}")
		driver.get(url)
		# time.sleep(5) # Wait for page to load - 5 seconds should be enough but increase if not
		# consent_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Reject all')]")))
		WebDriverWait(driver, 10).until(
			lambda d: (
				re.search(r"/(@|place/)[-.\d]+,[-.\d]+", d.current_url) or
				"Reject all" in d.page_source
			)
		)
		try:
			consent_button = WebDriverWait(driver, 3).until(
				EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Reject all')]")))
			consent_button.click()
			print("[DEBUG] Clicked on 'Reject all' button.")
		except:
			print("[DEBUG] No consent popup detected.")
		WebDriverWait(driver, 10).until(
				lambda d: re.search(r"/(@|place/)[-.\d]+,[-.\d]+", d.current_url)
			)
		print("[DEBUG] Coordinates detected in URL.")
		# consent_button.click()
		# print("[DEBUG] Clicked on consent button.")
		# time.sleep(3)
		final_url = driver.current_url
		print(f"[DEBUG] Final URL: {final_url}")
		patterns = [
			r'/@([-.\d]+),([-.\d]+)',  # /@lat,lon
			r'/place/([-.\d]+),([-.\d]+)',	# /place/lat,lon
			r'q=([-.\d]+),([-.\d]+)'  # ?q=lat,lon
		]
		for pattern in patterns:
			match = re.search(pattern, final_url)
			if match:
				print(f"[DEBUG] final_url 2: {final_url}")
				return match.groups(), final_url
		return None, final_url
	finally:
		driver.quit()
		shutil.rmtree(temp_dir)

def extract_coordinates(url: str):
	"""
	Attempt to extract the coordinates from a google maps URL taking into consideration several of the formats.
	"""
	try:
		print(f"[DEBUG] Original URL: {url}")
		# Follow redirects
		response =requests.get(url, allow_redirects=True)
		print(f"[DEBUG] Final resolved URL: {response.url}")
		print(f"[DEBUG] Redirect history:")
		for i, r in enumerate(response.history):
			print(f"  [{i}] {r.status_code} -> {r.url}")
		final_url = response.url
		print(f"[DEBUG] Final URL: {final_url}")
		# Handle google consent redirect
		if "consent.google.com" in final_url:
			parsed = urllib.parse.urlparse(final_url)
			query = urllib.parse.parse_qs(parsed.query)
			continue_url = query.get("continue", [""])[0]
			final_url = urllib.parse.unquote(continue_url)
			print(f"[DEBUG] Final URL after consent redirect: {final_url}")
		patterns = [
			r'/@([-.\d]+),([-.\d]+)',
			r'/search/([-.\d]+),\+?([-.\d]+)',
			r'[?&]q=([-.\d]+),([-.\d]+)',
			r'[?&]ll=([-.\d]+),([-.\d]+)',
			r'[?&]center=([-.\d]+),([-.\d]+)',
			r'!3d([-.\d]+)!4d([-.\d]+)'
		]
		for pattern in patterns:
			match = re.search(pattern, final_url)
			if match:
				print(f"[DEBUG] Match found with pattern '{pattern}': {match.groups()}")
				print(f"[DEBUG] final_url 1 {final_url}")
				return match.groups(), final_url
		return extract_coordinates_for_place_name(final_url)
		# return None, final_url
	except requests.RequestException as e:
		print(f"Error resolving or parsing URL: {e}")
		return None, None

@app.route("/", methods=["GET", "POST"])
def index():
	result = {}
	if request.method == "POST":
		url = request.form.get("gmaps_url", "").strip()
		print(f"[DEBUG] URL: {url}")
		if not url:
			result["error"] = "Please enter a Google Maps URL."
			print(f"[DEBUG] Not a URL")
		else:
			try:
				if not GMAPS_URL_RE.search(url):
					result["error"] = "Please enter a valid Google Maps URL."
				else:
					coords, final_url = extract_coordinates(url)
					print(f"[DEBUG] coords: {coords}")
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
