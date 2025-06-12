from typing import final
from flask import Flask, request, render_template, jsonify
import re
import requests
import urllib.parse

from werkzeug.wrappers import response

app = Flask(__name__)

def extract_coordinates(url: str):
	"""
	Attempt to extract the coordinates from a google maps URL taking into consideration several of the formats.
	"""
	try:
		print(f"[DEBUG] Original URL: {url}")
		# Follow redirects
		response =requests.get(url, allow_redirects=True)
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
				return match.groups()
		return None
	except requests.RequestException as e:
		print(f"Error resolving or parsing URL: {e}")
		return None

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
				coords = extract_coordinates(url)
				if coords is None:
					raise ValueError("No coordinates found in the URL.")
				lat, lon = coords
				result["latitude"] = lat
				result["longitude"] = lon
				result["osm_link"] = f"https://osmand.net/map?pin={lat},{lon}#16/{lat}/{lon}"
			except ValueError as e:
				result["error"] = f"Error resolving or parsing URL: {e}"
		# coords = extract_coordinates(url)
		# if coords:
		# 	lat, lon = coords
		# 	return jsonify({"status": "success", "osm_link": osm_link})
		# else:
		# 	return jsonify({"status": "error", "message": "Could not extract coordinates."})
	return render_template("index.html", **result)

if __name__ == "__main__":
	app.run(debug=True)
