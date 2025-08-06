from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
import os
import pandas as pd
from datetime import datetime, timedelta
import logging
import requests_cache
from retry_requests import retry
import openmeteo_requests
import json
import math

# Initialize Flask
app = Flask(__name__)

# -------------- CONFIGURATION ---------------
NEWS_API_KEY = "74a63b127ba544d182c0f037bd5fb533"
WEATHER_CSV_FILE = "weather_hourly_current.csv"
RESCUE_DATA_FILE = "rescue_members.json"

# -------------- LOGGING ---------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('weather_retrieval.log'), logging.StreamHandler()]
)

# -------------- RESCUE TEAM UTILITIES ---------------
def load_rescue_members():
    """Load rescue team members from JSON file"""
    try:
        if os.path.exists(RESCUE_DATA_FILE):
            with open(RESCUE_DATA_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logging.error(f"Error loading rescue members: {e}")
        return []

def save_rescue_members(members):
    """Save rescue team members to JSON file"""
    try:
        with open(RESCUE_DATA_FILE, 'w') as f:
            json.dump(members, f, indent=2)
        return True
    except Exception as e:
        logging.error(f"Error saving rescue members: {e}")
        return False

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates using Haversine formula"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance

def find_nearby_rescue_members(user_lat, user_lon, max_distance_km=50):
    """Find rescue team members within specified distance"""
    members = load_rescue_members()
    nearby_members = []
    
    for member in members:
        if 'location' in member and member['location']:
            member_lat = member['location']['latitude']
            member_lon = member['location']['longitude']
            distance = calculate_distance(user_lat, user_lon, member_lat, member_lon)
            
            if distance <= max_distance_km:
                member_copy = member.copy()
                member_copy['distance'] = round(distance, 2)
                nearby_members.append(member_copy)
    
    # Sort by distance
    nearby_members.sort(key=lambda x: x['distance'])
    return nearby_members

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
        "forecast_days": 7
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
    return datetime.now() - last_update > timedelta(hours=1)

def fetch_weather_if_needed():
    if not should_update_data():
        logging.info("Weather data is fresh.")
        return
    logging.info("Fetching new weather data...")
    try:
        hourly_vars = [
            "temperature_2m", "apparent_temperature", "relative_humidity_2m", 
            "dew_point_2m", "precipitation", "rain", "showers", "snowfall",
            "precipitation_probability", "cloud_cover", "cloud_cover_low", 
            "cloud_cover_mid", "cloud_cover_high", "wind_speed_10m", 
            "wind_speed_80m", "wind_speed_120m", "wind_speed_180m",
            "wind_direction_10m", "wind_direction_80m", "wind_direction_120m",
            "wind_direction_180m", "wind_gusts_10m", "pressure_msl", 
            "surface_pressure", "weather_code"
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

@app.route("/")
def index():
    """Login page"""
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    """Dashboard page - requires authentication via JavaScript"""
    fetch_weather_if_needed()
    return render_template("dashboard.html")

@app.route("/rescue")
def rescue():
    """Rescue team registration and management page"""
    return render_template("rescue.html")

# -------------- RESCUE TEAM API ROUTES ---------------

@app.route("/api/rescue/register", methods=["POST"])
def register_rescue_member():
    """Register a new rescue team member"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'phone', 'email', 'deptId', 'location']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Load existing members
        members = load_rescue_members()
        
        # Check for duplicates
        for member in members:
            if member['phone'] == data['phone']:
                return jsonify({"error": "Phone number already registered"}), 400
            if member['deptId'] == data['deptId']:
                return jsonify({"error": "Department ID already exists"}), 400
        
        # Create new member
        new_member = {
            "id": str(len(members) + 1),
            "name": data['name'],
            "phone": data['phone'],
            "email": data['email'],
            "deptId": data['deptId'],
            "specialization": data.get('specialization', 'general'),
            "location": data['location'],
            "registeredAt": datetime.now().isoformat()
        }
        
        # Add to members list
        members.append(new_member)
        
        # Save to file
        if save_rescue_members(members):
            logging.info(f"New rescue member registered: {new_member['name']}")
            return jsonify({"message": "Registration successful", "member": new_member}), 201
        else:
            return jsonify({"error": "Failed to save member data"}), 500
            
    except Exception as e:
        logging.error(f"Error registering rescue member: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/rescue/members")
def get_rescue_members():
    """Get nearby rescue team members"""
    try:
        # Get user location (you can also get this from request parameters)
        user_lat, user_lon = get_user_location()
        max_distance = float(request.args.get('max_distance', 50))  # km
        
        nearby_members = find_nearby_rescue_members(user_lat, user_lon, max_distance)
        
        return jsonify({
            "user_location": {"latitude": user_lat, "longitude": user_lon},
            "members": nearby_members,
            "total_count": len(nearby_members)
        })
        
    except Exception as e:
        logging.error(f"Error getting rescue members: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/rescue/emergency", methods=["POST"])
def emergency_alert():
    """Send emergency alert to nearby rescue members"""
    try:
        data = request.get_json()
        emergency_type = data.get('emergency_type', 'general')
        user_location = data.get('location')
        
        if not user_location:
            user_lat, user_lon = get_user_location()
        else:
            user_lat = user_location['latitude']
            user_lon = user_location['longitude']
        
        # Find nearby rescue members
        nearby_members = find_nearby_rescue_members(user_lat, user_lon, 10)  # 10km for emergencies
        
        # Filter by specialization if needed
        if emergency_type != 'general':
            nearby_members = [m for m in nearby_members if m.get('specialization') == emergency_type]
        
        # In a real application, you would send SMS/push notifications here
        # For now, we'll just return the list of members to contact
        
        alert_data = {
            "emergency_type": emergency_type,
            "user_location": {"latitude": user_lat, "longitude": user_lon},
            "nearby_rescue_members": nearby_members[:5],  # Top 5 closest
            "timestamp": datetime.now().isoformat()
        }
        
        logging.info(f"Emergency alert sent: {emergency_type} at {user_lat}, {user_lon}")
        return jsonify(alert_data)
        
    except Exception as e:
        logging.error(f"Error sending emergency alert: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/rescue/members/all")
def get_all_rescue_members():
    """Get all rescue team members (for admin/management purposes)"""
    try:
        members = load_rescue_members()
        return jsonify({
            "members": members,
            "total_count": len(members)
        })
    except Exception as e:
        logging.error(f"Error getting all rescue members: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/rescue/members/<member_id>", methods=["DELETE"])
def delete_rescue_member(member_id):
    """Delete a rescue team member"""
    try:
        members = load_rescue_members()
        
        # Find and remove the member
        updated_members = [m for m in members if m.get('id') != member_id]
        
        if len(updated_members) == len(members):
            return jsonify({"error": "Member not found"}), 404
        
        if save_rescue_members(updated_members):
            logging.info(f"Rescue member deleted: ID {member_id}")
            return jsonify({"message": "Member deleted successfully"})
        else:
            return jsonify({"error": "Failed to delete member"}), 500
            
    except Exception as e:
        logging.error(f"Error deleting rescue member: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/rescue/members/<member_id>", methods=["PUT"])
def update_rescue_member(member_id):
    """Update a rescue team member"""
    try:
        data = request.get_json()
        members = load_rescue_members()
        
        # Find the member to update
        member_index = None
        for i, member in enumerate(members):
            if member.get('id') == member_id:
                member_index = i
                break
        
        if member_index is None:
            return jsonify({"error": "Member not found"}), 404
        
        # Update allowed fields
        allowed_fields = ['name', 'phone', 'email', 'specialization']
        for field in allowed_fields:
            if field in data:
                members[member_index][field] = data[field]
        
        # Update timestamp
        members[member_index]['updatedAt'] = datetime.now().isoformat()
        
        if save_rescue_members(members):
            logging.info(f"Rescue member updated: ID {member_id}")
            return jsonify({"message": "Member updated successfully", "member": members[member_index]})
        else:
            return jsonify({"error": "Failed to update member"}), 500
            
    except Exception as e:
        logging.error(f"Error updating rescue member: {e}")
        return jsonify({"error": str(e)}), 500

# -------------- EXISTING API ROUTES ---------------

@app.route("/api/weather")
def api_weather():
    """API endpoint to get weather data as JSON"""
    try:
        if not os.path.exists(WEATHER_CSV_FILE):
            fetch_weather_if_needed()
        
        if os.path.exists(WEATHER_CSV_FILE):
            df = pd.read_csv(WEATHER_CSV_FILE)
            df['date'] = df['date'].astype(str)
            weather_data = df.to_dict(orient="records")
            return jsonify(weather_data)
        else:
            return jsonify({"error": "No weather data available"}), 404
    except Exception as e:
        logging.error(f"Error in weather API: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/news")
def api_news():
    """API endpoint to get news data as JSON"""
    city = request.args.get('city', '')
    if not city:
        return jsonify({"error": "City parameter is required"}), 400
    
    if not NEWS_API_KEY or NEWS_API_KEY == "your_news_api_key_here":
        return jsonify({"error": "News API key not configured"}), 500
    
    headlines = fetch_weather_news(city)
    return jsonify(headlines)

@app.route("/news", methods=["GET", "POST"])
def news():
    """News search page"""
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

    return render_template("news.html",
                           city=city,
                           headlines=headlines,
                           weather=weather_data,
                           error_message=error_message)

# -------------- UTILITY ROUTES ---------------

@app.route("/api/user-location")
def get_current_user_location():
    """Get current user location"""
    try:
        lat, lon = get_user_location()
        return jsonify({
            "latitude": lat,
            "longitude": lon,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logging.error(f"Error getting user location: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "weather_data": os.path.exists(WEATHER_CSV_FILE),
            "rescue_data": os.path.exists(RESCUE_DATA_FILE)
        }
    })

# -------------- ERROR HANDLERS ---------------

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({"error": "API endpoint not found"}), 404
    return render_template("index.html"), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

if __name__ == "__main__":
    # Create rescue data file if it doesn't exist
    if not os.path.exists(RESCUE_DATA_FILE):
        save_rescue_members([])
        logging.info(f"Created rescue data file: {RESCUE_DATA_FILE}")
    
    app.run(debug=True, host="0.0.0.0", port=5000)
