from flask import Flask, render_template, request
import requests
import os
import pandas as pd
from datetime import datetime, timedelta
import logging
import requests_cache
from retry_requests import retry
import openmeteo_requests

# Initialize Flask
app = Flask(__name__)

# -------------- CONFIGURATION ---------------
NEWS_API_KEY = "74a63b127ba544d182c0f037bd5fb533"
WEATHER_CSV_FILE = "weather_hourly_current.csv"

# -------------- LOGGING ---------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('weather_retrieval.log'), logging.StreamHandler()]
)

# -------------- WEATHER UTILITIES ---------------
def initialize_session():
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    return openmeteo_requests.Client(session=retry_session)

def get_user_location():
    try:
        response = requests.get("https://ipinfo.io/json", timeout=5)
        response.raise_for_status()
        data = response.json()
        lat, lon = map(float, data["loc"].split(","))
        return lat, lon
    except Exception as e:
        logging.warning(f"Using default location (Patna) due to error: {e}")
        return 25.5941, 85.1356

def get_weather_data(client, latitude, longitude, hourly_vars):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(hourly_vars),
        "timezone": "Asia/Kolkata",
        "forecast_days": 2
    }
    responses = client.weather_api(url, params=params)
    return responses[0]

def process_weather_response(response, hourly_vars):
    hourly = response.Hourly()
    hourly_data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        )
    }
    for idx, var in enumerate(hourly_vars):
        hourly_data[var] = hourly.Variables(idx).ValuesAsNumpy()
    df = pd.DataFrame(hourly_data)
    return df

def add_date_features(df):
    df['date'] = pd.to_datetime(df['date'])
    df['hour'] = df['date'].dt.hour
    df['day'] = df['date'].dt.date
    df['is_weekend'] = df['date'].dt.dayofweek.isin([5, 6])
    return df

def should_update_data():
    if not os.path.exists(WEATHER_CSV_FILE):
        return True
    last_update = datetime.fromtimestamp(os.path.getmtime(WEATHER_CSV_FILE))
    return datetime.now() - last_update > timedelta(hours=6)

def fetch_weather_if_needed():
    if not should_update_data():
        logging.info("Weather data is fresh.")
        return
    logging.info("Fetching new weather data...")
    try:
        hourly_vars = [
            "temperature_2m", "relative_humidity_2m", "cloud_cover",
            "precipitation", "wind_speed_10m", "weather_code"
        ]
        lat, lon = get_user_location()
        client = initialize_session()
        response = get_weather_data(client, lat, lon, hourly_vars)
        df = process_weather_response(response, hourly_vars)
        df = add_date_features(df)
        df.to_csv(WEATHER_CSV_FILE, index=False)
        logging.info("Weather data updated.")
    except Exception as e:
        logging.error(f"Failed to fetch weather data: {e}")

# -------------- NEWS ---------------------
def fetch_weather_news(city):
    url = f"https://newsapi.org/v2/everything?q={city}+weather&apiKey={NEWS_API_KEY}&language=en&sortBy=publishedAt&pageSize=20"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        headlines = []
        for article in data.get("articles", []):
            if article.get("title") and article.get("url"):
                headlines.append({
                    "title": article["title"],
                    "url": article["url"],
                    "description": article.get("description", ""),
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "publishedAt": article.get("publishedAt", "")
                })
        return headlines
    except Exception as e:
        logging.error(f"Error fetching news: {e}")
        return []

# -------------- FLASK ROUTES ---------------------
@app.route("/", methods=["GET", "POST"])
def home():
    city = ""
    headlines = []
    error_message = ""
    
    if request.method == "POST":
        city = request.form.get("city", "").strip()
        if city:
            if not NEWS_API_KEY or NEWS_API_KEY == "your_news_api_key_here":
                error_message = "Please add your News API key."
            else:
                headlines = fetch_weather_news(city)
                if not headlines:
                    error_message = f"No news found for '{city}'. Try another city."
        else:
            error_message = "Please enter a city."

    fetch_weather_if_needed()

    weather_data = []
    if os.path.exists(WEATHER_CSV_FILE):
        try:
            df = pd.read_csv(WEATHER_CSV_FILE)
            today = datetime.now().date()
            weather_data = df[df["day"] == str(today)].to_dict(orient="records")
        except Exception as e:
            logging.error(f"Error loading weather data: {e}")

    return render_template("index.html",
                           city=city,
                           headlines=headlines,
                           weather=weather_data,
                           error_message=error_message)

@app.errorhandler(404)
def not_found(error):
    return render_template("index.html", error_message="Page not found."), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template("index.html", error_message="Internal server error."), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
