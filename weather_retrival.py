import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import requests
import time
import logging
from datetime import datetime, timedelta
import os
from geopy.geocoders import Nominatim

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('weather_retrieval.log'),
        logging.StreamHandler()
    ]
)

def initialize_session():
    """Initialize a cached session with retry functionality."""
    try:
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        client = openmeteo_requests.Client(session=retry_session)
        return client
    except Exception as e:
        logging.error(f"Error initializing session: {e}")
        raise

def get_user_location():
    """Get user's location with multiple fallback methods."""
    try:
        # Method 1: Try IP-based location first
        try:
            response = requests.get("https://ipinfo.io/json", timeout=5)
            response.raise_for_status()
            data = response.json()
            lat, lon = map(float, data["loc"].split(","))
            city = data.get("city", "unknown")
            logging.info(f"Location detected via IP: {lat}, {lon} near {city}")
            return lat, lon
        except Exception as ip_error:
            logging.warning(f"IP-based location failed: {ip_error}")

        default_lat, default_lon = 25.5941, 85.1356  # Patna, India
        logging.warning(f"Using default location: {default_lat}, {default_lon}")
        return default_lat, default_lon
        
    except Exception as e:
        logging.error(f"Error getting user location: {e}")
        raise

def get_weather_data(client, latitude, longitude, hourly_vars):
    """Fetch weather data from OpenMeteo API."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(hourly_vars),
            "timezone": "Asia/Kolkata",
            "forecast_days": 2  # Get current day and next day
        }
        responses = client.weather_api(url, params=params)
        return responses[0]
    except Exception as e:
        logging.error(f"Error fetching weather data: {e}")
        raise

def process_weather_response(response, hourly_vars):
    """Process API response into a DataFrame."""
    try:
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
            values = hourly.Variables(idx).ValuesAsNumpy()
            hourly_data[var] = values
            
        hourly_df = pd.DataFrame(hourly_data)
        return hourly_df
    except Exception as e:
        logging.error(f"Error processing weather response: {e}")
        raise

def add_date_features(df):
    """Add temporal features to the DataFrame."""
    try:
        df['date'] = pd.to_datetime(df['date'])
        df['date_only'] = df['date'].dt.date
        df['hour'] = df['date'].dt.hour
        df['minute'] = df['date'].dt.minute
        df['second'] = df['date'].dt.second
        df['day_of_week'] = df['date'].dt.dayofweek
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year
        df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
        return df
    except Exception as e:
        logging.error(f"Error adding date features: {e}")
        raise

def should_update_data():
    """Check if data needs to be updated (more than 24 hours old)."""
    if not os.path.exists("weather_hourly.csv"):
        return True
    
    file_time = os.path.getmtime("weather_hourly.csv")
    last_update = datetime.fromtimestamp(file_time)
    return datetime.now() - last_update > timedelta(hours=24)

def main():
    """Main function to execute weather data retrieval."""
    try:
        # Only proceed if data needs updating
        if not should_update_data():
            logging.info("Data is up-to-date. No need to refresh.")
            return
            
        hourly_vars = [
            "temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature",
            "pressure_msl", "surface_pressure", "cloud_cover", "cloud_cover_low",
            "cloud_cover_mid", "cloud_cover_high", "wind_speed_10m", "wind_direction_10m",
            "wind_gusts_10m", "precipitation", "snowfall", "precipitation_probability",
            "weather_code", "wind_speed_80m", "wind_speed_120m", "wind_speed_180m",
            "wind_direction_80m", "wind_direction_120m", "wind_direction_180m", "rain", "showers"
        ]
        
        logging.info("Starting weather data retrieval...")
        latitude, longitude = get_user_location()
        client = initialize_session()
        response = get_weather_data(client, latitude, longitude, hourly_vars)

        logging.info(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")

        df = process_weather_response(response, hourly_vars)
        df = add_date_features(df)
        
        # Save with timestamp in filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"weather_hourly.csv"
        df.to_csv(filename, index=False)
        
        # Also maintain a current version
        df.to_csv("weather_hourly_current.csv", index=False)
        
        logging.info(f"✅ Weather data saved to {filename} and weather_hourly.csv")
        
    except Exception as e:
        logging.error(f"Error in main execution: {e}")
        raise

def run_as_service():
    """Run the script as a continuous service with daily updates."""
    logging.info("Starting weather retrieval service...")
    while True:
        try:
            main()
            # Sleep for 6 hours before checking again (will only update if data is stale)
            time.sleep(6 * 3600)
        except KeyboardInterrupt:
            logging.info("Service stopped by user")
            break
        except Exception as e:
            logging.error(f"Service error: {e}. Restarting in 1 hour...")
            time.sleep(3600)

if __name__ == "__main__":
    # Run either as a one-time update or as a continuous service
    # Uncomment the one you want to use
    
    # Option 1: One-time update
    main()
    
    # Option 2: Run as continuous service (for production)
    # run_as_service()