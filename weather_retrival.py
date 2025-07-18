import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

# ✅ Function to initialize OpenMeteo session
def initialize_session():
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    client = openmeteo_requests.Client(session=retry_session)
    return client

# ✅ Function to get weather data
def get_weather_data(client, latitude, longitude, hourly_vars):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(hourly_vars)
    }
    responses = client.weather_api(url, params=params)
    return responses[0]

# ✅ Function to process weather response and convert to DataFrame
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
        values = hourly.Variables(idx).ValuesAsNumpy()
        hourly_data[var] = values
    hourly_df = pd.DataFrame(hourly_data)
    return hourly_df

# ✅ Function to do feature engineering on date column
def add_date_features(df):
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


# ✅ Main function to execute
def main():
    hourly_vars = [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature",
        "pressure_msl", "surface_pressure", "cloud_cover", "cloud_cover_low",
        "cloud_cover_mid", "cloud_cover_high", "wind_speed_10m", "wind_direction_10m",
        "wind_gusts_10m", "precipitation", "snowfall", "precipitation_probability",
        "weather_code", "wind_speed_80m", "wind_speed_120m", "wind_speed_180m",
        "wind_direction_80m", "wind_direction_120m", "wind_direction_180m", "rain", "showers"
    ]
    latitude, longitude = 25.5941, 85.1376
    client = initialize_session()
    response = get_weather_data(client, latitude, longitude, hourly_vars)

    print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")

    df = process_weather_response(response, hourly_vars)
    df = add_date_features(df)
    df.to_csv("weather_hourly.csv", index=False)
    print("✅ Weather data saved to weather_hourly.csv")

if __name__ == "__main__":
    main()
