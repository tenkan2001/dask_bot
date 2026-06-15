import requests
import os
from geopy.geocoders import Nominatim
from dotenv import load_dotenv

#Dans ce fichier avec le token de openweather, cet classe fait appel au API quand l'utilisateur tape le nom de la ville souhaité, et puis récupère et renvoi le résultat en json
load_dotenv()
WEATHER_TOKEN = os.getenv("WEATHER_TOKEN")

class OpenWeatherMapAPIClient:
    def __init__(self, api_token, name):
        self.base_url = "https://api.openweathermap.org"
        self._api_token = WEATHER_TOKEN
        self.name = name
    
    def get_geodata(self, location):
        geolocator = Nominatim(user_agent=self.name)
        geodata = geolocator.geocode(location, language="en-us").raw

        return geodata["lat"], geodata["lon"]

    def get_current_weather(self, location, units="metric"):
        url = f"{self.base_url}/data/2.5/weather"
        lat, lon = self.get_geodata(location)
        params = {
            "lat": lat,
            "lon": lon,
            "units": units,
            "appid": self._api_token,
        }

        response = requests.get(url, params=params)
        data = response.json()

        return data