from flask import Flask, render_template, request
import requests

app = Flask(__name__)

# Add your News API key here
NEWS_API_KEY = "74a63b127ba544d182c0f037bd5fb533"

def fetch_weather_news(city):
    """
    Fetch weather-related news for a specific city using News API
    """
    url = f"https://newsapi.org/v2/everything?q={city}+weather&apiKey={NEWS_API_KEY}&language=en&sortBy=publishedAt&pageSize=20"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        headlines = []
        if data.get("articles"):
            for article in data["articles"]:
                # Filter out articles with null titles or URLs
                if article.get("title") and article.get("url"):
                    headlines.append({
                        "title": article["title"],
                        "url": article["url"],
                        "description": article.get("description", ""),
                        "source": article.get("source", {}).get("name", "Unknown"),
                        "publishedAt": article.get("publishedAt", "")
                    })
        
        return headlines
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []

@app.route("/", methods=["GET", "POST"])
def home():
    """
    Main route handling both GET and POST requests
    """
    headlines = []
    city = ""
    error_message = ""
    
    if request.method == "POST":
        city = request.form.get("city", "").strip()
        
        if city:
            if not NEWS_API_KEY or NEWS_API_KEY == "your_news_api_key_here":
                error_message = "Please add your News API key to the application."
            else:
                headlines = fetch_weather_news(city)
                if not headlines:
                    error_message = f"No weather news found for '{city}'. Please try a different city."
        else:
            error_message = "Please enter a city name."
    
    return render_template("index.html", 
                         city=city, 
                         headlines=headlines, 
                         error_message=error_message)

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template("index.html", error_message="Page not found."), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return render_template("index.html", error_message="Internal server error. Please try again."), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)